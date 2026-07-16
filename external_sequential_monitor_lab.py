"""Externally audit the fixed-Poisson sequential aftershock monitor."""

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
from online_uncertainty_lab import prequential_forecasts
from poisson_regime_monitor import monte_carlo_threshold, tail_scale_scan


DEVELOPMENT_DIR = Path("data/aftershock_population")
EXTERNAL_DIR = Path("data/aftershock_external/alaska_2010_2025")
SOURCE_EVIDENCE = Path("artifacts/external_aftershock_validation.json")
FALSE_ALARM_RATE = 0.01
CALIBRATION_SAMPLES = 8192
VALIDATION_SAMPLES = 4096


def first_alarm_record(
    observed: torch.Tensor,
    expected: torch.Tensor,
    threshold: float,
    evaluation_starts: torch.Tensor,
    evaluation_ends: torch.Tensor,
) -> dict:
    """Return the first causal threshold crossing and full diagnostic trace."""
    statistics_trace, splits = tail_scale_scan(observed, expected)
    crossings = torch.nonzero(statistics_trace > threshold).flatten()
    first_alarm = int(crossings[0]) if len(crossings) else None
    if first_alarm is None:
        split_index = None
        first_alarm_day = None
        estimated_change_day = None
        rate_multiplier = None
        direction = None
    else:
        split_index = int(splits[first_alarm])
        observed_tail = observed[split_index : first_alarm + 1].sum()
        expected_tail = expected[split_index : first_alarm + 1].sum()
        rate_multiplier = float(observed_tail / expected_tail)
        direction = "higher" if rate_multiplier > 1.0 else "lower"
        first_alarm_day = float(evaluation_ends[first_alarm])
        estimated_change_day = float(evaluation_starts[split_index])
    return {
        "first_alarm_bin": first_alarm,
        "first_alarm_day": first_alarm_day,
        "estimated_change_bin": split_index,
        "estimated_change_day": estimated_change_day,
        "rate_multiplier_at_alarm": rate_multiplier,
        "direction": direction,
        "maximum_statistic": float(statistics_trace.max()),
        "maximum_threshold_ratio": float(statistics_trace.max() / threshold),
        "statistics": statistics_trace.tolist(),
        "observed_counts": observed.tolist(),
        "expected_counts": expected.tolist(),
    }


def _rank_correlation(first: list[float], second: list[float]) -> float:
    """Spearman correlation for values without material ties."""
    if len(first) != len(second) or len(first) < 2:
        raise ValueError("rank correlation needs equal lists with at least two values")

    def ranks(values: list[float]) -> torch.Tensor:
        order = sorted(range(len(values)), key=values.__getitem__)
        result = torch.empty(len(values), dtype=DTYPE)
        for rank, index in enumerate(order):
            result[index] = rank
        return result

    left = ranks(first)
    right = ranks(second)
    left = left - left.mean()
    right = right - right.mean()
    return float((left * right).sum() / torch.sqrt((left.square().sum()) * (right.square().sum())))


def _binary_summary(records: list[dict], outcome_key: str) -> dict:
    positives = [record for record in records if record[outcome_key] is True]
    negatives = [record for record in records if record[outcome_key] is False]
    alarmed = [record for record in records if record["first_alarm_bin"] is not None]
    quiet = [record for record in records if record["first_alarm_bin"] is None]
    true_positive = sum(record[outcome_key] is True for record in alarmed)
    false_positive = sum(record[outcome_key] is False for record in alarmed)
    return {
        "eligible": len(records),
        "outcome_positive": len(positives),
        "outcome_negative": len(negatives),
        "alarmed": len(alarmed),
        "quiet": len(quiet),
        "positive_alarmed": true_positive,
        "negative_alarmed": false_positive,
        "sensitivity": true_positive / len(positives) if positives else None,
        "negative_alarm_fraction": false_positive / len(negatives) if negatives else None,
        "alarm_precision": true_positive / len(alarmed) if alarmed else None,
        "positive_prevalence": len(positives) / len(records) if records else None,
        "quiet_negative_fraction": (
            sum(record[outcome_key] is False for record in quiet) / len(quiet)
            if quiet
            else None
        ),
        "quiet_positive_event_ids": [
            record["event_id"] for record in quiet if record[outcome_key] is True
        ],
    }


def summarize_records(records: list[dict]) -> dict:
    alarmed = [record for record in records if record["first_alarm_bin"] is not None]
    quiet = [record for record in records if record["first_alarm_bin"] is None]
    rolling = [record for record in records if record["rolling_interval_miss"] is not None]
    null_rates = [record["empirical_null_false_alarm_rate"] for record in records]
    return {
        "sequence_count": len(records),
        "alarmed_sequences": len(alarmed),
        "observed_alarm_fraction": len(alarmed) / len(records),
        "raw_interval_miss_association": _binary_summary(
            records, "raw_interval_miss"
        ),
        "rolling_interval_miss_association": _binary_summary(
            rolling, "rolling_interval_miss"
        ),
        "alarm_timing": {
            "median_first_alarm_day": statistics.median(
                record["first_alarm_day"] for record in alarmed
            ),
            "alarmed_by_day_3_6": sum(
                record["first_alarm_day"] <= 3.6 for record in alarmed
            ),
            "alarmed_by_day_7_3": sum(
                record["first_alarm_day"] <= 7.3 for record in alarmed
            ),
            "higher": sum(record["direction"] == "higher" for record in alarmed),
            "lower": sum(record["direction"] == "lower" for record in alarmed),
        },
        "shape_association": {
            "median_deviance_alarmed": statistics.median(
                record["hierarchy_poisson_deviance"] for record in alarmed
            ),
            "median_deviance_quiet": statistics.median(
                record["hierarchy_poisson_deviance"] for record in quiet
            ),
            "spearman_max_ratio_vs_deviance": _rank_correlation(
                [record["maximum_threshold_ratio"] for record in records],
                [record["hierarchy_poisson_deviance"] for record in records],
            ),
        },
        "fixed_null_validation": {
            "requested_false_alarm_rate": FALSE_ALARM_RATE,
            "mean_empirical_false_alarm_rate": statistics.mean(null_rates),
            "minimum_empirical_false_alarm_rate": min(null_rates),
            "maximum_empirical_false_alarm_rate": max(null_rates),
        },
    }


def run_external_monitor_audit(
    development_dir: Path = DEVELOPMENT_DIR,
    external_dir: Path = EXTERNAL_DIR,
    evidence_path: Path = SOURCE_EVIDENCE,
) -> dict:
    source = json.loads(evidence_path.read_text(encoding="utf-8"))
    source_folds = {fold["event_id"]: fold for fold in source["folds"]}
    rolling_rows = {
        row["event_id"]: row
        for row in prequential_forecasts(source["folds"], mode="rolling")["rows"]
    }
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
    frozen_population = robust_population(
        development_fits, list(range(len(development_fits)))
    )
    frozen_strength = float(
        source["development_population"]["selected_pooling_strength"]
    )

    external_specs, _ = load_population_manifest(external_dir / "manifest.json")
    external_sequences = [
        load_sequence(spec, edges, external_dir) for spec in external_specs
    ]
    records = []
    for index, sequence in enumerate(external_sequences):
        source_fold = source_folds[sequence.spec.event_id]
        fit = fit_hierarchical_target(
            sequence,
            edges,
            calibration_mask,
            frozen_population,
            frozen_strength,
        )
        expected = fit.expected_counts[evaluation_mask]
        observed = sequence.counts[evaluation_mask]
        recorded_total = float(
            source_fold["models"]["frozen_hierarchy"]["predicted_total"]
        )
        if not math.isclose(float(expected.sum()), recorded_total, rel_tol=1e-10):
            raise RuntimeError(
                f"reconstructed forecast differs for {sequence.spec.event_id}"
            )

        calibration_seed = 20260727 + index
        validation_seed = 20261727 + index
        threshold, calibration_maxima = monte_carlo_threshold(
            expected,
            FALSE_ALARM_RATE,
            CALIBRATION_SAMPLES,
            torch.Generator().manual_seed(calibration_seed),
        )
        validation_counts = torch.poisson(
            expected.expand(VALIDATION_SAMPLES, -1),
            generator=torch.Generator().manual_seed(validation_seed),
        )
        validation_statistics, _ = tail_scale_scan(validation_counts, expected)
        validation_maxima = validation_statistics.max(dim=1).values
        empirical_false_alarm = float(
            (validation_maxima > threshold).to(DTYPE).mean()
        )
        monitor = first_alarm_record(
            observed, expected, threshold, evaluation_starts, evaluation_ends
        )
        rolling = rolling_rows.get(sequence.spec.event_id)
        records.append(
            {
                "event_id": sequence.spec.event_id,
                "name": sequence.spec.name,
                "time": source_fold["time"],
                "raw_interval_miss": not bool(
                    source_fold["predictive_distribution"]["total_covered"]
                ),
                "rolling_interval_miss": (
                    None if rolling is None else not bool(rolling["covered"])
                ),
                "hierarchy_poisson_deviance": float(
                    source_fold["models"]["frozen_hierarchy"]["poisson_deviance"]
                ),
                "threshold": threshold,
                "calibration_seed": calibration_seed,
                "validation_seed": validation_seed,
                "calibration_maximum_p99": float(
                    torch.quantile(calibration_maxima, 0.99)
                ),
                "empirical_null_false_alarm_rate": empirical_false_alarm,
                "evaluation_start_days": evaluation_starts.tolist(),
                "evaluation_end_days": evaluation_ends.tolist(),
                **monitor,
            }
        )

    return {
        "experiment": "external audit of fixed-Poisson sequential regime monitor",
        "claim_boundary": (
            "unchanged monitor design applied retrospectively to the geographic "
            "external cohort; fixed-Poisson calibration is conditional, not predictive"
        ),
        "source_experiment": source["experiment"],
        "null": "fixed frozen-hierarchy expected bin counts with independent Poisson noise",
        "false_alarm_rate": FALSE_ALARM_RATE,
        "calibration_samples_per_sequence": CALIBRATION_SAMPLES,
        "validation_samples_per_sequence": VALIDATION_SAMPLES,
        "summary": summarize_records(records),
        "records": records,
    }


def plot_external_monitor_audit(report: dict, output_path: Path) -> None:
    records = report["records"]
    summary = report["summary"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    trace_axis, outcome_axis, deviance_axis, timing_axis = axes.ravel()

    for record in records:
        normalized = torch.tensor(record["statistics"]) / record["threshold"]
        trace_axis.plot(
            record["evaluation_end_days"],
            normalized,
            color="#d63031" if record["raw_interval_miss"] else "#0984e3",
            alpha=0.65 if record["first_alarm_bin"] is not None else 0.3,
            linewidth=1.1,
        )
    trace_axis.plot([], [], color="#d63031", label="raw total miss")
    trace_axis.plot([], [], color="#0984e3", label="raw total covered")
    trace_axis.axhline(1.0, color="#2d3436", linestyle="--")
    trace_axis.set_xscale("log")
    trace_axis.set_yscale("log")
    trace_axis.set(
        title="External sequential traces",
        xlabel="day after mainshock",
        ylabel="statistic / fixed-null threshold",
    )
    trace_axis.legend(frameon=False, fontsize=8)
    trace_axis.grid(alpha=0.2, which="both")

    association = summary["raw_interval_miss_association"]
    alarm_counts = [
        association["positive_alarmed"],
        association["negative_alarmed"],
    ]
    totals = [association["outcome_positive"], association["outcome_negative"]]
    quiet_counts = [total - alarm for total, alarm in zip(totals, alarm_counts)]
    outcome_axis.bar((0, 1), alarm_counts, color="#d63031", label="alarm")
    outcome_axis.bar(
        (0, 1), quiet_counts, bottom=alarm_counts, color="#b2bec3", label="quiet"
    )
    outcome_axis.set_xticks((0, 1), ("raw interval\nmiss", "raw interval\ncovered"))
    outcome_axis.set(
        title="Alarm is only weakly enriched for total misses",
        ylabel="external sequences",
    )
    outcome_axis.legend(frameon=False)
    outcome_axis.grid(axis="y", alpha=0.2)

    for record in records:
        deviance_axis.scatter(
            record["hierarchy_poisson_deviance"],
            record["maximum_threshold_ratio"],
            marker="o" if record["first_alarm_bin"] is not None else "x",
            color="#d63031" if record["raw_interval_miss"] else "#0984e3",
            alpha=0.8,
        )
    deviance_axis.scatter([], [], marker="o", color="#636e72", label="alarm")
    deviance_axis.scatter([], [], marker="x", color="#636e72", label="quiet")
    deviance_axis.scatter([], [], marker="s", color="#d63031", label="raw miss")
    deviance_axis.scatter([], [], marker="s", color="#0984e3", label="raw covered")
    deviance_axis.axhline(1.0, color="#2d3436", linestyle="--")
    deviance_axis.set_xscale("log")
    deviance_axis.set_yscale("log")
    deviance_axis.set(
        title="Monitor tracks temporal-shape deviance",
        xlabel="frozen hierarchy Poisson deviance",
        ylabel="maximum statistic / threshold",
    )
    deviance_axis.legend(frameon=False, fontsize=7)
    deviance_axis.grid(alpha=0.2, which="both")

    alarmed = [record for record in records if record["first_alarm_bin"] is not None]
    for direction, color in (("higher", "#e17055"), ("lower", "#6c5ce7")):
        subset = [record for record in alarmed if record["direction"] == direction]
        timing_axis.scatter(
            [record["first_alarm_day"] for record in subset],
            [record["rate_multiplier_at_alarm"] for record in subset],
            color=color,
            alpha=0.8,
            label=direction,
        )
    timing_axis.axhline(1.0, color="#2d3436", linestyle="--")
    timing_axis.set_yscale("log")
    timing_axis.set(
        title="First external alarm state",
        xlabel="first alarm day",
        ylabel="observed / expected tail rate",
    )
    timing_axis.legend(frameon=False)
    timing_axis.grid(alpha=0.2, which="both")

    fig.suptitle("A calibrated fixed-Poisson monitor meets a much wider real process")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_external_monitor_audit()
    (output_dir / "external_sequential_monitor.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_external_monitor_audit(
        report, output_dir / "external_sequential_monitor.png"
    )
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
