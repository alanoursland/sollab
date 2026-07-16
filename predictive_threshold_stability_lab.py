"""Repeat predictive-null calibration across independent proposal batches."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aftershock_hierarchy_lab import robust_population
from aftershock_lab import DTYPE, fit_relaxation_model
from aftershock_meta_lab import load_population_manifest
from aftershock_transfer_lab import CALIBRATION_END_DAYS, load_sequence, make_transfer_bins
from external_sequential_monitor_lab import first_alarm_record
from predictive_sequential_monitor_lab import (
    CALIBRATION_SAMPLES,
    DEVELOPMENT_DIR,
    EXTERNAL_DIR,
    PROPOSAL_COUNT,
    sample_population_predictive_counts,
    threshold_from_predictive_streams,
)


PREDICTIVE_EVIDENCE = Path("artifacts/predictive_sequential_monitor.json")
FIXED_EVIDENCE = Path("artifacts/external_sequential_monitor.json")
REPEATS = 8
TARGET_PANEL = {
    "ak01479djus2": "predictive alarm",
    "us10004x1w": "predictive alarm",
    "us2000cmy3": "predictive alarm and low ESS",
    "us6000c9hg": "predictive alarm and minimum ESS",
    "us200030aq": "highest validation rate",
    "usp000j7dc": "second-highest validation rate",
    "ak018fcnsk91": "third-highest validation rate",
    "ak018aap2cqu": "low ESS and high validation rate",
    "us7000nx3z": "low ESS quiet target",
}


def coefficient_of_variation(values: list[float]) -> float:
    if not values or statistics.mean(values) == 0.0:
        raise ValueError("values must have a nonzero mean")
    return statistics.pstdev(values) / statistics.mean(values)


def summarize_target(
    target: dict, repeats: list[dict], selection_reason: str | None = None
) -> dict:
    thresholds = [item["threshold"] for item in repeats]
    effective_sizes = [item["proposal_effective_sample_size"] for item in repeats]
    alarm_days = [item["first_alarm_day"] for item in repeats if item["alarm"]]
    original_alarm = bool(target["predictive_alarm"])
    repeat_alarms = sum(item["alarm"] for item in repeats)
    return {
        "event_id": target["event_id"],
        "name": target["name"],
        "selection_reason": (
            TARGET_PANEL.get(target["event_id"], "unspecified")
            if selection_reason is None
            else selection_reason
        ),
        "raw_interval_miss": target.get("raw_interval_miss"),
        "rolling_interval_miss": target.get("rolling_interval_miss"),
        "original_threshold": float(target["predictive_threshold"]),
        "original_alarm": original_alarm,
        "repeat_count": len(repeats),
        "repeat_alarm_count": repeat_alarms,
        "repeat_alarm_fraction": repeat_alarms / len(repeats),
        "classification_stable": repeat_alarms in (0, len(repeats)),
        "classification_matches_original_in_every_repeat": (
            repeat_alarms == len(repeats) if original_alarm else repeat_alarms == 0
        ),
        "threshold_minimum": min(thresholds),
        "threshold_median": statistics.median(thresholds),
        "threshold_maximum": max(thresholds),
        "threshold_coefficient_of_variation": coefficient_of_variation(thresholds),
        "threshold_max_to_min": max(thresholds) / min(thresholds),
        "original_threshold_empirical_rank": sum(
            value <= target["predictive_threshold"] for value in thresholds
        )
        / len(thresholds),
        "proposal_ess_minimum": min(effective_sizes),
        "proposal_ess_median": statistics.median(effective_sizes),
        "proposal_ess_maximum": max(effective_sizes),
        "first_alarm_day_minimum": min(alarm_days) if alarm_days else None,
        "first_alarm_day_median": statistics.median(alarm_days) if alarm_days else None,
        "first_alarm_day_maximum": max(alarm_days) if alarm_days else None,
    }


def summarize_panel(
    targets: list[dict], repeats_per_target: int = REPEATS
) -> dict:
    unstable = [target for target in targets if not target["classification_stable"]]
    mismatched = [
        target
        for target in targets
        if not target["classification_matches_original_in_every_repeat"]
    ]
    original_alarms = [target for target in targets if target["original_alarm"]]
    quiet = [target for target in targets if not target["original_alarm"]]
    most_variable = max(
        targets, key=lambda target: target["threshold_coefficient_of_variation"]
    )
    return {
        "target_count": len(targets),
        "repeats_per_target": repeats_per_target,
        "total_calibrations": len(targets) * repeats_per_target,
        "stable_classification_count": len(targets) - len(unstable),
        "unstable_event_ids": [target["event_id"] for target in unstable],
        "all_repeats_match_original_count": len(targets) - len(mismatched),
        "mismatched_event_ids": [target["event_id"] for target in mismatched],
        "original_alarm_target_count": len(original_alarms),
        "original_alarm_repeat_alarm_fractions": {
            target["event_id"]: target["repeat_alarm_fraction"]
            for target in original_alarms
        },
        "original_quiet_repeat_alarm_fractions": {
            target["event_id"]: target["repeat_alarm_fraction"] for target in quiet
        },
        "median_target_threshold_cv": statistics.median(
            target["threshold_coefficient_of_variation"] for target in targets
        ),
        "maximum_target_threshold_cv": most_variable[
            "threshold_coefficient_of_variation"
        ],
        "maximum_cv_event_id": most_variable["event_id"],
        "median_target_threshold_max_to_min": statistics.median(
            target["threshold_max_to_min"] for target in targets
        ),
    }


def run_threshold_stability(
    predictive_path: Path = PREDICTIVE_EVIDENCE,
    fixed_path: Path = FIXED_EVIDENCE,
    development_dir: Path = DEVELOPMENT_DIR,
    external_dir: Path = EXTERNAL_DIR,
    target_panel: dict[str, str] | None = None,
    repeats: int = REPEATS,
    seed_base: int = 2026072900,
    claim_boundary: str | None = None,
) -> dict:
    if repeats < 1:
        raise ValueError("repeats must be positive")
    selected_panel = TARGET_PANEL if target_panel is None else target_panel
    predictive = json.loads(predictive_path.read_text(encoding="utf-8"))
    predictive_by_id = {
        record["event_id"]: record for record in predictive["records"]
    }
    fixed = json.loads(fixed_path.read_text(encoding="utf-8"))
    fixed_by_id = {record["event_id"]: record for record in fixed["records"]}

    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    evaluation_starts = edges[:-1][evaluation_mask]
    evaluation_ends = edges[1:][evaluation_mask]
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)

    development_specs, _ = load_population_manifest(development_dir / "manifest.json")
    development_sequences = [
        load_sequence(spec, edges, development_dir) for spec in development_specs
    ]
    development_fits = [
        fit_relaxation_model("omori", edges, sequence.counts, all_mask, sequence.background)
        for sequence in development_sequences
    ]
    population = robust_population(development_fits, list(range(len(development_fits))))

    external_specs, _ = load_population_manifest(external_dir / "manifest.json")
    sequence_by_id = {
        spec.event_id: load_sequence(spec, edges, external_dir) for spec in external_specs
    }
    target_summaries = []
    batch_records = []
    for target_position, event_id in enumerate(selected_panel):
        sequence = sequence_by_id[event_id]
        target = predictive_by_id[event_id]
        fixed_record = fixed_by_id[event_id]
        central_expected = torch.tensor(fixed_record["expected_counts"], dtype=DTYPE)
        observed = torch.tensor(fixed_record["observed_counts"], dtype=DTYPE)
        repeat_records = []
        for repeat in range(repeats):
            seed = seed_base + 100 * target_position + repeat
            counts, effective_size = sample_population_predictive_counts(
                sequence,
                edges,
                calibration_mask,
                evaluation_mask,
                population,
                CALIBRATION_SAMPLES,
                seed,
                PROPOSAL_COUNT,
            )
            threshold, _, rank = threshold_from_predictive_streams(
                counts, central_expected
            )
            monitor = first_alarm_record(
                observed,
                central_expected,
                threshold,
                evaluation_starts,
                evaluation_ends,
            )
            batch = {
                "event_id": event_id,
                "repeat": repeat,
                "seed": seed,
                "threshold": threshold,
                "threshold_rank": rank,
                "proposal_effective_sample_size": effective_size,
                "alarm": monitor["first_alarm_bin"] is not None,
                "first_alarm_day": monitor["first_alarm_day"],
                "direction": monitor["direction"],
            }
            repeat_records.append(batch)
            batch_records.append(batch)
        target_summaries.append(
            summarize_target(target, repeat_records, selected_panel[event_id])
        )

    return {
        "experiment": "independent proposal-batch stability of predictive monitor thresholds",
        "claim_boundary": claim_boundary or (
            "post-hoc diagnostic panel selected from report 28 alarms, high "
            "validation rates, and low effective sample sizes"
        ),
        "proposal_count": PROPOSAL_COUNT,
        "predictive_paths_per_calibration": CALIBRATION_SAMPLES,
        "repeats_per_target": repeats,
        "target_panel": selected_panel,
        "summary": summarize_panel(target_summaries, repeats),
        "targets": target_summaries,
        "batches": batch_records,
    }


def plot_threshold_stability(report: dict, output_path: Path) -> None:
    targets = report["targets"]
    batches = report["batches"]
    aliases = {target["event_id"]: target["event_id"] for target in targets}
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    threshold_axis, alarm_axis, variability_axis, ess_axis = axes.ravel()

    for position, target in enumerate(targets):
        target_batches = [
            batch for batch in batches if batch["event_id"] == target["event_id"]
        ]
        threshold_axis.scatter(
            [position] * len(target_batches),
            [batch["threshold"] for batch in target_batches],
            color="#6c5ce7",
            alpha=0.65,
        )
        threshold_axis.scatter(
            position,
            target["original_threshold"],
            marker="x",
            s=70,
            color="#d63031",
        )
    threshold_axis.set_yscale("log")
    threshold_axis.set_xticks(
        range(len(targets)), [aliases[target["event_id"]] for target in targets], rotation=55, ha="right"
    )
    threshold_axis.set(title="Fresh-batch thresholds", ylabel="predictive threshold")
    threshold_axis.scatter([], [], color="#6c5ce7", label="repeat")
    threshold_axis.scatter([], [], marker="x", color="#d63031", label="report 28")
    threshold_axis.legend(frameon=False)
    threshold_axis.grid(alpha=0.2, which="both")

    colors = ["#d63031" if target["original_alarm"] else "#0984e3" for target in targets]
    alarm_axis.bar(
        range(len(targets)),
        [target["repeat_alarm_fraction"] for target in targets],
        color=colors,
    )
    alarm_axis.set_xticks(
        range(len(targets)), [target["event_id"] for target in targets], rotation=55, ha="right"
    )
    alarm_axis.set(
        title="Alarm classification across repeats",
        ylabel="fraction of fresh batches that alarm",
        ylim=(0, 1.05),
    )
    alarm_axis.grid(axis="y", alpha=0.2)

    variability_axis.bar(
        range(len(targets)),
        [100 * target["threshold_coefficient_of_variation"] for target in targets],
        color="#e17055",
    )
    variability_axis.set_xticks(
        range(len(targets)), [target["event_id"] for target in targets], rotation=55, ha="right"
    )
    variability_axis.set(
        title="Threshold Monte Carlo variability",
        ylabel="coefficient of variation (%)",
    )
    variability_axis.grid(axis="y", alpha=0.2)

    for target in targets:
        ess_axis.scatter(
            target["proposal_ess_median"],
            100 * target["threshold_coefficient_of_variation"],
            color="#d63031" if target["original_alarm"] else "#0984e3",
        )
        ess_axis.annotate(
            target["event_id"],
            (target["proposal_ess_median"], 100 * target["threshold_coefficient_of_variation"]),
            fontsize=7,
            xytext=(3, 3),
            textcoords="offset points",
        )
    ess_axis.set(
        title="Low ESS is not the only instability source",
        xlabel="median proposal effective sample size",
        ylabel="threshold CV (%)",
    )
    ess_axis.grid(alpha=0.2)

    fig.suptitle("Is the hierarchy-predictive alarm reproducible across proposal batches?")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_threshold_stability()
    (output_dir / "predictive_threshold_stability.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_threshold_stability(report, output_dir / "predictive_threshold_stability.png")
    print(json.dumps(report["summary"], indent=2))
    for target in report["targets"]:
        print(
            target["event_id"],
            f"alarms={target['repeat_alarm_count']}/{target['repeat_count']}",
            f"cv={100 * target['threshold_coefficient_of_variation']:.1f}%",
            f"range={target['threshold_max_to_min']:.2f}x",
        )


if __name__ == "__main__":
    main()
