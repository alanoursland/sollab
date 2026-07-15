"""Calibrated sequential Poisson regime monitoring for aftershock forecasts."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aftershock_hierarchy_lab import fit_hierarchical_target, robust_population
from aftershock_lab import DTYPE, fit_relaxation_model
from aftershock_meta_lab import load_population_manifest
from aftershock_transfer_lab import CALIBRATION_END_DAYS, load_sequence, make_transfer_bins
from poisson_regime_monitor import (
    DEFAULT_MIN_POSTCHANGE_BINS,
    DEFAULT_MIN_PRECHANGE_BINS,
    monte_carlo_threshold,
    tail_scale_scan,
)


MIN_PRECHANGE_BINS = DEFAULT_MIN_PRECHANGE_BINS
MIN_POSTCHANGE_BINS = DEFAULT_MIN_POSTCHANGE_BINS
FALSE_ALARM_RATE = 0.01
CALIBRATION_SAMPLES = 8192
VALIDATION_SAMPLES = 4096


def main(
    data_dir: Path = Path("data/aftershock_population"),
    output_dir: Path = Path("artifacts"),
) -> None:
    hierarchy = json.loads(
        (output_dir / "aftershock_population_hierarchy.json").read_text(
            encoding="utf-8"
        )
    )
    specs, _ = load_population_manifest(data_dir / "manifest.json")
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    evaluation_starts = edges[:-1][evaluation_mask]
    evaluation_ends = edges[1:][evaluation_mask]
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)
    sequences = [load_sequence(spec, edges, data_dir) for spec in specs]
    full_fits = [
        fit_relaxation_model(
            "omori", edges, sequence.counts, all_mask, sequence.background
        )
        for sequence in sequences
    ]

    records = []
    for index, sequence in enumerate(sequences):
        fold = hierarchy["folds"][index]
        population = robust_population(
            full_fits, [other for other in range(len(sequences)) if other != index]
        )
        fit = fit_hierarchical_target(
            sequence,
            edges,
            calibration_mask,
            population,
            fold["selected_pooling_strength"],
        )
        expected = fit.expected_counts[evaluation_mask]
        observed = sequence.counts[evaluation_mask]
        generator = torch.Generator().manual_seed(20260717 + index)
        threshold, calibration_maxima = monte_carlo_threshold(
            expected,
            FALSE_ALARM_RATE,
            CALIBRATION_SAMPLES,
            generator,
        )
        validation_counts = torch.poisson(
            expected.expand(VALIDATION_SAMPLES, -1), generator=generator
        )
        validation_statistics, _ = tail_scale_scan(validation_counts, expected)
        validation_maxima = validation_statistics.max(dim=1).values
        empirical_false_alarm = float((validation_maxima > threshold).to(DTYPE).mean())

        statistics, splits = tail_scale_scan(observed, expected)
        alarms = torch.nonzero(statistics > threshold).flatten()
        first_alarm = int(alarms[0]) if len(alarms) else None
        if first_alarm is None:
            split_index = None
            rate_multiplier = None
            direction = None
            first_alarm_day = None
            estimated_change_day = None
        else:
            split_index = int(splits[first_alarm])
            observed_tail = observed[split_index : first_alarm + 1].sum()
            expected_tail = expected[split_index : first_alarm + 1].sum()
            rate_multiplier = float(observed_tail / expected_tail)
            direction = "higher" if rate_multiplier > 1.0 else "lower"
            first_alarm_day = float(evaluation_ends[first_alarm])
            estimated_change_day = float(evaluation_starts[split_index])
        records.append(
            {
                "event_id": sequence.spec.event_id,
                "name": sequence.spec.name,
                "population_predictive_total_miss": not fold[
                    "predictive_distribution"
                ]["total_covered"],
                "threshold": threshold,
                "calibration_maximum_p99": float(
                    torch.quantile(calibration_maxima, 0.99)
                ),
                "empirical_null_false_alarm_rate": empirical_false_alarm,
                "statistics": statistics.tolist(),
                "maximum_statistic": float(statistics.max()),
                "first_alarm_bin": first_alarm,
                "first_alarm_day": first_alarm_day,
                "estimated_change_bin": split_index,
                "estimated_change_day": estimated_change_day,
                "rate_multiplier_at_alarm": rate_multiplier,
                "direction": direction,
                "evaluation_start_days": evaluation_starts.tolist(),
                "evaluation_end_days": evaluation_ends.tolist(),
                "observed_counts": observed.tolist(),
                "expected_counts": expected.tolist(),
            }
        )

    misses = [record for record in records if record["population_predictive_total_miss"]]
    covered = [
        record for record in records if not record["population_predictive_total_miss"]
    ]
    summary = {
        "experiment": "Monte Carlo calibrated sequential Poisson tail-regime monitor",
        "null": "fixed hierarchical expected bin counts with independent Poisson noise",
        "false_alarm_rate": FALSE_ALARM_RATE,
        "calibration_samples": CALIBRATION_SAMPLES,
        "validation_samples": VALIDATION_SAMPLES,
        "minimum_prechange_bins": MIN_PRECHANGE_BINS,
        "minimum_postchange_bins": MIN_POSTCHANGE_BINS,
        "sequence_count": len(records),
        "alarmed_sequences": sum(record["first_alarm_bin"] is not None for record in records),
        "predictive_total_misses_alarmed": sum(
            record["first_alarm_bin"] is not None for record in misses
        ),
        "predictive_total_miss_count": len(misses),
        "covered_totals_alarmed": sum(
            record["first_alarm_bin"] is not None for record in covered
        ),
        "covered_total_count": len(covered),
        "mean_empirical_null_false_alarm_rate": sum(
            record["empirical_null_false_alarm_rate"] for record in records
        )
        / len(records),
        "records": records,
    }
    result_path = output_dir / "sequential_regime_analysis.json"
    result_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    trace_axis, ratio_axis, count_axis, calibration_axis = axes.ravel()
    for record in records:
        normalized = torch.tensor(record["statistics"]) / record["threshold"]
        color = "#d63031" if record["first_alarm_bin"] is not None else "#636e72"
        alpha = 0.9 if record["first_alarm_bin"] is not None else 0.45
        trace_axis.plot(
            record["evaluation_end_days"],
            normalized,
            color=color,
            alpha=alpha,
            linewidth=1.3,
        )
    trace_axis.axhline(1.0, color="black", linestyle="--", label="calibrated threshold")
    trace_axis.set_xscale("log")
    trace_axis.set(
        title="Sequential scan statistic",
        xlabel="day after mainshock (log scale)",
        ylabel="statistic / family-wise threshold",
    )
    trace_axis.legend(frameon=False)
    trace_axis.grid(alpha=0.2)

    alarmed = [record for record in records if record["first_alarm_bin"] is not None]
    aliases = {
        "ci14607652": "El Mayor",
        "ci38457511": "Ridgecrest",
        "us70008jr5": "Stanley",
        "nn00725272": "Monte Cristo",
        "us6000ga9w": "Oregon",
        "nc73821036": "Ferndale",
    }
    annotation_offsets = {
        "ci38457511": (4, 8),
        "nn00725272": (4, -12),
    }
    for record in alarmed:
        ratio_axis.scatter(
            record["first_alarm_day"],
            record["rate_multiplier_at_alarm"],
            s=65,
            color=(
                "#d63031"
                if record["population_predictive_total_miss"]
                else "#0984e3"
            ),
        )
        ratio_axis.annotate(
            aliases.get(record["event_id"], record["event_id"]),
            (record["first_alarm_day"], record["rate_multiplier_at_alarm"]),
            fontsize=7,
            xytext=annotation_offsets.get(record["event_id"], (3, 3)),
            textcoords="offset points",
        )
    ratio_axis.axhline(1.0, color="black", linestyle="--")
    ratio_axis.set_yscale("log")
    ratio_axis.set(
        title="State when the first alarm becomes defensible",
        xlabel="first alarm day",
        ylabel="observed / expected tail rate (log scale)",
    )
    ratio_axis.grid(alpha=0.2)

    groups = (misses, covered)
    alarm_counts = [
        sum(record["first_alarm_bin"] is not None for record in group)
        for group in groups
    ]
    quiet_counts = [len(group) - alarms for group, alarms in zip(groups, alarm_counts)]
    count_axis.bar((0, 1), alarm_counts, label="alarm", color="#d63031")
    count_axis.bar(
        (0, 1), quiet_counts, bottom=alarm_counts, label="no alarm", color="#b2bec3"
    )
    count_axis.set_xticks((0, 1), ("predictive total\nmiss", "predictive total\ncovered"))
    count_axis.set(
        title="Alarm outcomes at 1% fixed-null family-wise error",
        ylabel="sequence count",
    )
    count_axis.legend(frameon=False)
    count_axis.grid(axis="y", alpha=0.2)

    empirical = [record["empirical_null_false_alarm_rate"] for record in records]
    calibration_axis.scatter(range(len(records)), empirical, color="#00b894")
    calibration_axis.axhline(
        FALSE_ALARM_RATE, color="black", linestyle="--", label="nominal 1%"
    )
    calibration_axis.set_xticks(
        range(len(records)), [record["event_id"] for record in records], rotation=40, ha="right"
    )
    calibration_axis.set(
        title="Independent Monte Carlo null validation",
        ylabel="empirical probability of any alarm",
    )
    calibration_axis.legend(frameon=False)
    calibration_axis.grid(axis="y", alpha=0.2)
    fig.suptitle("Sequentially admitting when an aftershock forecast has changed regime")
    figure_path = output_dir / "sequential_regime_lab.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2))
    print(f"Wrote {result_path} and {figure_path}")


if __name__ == "__main__":
    main()
