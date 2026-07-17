"""Explain the causal anatomy of the transferred Japan/Kuril alarm."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aftershock_hierarchy_lab import fit_hierarchical_target, robust_population
from aftershock_lab import DTYPE, fit_relaxation_model
from aftershock_meta_lab import load_population_manifest
from aftershock_transfer_lab import CALIBRATION_END_DAYS, load_sequence, make_transfer_bins
from external_sequential_monitor_lab import first_alarm_record
from poisson_regime_monitor import tail_scale_scan
from predictive_sequential_monitor_lab import (
    PROPOSAL_COUNT,
    sample_population_predictive_counts,
)


DEVELOPMENT_DIR = Path("data/aftershock_population")
JAPAN_DIR = Path("data/aftershock_external/japan_kuril_2016_2025")
TRANSFER_EVIDENCE = Path("artifacts/japan_transfer.json")
ISOLATION_EVIDENCE = Path("artifacts/japan_cohort_isolation_audit.json")
TARGET_EVENT_ID = "us6000ldbb"
EXPLANATORY_SAMPLES = 16384
EXPLANATORY_SEED = 2026073200
CHECKPOINT_DAYS = (3.6, 7.3, 14.8, 22.6, 30.0)


def zero_success_upper_bound(sample_count: int, alpha: float = 0.05) -> float:
    """Exact one-sided binomial upper bound after observing zero successes."""
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    return 1.0 - alpha ** (1.0 / sample_count)


def select_checkpoints(endpoint_records: list[dict]) -> list[dict]:
    """Select the last evaluated endpoint at or before each declared day."""
    selected = []
    used = set()
    for checkpoint in CHECKPOINT_DAYS:
        eligible = [row for row in endpoint_records if row["end_day"] <= checkpoint + 1e-9]
        if not eligible:
            continue
        row = eligible[-1]
        if row["bin"] in used:
            continue
        selected.append({**row, "checkpoint_day": checkpoint})
        used.add(row["bin"])
    return selected


def endpoint_trace(
    observed: torch.Tensor,
    expected: torch.Tensor,
    evaluation_starts: torch.Tensor,
    evaluation_ends: torch.Tensor,
    threshold: float,
) -> list[dict]:
    statistics, splits = tail_scale_scan(observed, expected)
    rows = []
    for index in range(len(observed)):
        split = int(splits[index])
        if split < 0:
            change_day = None
            tail_observed = None
            tail_expected = None
            multiplier = None
        else:
            change_day = float(evaluation_starts[split])
            tail_observed = float(observed[split : index + 1].sum())
            tail_expected = float(expected[split : index + 1].sum())
            multiplier = tail_observed / tail_expected
        rows.append(
            {
                "bin": index,
                "start_day": float(evaluation_starts[index]),
                "end_day": float(evaluation_ends[index]),
                "observed_count": float(observed[index]),
                "expected_count": float(expected[index]),
                "cumulative_observed": float(observed[: index + 1].sum()),
                "cumulative_expected": float(expected[: index + 1].sum()),
                "statistic": float(statistics[index]),
                "threshold_ratio": float(statistics[index] / threshold),
                "selected_change_bin": split if split >= 0 else None,
                "selected_change_day": change_day,
                "selected_tail_observed": tail_observed,
                "selected_tail_expected": tail_expected,
                "selected_tail_rate_multiplier": multiplier,
            }
        )
    return rows


def run_alarm_anatomy(
    development_dir: Path = DEVELOPMENT_DIR,
    japan_dir: Path = JAPAN_DIR,
    transfer_path: Path = TRANSFER_EVIDENCE,
    isolation_path: Path = ISOLATION_EVIDENCE,
    sample_count: int = EXPLANATORY_SAMPLES,
    seed: int = EXPLANATORY_SEED,
) -> dict:
    transfer = json.loads(transfer_path.read_text(encoding="utf-8"))
    isolation = json.loads(isolation_path.read_text(encoding="utf-8"))
    isolation_record = next(
        record for record in isolation["records"] if record["event_id"] == TARGET_EVENT_ID
    )
    if isolation_record["passes_boundary_free_priority"]:
        raise RuntimeError("expected the Izu target to fail the cohort-edge audit")
    transfer_fold = next(
        fold for fold in transfer["folds"] if fold["event_id"] == TARGET_EVENT_ID
    )
    transfer_batches = [
        batch for batch in transfer["batches"] if batch["event_id"] == TARGET_EVENT_ID
    ]
    threshold = statistics.median(batch["threshold"] for batch in transfer_batches)

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

    japan_specs, _ = load_population_manifest(japan_dir / "manifest.json")
    target_spec = next(spec for spec in japan_specs if spec.event_id == TARGET_EVENT_ID)
    target = load_sequence(target_spec, edges, japan_dir)
    pooling_strength = float(transfer["development_population"]["selected_pooling_strength"])
    fit = fit_hierarchical_target(
        target, edges, calibration_mask, population, pooling_strength
    )
    expected = fit.expected_counts[evaluation_mask]
    observed = target.counts[evaluation_mask]
    if not math.isclose(
        float(expected.sum()),
        transfer_fold["models"]["frozen_hierarchy"]["predicted_total"],
        rel_tol=1e-10,
    ):
        raise RuntimeError("reconstructed Izu forecast differs from transfer evidence")

    predictive_counts, effective_size = sample_population_predictive_counts(
        target,
        edges,
        calibration_mask,
        evaluation_mask,
        population,
        sample_count,
        seed,
        PROPOSAL_COUNT,
    )
    predictive_totals = predictive_counts.sum(dim=1)
    observed_total = float(observed.sum())
    lower_tail_count = int((predictive_totals <= observed_total).sum())
    predictive_statistics, _ = tail_scale_scan(predictive_counts, expected)
    predictive_maxima = predictive_statistics.max(dim=1).values
    observed_statistics, _ = tail_scale_scan(observed, expected)
    observed_maximum = float(observed_statistics.max())
    maximum_tail_count = int((predictive_maxima >= observed_maximum).sum())

    cumulative = predictive_counts.cumsum(dim=1)
    cumulative_lower = torch.quantile(cumulative, 0.1, dim=0)
    cumulative_median = torch.quantile(cumulative, 0.5, dim=0)
    cumulative_upper = torch.quantile(cumulative, 0.9, dim=0)
    endpoints = endpoint_trace(
        observed, expected, evaluation_starts, evaluation_ends, threshold
    )
    for index, row in enumerate(endpoints):
        row["predictive_cumulative_p10"] = float(cumulative_lower[index])
        row["predictive_cumulative_median"] = float(cumulative_median[index])
        row["predictive_cumulative_p90"] = float(cumulative_upper[index])

    alarm = first_alarm_record(
        observed, expected, threshold, evaluation_starts, evaluation_ends
    )
    first = endpoints[alarm["first_alarm_bin"]]
    return {
        "experiment": "causal anatomy of the transferred Japan/Kuril alarm",
        "claim_boundary": (
            "post-outcome explanatory audit of one frozen transfer alarm; no model, "
            "threshold, cohort, or decision rule is changed"
        ),
        "target": {
            "event_id": TARGET_EVENT_ID,
            "name": target.spec.name,
            "time": transfer_fold["time"],
            "magnitude": transfer_fold["magnitude"],
            "calibration_events": transfer_fold["calibration_events"],
            "evaluation_events": transfer_fold["evaluation_events"],
        },
        "cohort_edge_audit": isolation_record,
        "frozen_monitor": {
            "threshold_source": "median of four independent report-31 thresholds",
            "threshold": threshold,
            "thresholds": [batch["threshold"] for batch in transfer_batches],
            "first_alarm_day": alarm["first_alarm_day"],
            "estimated_change_day_at_first_alarm": alarm["estimated_change_day"],
            "direction": alarm["direction"],
            "rate_multiplier_at_first_alarm": alarm["rate_multiplier_at_alarm"],
            "first_alarm_tail_observed": first["selected_tail_observed"],
            "first_alarm_tail_expected": first["selected_tail_expected"],
            "maximum_statistic": observed_maximum,
            "maximum_threshold_ratio": observed_maximum / threshold,
        },
        "independent_predictive_audit": {
            "sample_count": sample_count,
            "seed": seed,
            "proposal_count": PROPOSAL_COUNT,
            "proposal_effective_sample_size": effective_size,
            "observed_total": observed_total,
            "predictive_total_p01": float(torch.quantile(predictive_totals, 0.01)),
            "predictive_total_p10": float(torch.quantile(predictive_totals, 0.1)),
            "predictive_total_median": float(torch.quantile(predictive_totals, 0.5)),
            "predictive_total_p90": float(torch.quantile(predictive_totals, 0.9)),
            "lower_or_equal_total_count": lower_tail_count,
            "lower_or_equal_total_fraction": lower_tail_count / sample_count,
            "zero_count_one_sided_95_upper": (
                zero_success_upper_bound(sample_count)
                if lower_tail_count == 0
                else None
            ),
            "maximum_statistic_tail_count": maximum_tail_count,
            "maximum_statistic_tail_fraction": maximum_tail_count / sample_count,
            "maximum_zero_count_one_sided_95_upper": (
                zero_success_upper_bound(sample_count)
                if maximum_tail_count == 0
                else None
            ),
        },
        "checkpoints": select_checkpoints(endpoints),
        "endpoints": endpoints,
        "predictive_totals": predictive_totals.tolist(),
    }


def plot_alarm_anatomy(report: dict, output_path: Path) -> None:
    endpoints = report["endpoints"]
    days = [row["end_day"] for row in endpoints]
    observed = [row["observed_count"] for row in endpoints]
    expected = [row["expected_count"] for row in endpoints]
    threshold = report["frozen_monitor"]["threshold"]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    count_axis, cumulative_axis, scan_axis, total_axis = axes.ravel()

    widths = [row["end_day"] - row["start_day"] for row in endpoints]
    count_axis.bar(
        [row["start_day"] for row in endpoints],
        observed,
        width=widths,
        align="edge",
        color="#0984e3",
        alpha=0.7,
        label="observed",
    )
    count_axis.plot(days, expected, "o-", color="#d63031", markersize=3, label="frozen expected")
    count_axis.set_xscale("log")
    count_axis.set(
        title="Evaluation-bin counts",
        xlabel="day after selected M6.1 event",
        ylabel="events per log-time bin",
    )
    count_axis.legend(frameon=False)
    count_axis.grid(alpha=0.2, which="both")

    cumulative_axis.fill_between(
        days,
        [row["predictive_cumulative_p10"] for row in endpoints],
        [row["predictive_cumulative_p90"] for row in endpoints],
        color="#74b9ff",
        alpha=0.35,
        label="predictive central 80%",
    )
    cumulative_axis.plot(
        days,
        [row["predictive_cumulative_median"] for row in endpoints],
        color="#0984e3",
        label="predictive median",
    )
    cumulative_axis.step(
        days,
        [row["cumulative_observed"] for row in endpoints],
        where="post",
        color="#2d3436",
        linewidth=2,
        label="observed",
    )
    cumulative_axis.set_xscale("log")
    cumulative_axis.set(
        title="The deficit accumulates gradually",
        xlabel="day after selected M6.1 event",
        ylabel="cumulative day-1+ events",
    )
    cumulative_axis.legend(frameon=False)
    cumulative_axis.grid(alpha=0.2, which="both")

    scan_axis.plot(days, [row["statistic"] for row in endpoints], "o-", color="#6c5ce7", markersize=3)
    scan_axis.axhline(threshold, color="#d63031", linestyle="--", label="transferred threshold")
    scan_axis.axvline(report["frozen_monitor"]["first_alarm_day"], color="#2d3436", linestyle=":", label="first crossing")
    scan_axis.set_xscale("log")
    scan_axis.set(
        title="Causal scan statistic",
        xlabel="monitoring endpoint (day)",
        ylabel="best tail-rate deviance",
    )
    scan_axis.legend(frameon=False)
    scan_axis.grid(alpha=0.2, which="both")

    totals = report["predictive_totals"]
    observed_total = report["independent_predictive_audit"]["observed_total"]
    total_axis.hist(totals, bins=60, color="#00b894", alpha=0.75)
    total_axis.axvline(observed_total, color="#d63031", linewidth=2, label=f"observed = {observed_total:.0f}")
    total_axis.set(
        title="Independent predictive-total audit",
        xlabel="simulated day-1-to-30 total",
        ylabel="paths",
    )
    total_axis.legend(frameon=False)
    total_axis.grid(alpha=0.2)

    fig.suptitle("Anatomy of the invalid 2023 Izu lower-rate alarm")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_alarm_anatomy()
    (output_dir / "japan_alarm_anatomy.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_alarm_anatomy(report, output_dir / "japan_alarm_anatomy.png")
    printable = {key: value for key, value in report.items() if key not in {"endpoints", "predictive_totals"}}
    print(json.dumps(printable, indent=2))


if __name__ == "__main__":
    main()
