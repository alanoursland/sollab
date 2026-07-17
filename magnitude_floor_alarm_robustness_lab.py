"""Refit the Alaska predictive alarm audit across reported-magnitude floors."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aftershock_hierarchy_lab import fit_hierarchical_target, robust_population
from aftershock_lab import DTYPE, fit_relaxation_model, poisson_deviance
from aftershock_meta_lab import load_population_manifest
from aftershock_transfer_lab import (
    CALIBRATION_END_DAYS,
    CONTROL_END_DAYS,
    CONTROL_START_DAYS,
    SequenceData,
    make_transfer_bins,
)
from external_sequential_monitor_lab import first_alarm_record
from predictive_sequential_monitor_lab import (
    PROPOSAL_COUNT,
    sample_population_predictive_counts,
    threshold_from_predictive_streams,
)


DEVELOPMENT_DIR = Path("data/aftershock_population")
EXTERNAL_DIR = Path("data/aftershock_external/alaska_2010_2025")
OUTPUT = Path("artifacts/magnitude_floor_alarm_robustness.json")
PLOT = Path("artifacts/magnitude_floor_alarm_robustness.png")
FLOORS = (2.5, 3.0, 3.5, 4.0)
MINIMUM_CALIBRATION_EVENTS = 15
MINIMUM_EVALUATION_EVENTS = 15
POOLING_STRENGTH = 4.0
CALIBRATION_SAMPLES = 8192
REPEATS = 4
INVALID_EXTERNAL_EVENT_IDS = {"us6000b56k"}
REFERENCE_ALARM_EVENT_IDS = {
    "ak01479djus2",
    "us10004x1w",
    "us2000cmy3",
    "us6000c9hg",
}


def load_sequence_at_floor(
    spec,
    edges: torch.Tensor,
    data_dir: Path,
    magnitude_floor: float,
) -> SequenceData:
    """Load one frozen CSV after explicitly reapplying a magnitude floor."""
    if not math.isfinite(magnitude_floor):
        raise ValueError("magnitude_floor must be finite")
    path = data_dir / f"{spec.slug}.csv"
    payload = path.read_bytes()
    rows = list(csv.DictReader(payload.decode("utf-8").splitlines()))
    times = []
    for row in rows:
        if row["id"] == spec.event_id:
            continue
        magnitude_text = row.get("mag", "")
        if not magnitude_text:
            continue
        magnitude = float(magnitude_text)
        if not math.isfinite(magnitude) or magnitude < magnitude_floor:
            continue
        event_time = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        times.append((event_time - spec.origin).total_seconds() / 86400.0)
    time_tensor = torch.tensor(times, dtype=DTYPE)
    usable = time_tensor[(time_tensor >= edges[0]) & (time_tensor <= edges[-1])]
    counts = torch.histogram(usable, bins=edges).hist.to(dtype=DTYPE)
    control_count = int(
        (
            (time_tensor >= CONTROL_START_DAYS)
            & (time_tensor < CONTROL_END_DAYS)
        ).sum()
    )
    return SequenceData(
        spec=spec,
        times_days=time_tensor,
        counts=counts,
        background=control_count / (CONTROL_END_DAYS - CONTROL_START_DAYS),
        sha256=hashlib.sha256(payload).hexdigest(),
        source_rows=len(rows),
    )


def event_support(
    sequence: SequenceData,
    calibration_mask: torch.Tensor,
    evaluation_mask: torch.Tensor,
) -> dict[str, int | bool]:
    calibration = int(sequence.counts[calibration_mask].sum())
    evaluation = int(sequence.counts[evaluation_mask].sum())
    return {
        "calibration_events": calibration,
        "evaluation_events": evaluation,
        "eligible": (
            calibration >= MINIMUM_CALIBRATION_EVENTS
            and evaluation >= MINIMUM_EVALUATION_EVENTS
        ),
    }


def repeat_summary(repeats: list[dict]) -> dict:
    if not repeats:
        raise ValueError("repeats cannot be empty")
    alarm_count = sum(item["alarm"] for item in repeats)
    alarm_days = [item["first_alarm_day"] for item in repeats if item["alarm"]]
    thresholds = [item["threshold"] for item in repeats]
    return {
        "repeat_count": len(repeats),
        "alarm_count": alarm_count,
        "alarm_fraction": alarm_count / len(repeats),
        "unanimous_alarm": alarm_count == len(repeats),
        "majority_alarm": alarm_count > len(repeats) / 2,
        "threshold_minimum": min(thresholds),
        "threshold_median": statistics.median(thresholds),
        "threshold_maximum": max(thresholds),
        "first_alarm_day_median": (
            statistics.median(alarm_days) if alarm_days else None
        ),
        "directions": sorted(
            {item["direction"] for item in repeats if item["direction"] is not None}
        ),
        "proposal_ess_median": statistics.median(
            item["proposal_effective_sample_size"] for item in repeats
        ),
    }


def summarize_floor(records: list[dict]) -> dict:
    unanimous = [record for record in records if record["unanimous_alarm"]]
    majority = [record for record in records if record["majority_alarm"]]
    reference = [
        record for record in records if record["event_id"] in REFERENCE_ALARM_EVENT_IDS
    ]
    return {
        "eligible_external_sequences": len(records),
        "unanimous_alarm_count": len(unanimous),
        "unanimous_alarm_fraction": len(unanimous) / len(records) if records else None,
        "unanimous_alarm_event_ids": [record["event_id"] for record in unanimous],
        "majority_alarm_count": len(majority),
        "majority_alarm_event_ids": [record["event_id"] for record in majority],
        "eligible_reference_alarm_event_ids": [
            record["event_id"] for record in reference
        ],
        "unanimous_reference_alarm_event_ids": [
            record["event_id"] for record in reference if record["unanimous_alarm"]
        ],
    }


def run_floor_robustness(
    development_dir: Path = DEVELOPMENT_DIR,
    external_dir: Path = EXTERNAL_DIR,
    floors: tuple[float, ...] = FLOORS,
    repeats: int = REPEATS,
    calibration_samples: int = CALIBRATION_SAMPLES,
    proposal_count: int = PROPOSAL_COUNT,
    seed_base: int = 2026071600,
) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    evaluation_starts = edges[:-1][evaluation_mask]
    evaluation_ends = edges[1:][evaluation_mask]
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)
    development_specs, _ = load_population_manifest(development_dir / "manifest.json")
    external_specs, _ = load_population_manifest(external_dir / "manifest.json")
    external_specs = [
        spec for spec in external_specs if spec.event_id not in INVALID_EXTERNAL_EVENT_IDS
    ]

    floor_reports = []
    for floor_position, floor in enumerate(floors):
        development_loaded = [
            load_sequence_at_floor(spec, edges, development_dir, floor)
            for spec in development_specs
        ]
        development_support = [
            event_support(sequence, calibration_mask, evaluation_mask)
            for sequence in development_loaded
        ]
        development_sequences = [
            sequence
            for sequence, support in zip(development_loaded, development_support)
            if support["eligible"]
        ]
        if len(development_sequences) < 3:
            raise RuntimeError(
                f"magnitude floor {floor} leaves fewer than three development sequences"
            )
        development_fits = [
            fit_relaxation_model(
                "omori", edges, sequence.counts, all_mask, sequence.background,
            )
            for sequence in development_sequences
        ]
        population = robust_population(
            development_fits, list(range(len(development_fits)))
        )

        external_loaded = [
            load_sequence_at_floor(spec, edges, external_dir, floor)
            for spec in external_specs
        ]
        external_support = [
            event_support(sequence, calibration_mask, evaluation_mask)
            for sequence in external_loaded
        ]
        records = []
        excluded = []
        eligible_position = 0
        for sequence, support in zip(external_loaded, external_support):
            if not support["eligible"]:
                excluded.append({"event_id": sequence.spec.event_id, **support})
                continue
            fitted = fit_hierarchical_target(
                sequence,
                edges,
                calibration_mask,
                population,
                POOLING_STRENGTH,
            )
            central_expected = fitted.expected_counts[evaluation_mask]
            observed = sequence.counts[evaluation_mask]
            repeat_records = []
            for repeat in range(repeats):
                seed = (
                    seed_base
                    + 100000 * floor_position
                    + 100 * eligible_position
                    + repeat
                )
                sampled, effective_size = sample_population_predictive_counts(
                    sequence,
                    edges,
                    calibration_mask,
                    evaluation_mask,
                    population,
                    calibration_samples,
                    seed,
                    proposal_count,
                )
                threshold, _, rank = threshold_from_predictive_streams(
                    sampled, central_expected
                )
                monitor = first_alarm_record(
                    observed,
                    central_expected,
                    threshold,
                    evaluation_starts,
                    evaluation_ends,
                )
                repeat_records.append(
                    {
                        "repeat": repeat,
                        "seed": seed,
                        "threshold": threshold,
                        "threshold_rank": rank,
                        "proposal_effective_sample_size": effective_size,
                        "alarm": monitor["first_alarm_bin"] is not None,
                        "first_alarm_day": monitor["first_alarm_day"],
                        "direction": monitor["direction"],
                    }
                )
            records.append(
                {
                    "event_id": sequence.spec.event_id,
                    "name": sequence.spec.name,
                    "magnitude_floor": floor,
                    **support,
                    "background_events_per_day": sequence.background,
                    "observed_evaluation_total": float(observed.sum()),
                    "expected_evaluation_total": float(central_expected.sum()),
                    "observed_to_expected_ratio": float(
                        observed.sum() / central_expected.sum().clamp_min(1e-12)
                    ),
                    "poisson_deviance": poisson_deviance(
                        central_expected, observed
                    ),
                    "fit_parameters": fitted.parameters,
                    **repeat_summary(repeat_records),
                    "repeats": repeat_records,
                }
            )
            eligible_position += 1
        floor_reports.append(
            {
                "magnitude_floor": floor,
                "development_selected_sequences": len(development_specs),
                "development_eligible_sequences": len(development_sequences),
                "development_eligible_event_ids": [
                    sequence.spec.event_id for sequence in development_sequences
                ],
                "population_c_days": float(torch.exp(population.center[0])),
                "population_p": float(0.3 + 1.7 * torch.sigmoid(population.center[1])),
                "population_log_c_scale": float(population.scale[0]),
                "population_p_transform_scale": float(population.scale[1]),
                "summary": summarize_floor(records),
                "records": records,
                "excluded_external_sequences": excluded,
            }
        )
    return {
        "experiment": "reported-magnitude-floor robustness of Alaska predictive alarms",
        "claim_boundary": (
            "retrospective sensitivity audit; every floor refits the frozen model family "
            "and reapplies the original count-eligibility rule, but floors were chosen "
            "after seeing catalog-support differences"
        ),
        "external_cohort_policy": (
            "strict-clean Alaska cohort excluding the ambiguous us6000b56k target"
        ),
        "magnitude_floors": list(floors),
        "minimum_calibration_events": MINIMUM_CALIBRATION_EVENTS,
        "minimum_evaluation_events": MINIMUM_EVALUATION_EVENTS,
        "pooling_strength": POOLING_STRENGTH,
        "pooling_policy": (
            "frozen at the original external-validation value; not reselected per floor"
        ),
        "predictive_false_alarm_rate": 0.01,
        "proposal_count": proposal_count,
        "calibration_samples_per_repeat": calibration_samples,
        "repeats_per_target": repeats,
        "reference_alarm_event_ids": sorted(REFERENCE_ALARM_EVENT_IDS),
        "floor_reports": floor_reports,
    }


def plot_floor_robustness(report: dict, output_path: Path = PLOT) -> None:
    floors = [item["magnitude_floor"] for item in report["floor_reports"]]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    fig.patch.set_facecolor("white")
    eligibility_axis, alarm_axis, heat_axis, ratio_axis = axes.ravel()

    eligibility_axis.plot(
        floors,
        [item["development_eligible_sequences"] for item in report["floor_reports"]],
        "o-",
        label="western development",
        color="#0984e3",
    )
    eligibility_axis.plot(
        floors,
        [item["summary"]["eligible_external_sequences"] for item in report["floor_reports"]],
        "o-",
        label="strict-clean Alaska",
        color="#6c5ce7",
    )
    eligibility_axis.axhline(3, color="#636e72", linestyle="--", linewidth=1)
    eligibility_axis.set(
        title="Count support collapses as the floor rises",
        xlabel="reported-magnitude floor",
        ylabel="eligible sequences",
    )
    eligibility_axis.legend()
    eligibility_axis.grid(alpha=0.2)

    alarm_axis.plot(
        floors,
        [item["summary"]["unanimous_alarm_count"] for item in report["floor_reports"]],
        "o-",
        color="#d63031",
        label="all eligible",
    )
    alarm_axis.plot(
        floors,
        [len(item["summary"]["unanimous_reference_alarm_event_ids"]) for item in report["floor_reports"]],
        "s--",
        color="#e17055",
        label="original alarm IDs",
    )
    alarm_axis.set(
        title="Unanimous predictive alarms after refitting",
        xlabel="reported-magnitude floor",
        ylabel="event count",
    )
    alarm_axis.legend()
    alarm_axis.grid(alpha=0.2)

    by_floor = {
        item["magnitude_floor"]: {record["event_id"]: record for record in item["records"]}
        for item in report["floor_reports"]
    }
    event_ids = sorted(
        {
            record["event_id"]
            for item in report["floor_reports"]
            for record in item["records"]
            if record["alarm_count"] > 0
        }
        | REFERENCE_ALARM_EVENT_IDS
    )
    values = torch.full((len(event_ids), len(floors)), float("nan"), dtype=DTYPE)
    for row, event_id in enumerate(event_ids):
        for column, floor in enumerate(floors):
            record = by_floor[floor].get(event_id)
            if record is not None:
                values[row, column] = record["alarm_fraction"]
    masked = np.ma.masked_invalid(values.numpy())
    image = heat_axis.imshow(masked, vmin=0, vmax=1, cmap="YlOrRd", aspect="auto")
    heat_axis.set_xticks(range(len(floors)), [f"M{floor:g}" for floor in floors])
    heat_axis.set_yticks(range(len(event_ids)), event_ids, fontsize=8)
    heat_axis.set(title="Alarm fraction across four threshold calibrations")
    fig.colorbar(image, ax=heat_axis, label="alarm fraction")

    colors = {
        event_id: color
        for event_id, color in zip(
            sorted(REFERENCE_ALARM_EVENT_IDS),
            ("#d63031", "#e17055", "#fdcb6e", "#6c5ce7"),
        )
    }
    for event_id in sorted(REFERENCE_ALARM_EVENT_IDS):
        x_values, y_values = [], []
        for floor in floors:
            record = by_floor[floor].get(event_id)
            if record is not None:
                x_values.append(floor)
                y_values.append(record["observed_to_expected_ratio"])
        ratio_axis.plot(
            x_values,
            y_values,
            "o-",
            color=colors[event_id],
            label=event_id,
        )
    ratio_axis.axhline(1.0, color="#2d3436", linestyle="--", linewidth=1)
    ratio_axis.set(
        title="Original alarm sequences after floor-specific refitting",
        xlabel="reported-magnitude floor",
        ylabel="observed / expected evaluation total",
    )
    ratio_axis.legend(fontsize=8)
    ratio_axis.grid(alpha=0.2)

    fig.suptitle("Are Alaska predictive alarms invariant to catalog magnitude support?")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(output_path: Path = OUTPUT, plot_path: Path = PLOT) -> None:
    report = run_floor_robustness()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    plot_floor_robustness(report, plot_path)
    for floor in report["floor_reports"]:
        summary = floor["summary"]
        print(
            f"M{floor['magnitude_floor']:g}: "
            f"development={floor['development_eligible_sequences']}, "
            f"Alaska={summary['eligible_external_sequences']}, "
            f"unanimous alarms={summary['unanimous_alarm_count']} "
            f"{summary['unanimous_alarm_event_ids']}"
        )


if __name__ == "__main__":
    main()
