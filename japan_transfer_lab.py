"""Test the frozen western aftershock workflow on a second geography."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aftershock_hierarchy_lab import (
    _sample_predictive_distribution,
    choose_pooling_strength,
    fit_hierarchical_target,
    robust_population,
)
from aftershock_lab import DTYPE, fit_relaxation_model, poisson_deviance
from aftershock_meta_lab import expected_from_shape, load_population_manifest
from aftershock_transfer_lab import CALIBRATION_END_DAYS, load_sequence, make_transfer_bins
from external_aftershock_lab import aggregate_folds
from external_sequential_monitor_lab import first_alarm_record
from full_predictive_stability_lab import outcome_summary
from predictive_sequential_monitor_lab import (
    CALIBRATION_SAMPLES,
    PROPOSAL_COUNT,
    sample_population_predictive_counts,
    threshold_from_predictive_streams,
)


DEVELOPMENT_DIR = Path("data/aftershock_population")
JAPAN_DIR = Path("data/aftershock_external/japan_kuril_2016_2025")
REPEATS = 4
SEED_BASE = 2026073100


def summarize_transfer(folds: list[dict]) -> dict:
    """Summarize the frozen point forecasts, intervals, and consensus alarm."""
    targets = [
        {
            "event_id": fold["event_id"],
            "repeat_alarm_count": fold["repeat_alarm_count"],
            "repeat_count": fold["repeat_count"],
            "original_alarm": False,
            "raw_interval_miss": fold["raw_interval_miss"],
        }
        for fold in folds
    ]
    frequency_counts = {
        str(count): sum(fold["repeat_alarm_count"] == count for fold in folds)
        for count in range(REPEATS + 1)
    }
    threshold_cvs = [fold["threshold_coefficient_of_variation"] for fold in folds]
    return {
        "sequence_count": len(folds),
        "raw_total_intervals_covered": sum(
            not fold["raw_interval_miss"] for fold in folds
        ),
        "raw_total_interval_coverage": sum(
            not fold["raw_interval_miss"] for fold in folds
        )
        / len(folds),
        "mean_bin_coverage": statistics.mean(
            fold["predictive_distribution"]["bin_coverage"] for fold in folds
        ),
        "repeat_alarm_frequency_counts": frequency_counts,
        "unanimous_against_raw_intervals": outcome_summary(
            targets, "raw_interval_miss", "unanimous"
        ),
        "any_repeat_against_raw_intervals": outcome_summary(
            targets, "raw_interval_miss", "any_repeat"
        ),
        "median_threshold_cv": statistics.median(threshold_cvs),
        "maximum_threshold_cv": max(threshold_cvs),
    }


def run_japan_transfer(
    development_dir: Path = DEVELOPMENT_DIR,
    japan_dir: Path = JAPAN_DIR,
    repeats: int = REPEATS,
    seed_base: int = SEED_BASE,
) -> dict:
    if repeats != REPEATS:
        raise ValueError("the transferred consensus protocol requires four repeats")

    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    evaluation_starts = edges[:-1][evaluation_mask]
    evaluation_ends = edges[1:][evaluation_mask]
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)

    development_specs, development_records = load_population_manifest(
        development_dir / "manifest.json"
    )
    development_sequences = [
        load_sequence(spec, edges, development_dir) for spec in development_specs
    ]
    development_fits = [
        fit_relaxation_model("omori", edges, sequence.counts, all_mask, sequence.background)
        for sequence in development_sequences
    ]
    indices = list(range(len(development_sequences)))
    population = robust_population(development_fits, indices)
    pooling_strength, inner_scores = choose_pooling_strength(
        indices,
        development_sequences,
        development_fits,
        edges,
        calibration_mask,
        evaluation_mask,
    )

    japan_specs, japan_records = load_population_manifest(japan_dir / "manifest.json")
    record_by_id = {record["event_id"]: record for record in japan_records}
    folds = []
    batches = []
    for target_index, spec in enumerate(japan_specs):
        sequence = load_sequence(spec, edges, japan_dir)
        hierarchy = fit_hierarchical_target(
            sequence, edges, calibration_mask, population, pooling_strength
        )
        pooled_expected, pooled_parameters = expected_from_shape(
            sequence, population.center, edges, calibration_mask
        )
        local = fit_relaxation_model(
            "omori", edges, sequence.counts, calibration_mask, sequence.background
        )
        predictive = _sample_predictive_distribution(
            sequence,
            edges,
            calibration_mask,
            evaluation_mask,
            population,
            seed=202607310 + target_index,
        )
        expected = hierarchy.expected_counts[evaluation_mask]
        observed = sequence.counts[evaluation_mask]
        repeat_records = []
        for repeat in range(repeats):
            seed = seed_base + 100 * target_index + repeat
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
            threshold, _, rank = threshold_from_predictive_streams(counts, expected)
            alarm = first_alarm_record(
                observed, expected, threshold, evaluation_starts, evaluation_ends
            )
            batch = {
                "event_id": spec.event_id,
                "repeat": repeat,
                "seed": seed,
                "threshold": threshold,
                "threshold_rank": rank,
                "proposal_effective_sample_size": effective_size,
                "alarm": alarm["first_alarm_bin"] is not None,
                "first_alarm_day": alarm["first_alarm_day"],
                "direction": alarm["direction"],
                "maximum_threshold_ratio": alarm["maximum_threshold_ratio"],
            }
            repeat_records.append(batch)
            batches.append(batch)

        thresholds = [batch["threshold"] for batch in repeat_records]
        threshold_mean = statistics.mean(thresholds)
        models = {}
        for name, model_expected, parameters in (
            ("frozen_hierarchy", hierarchy.expected_counts, hierarchy.parameters),
            ("robust_pool", pooled_expected, pooled_parameters),
            ("target_day1", local.expected_counts, local.parameters),
        ):
            models[name] = {
                "parameters": parameters,
                "poisson_deviance": poisson_deviance(
                    model_expected[evaluation_mask], observed
                ),
                "predicted_total": float(model_expected[evaluation_mask].sum()),
            }
        source = record_by_id[spec.event_id]
        folds.append(
            {
                "event_id": spec.event_id,
                "target": spec.slug,
                "name": spec.name,
                "time": source["time"],
                "magnitude": source["magnitude"],
                "depth_km": source["depth_km"],
                "calibration_events": int(sequence.counts[calibration_mask].sum()),
                "evaluation_events": int(observed.sum()),
                "models": models,
                "predictive_distribution": predictive,
                "raw_interval_miss": not bool(predictive["total_covered"]),
                "repeat_count": repeats,
                "repeat_alarm_count": sum(batch["alarm"] for batch in repeat_records),
                "repeat_alarm_fraction": sum(
                    batch["alarm"] for batch in repeat_records
                )
                / repeats,
                "unanimous_alarm": all(batch["alarm"] for batch in repeat_records),
                "threshold_minimum": min(thresholds),
                "threshold_median": statistics.median(thresholds),
                "threshold_maximum": max(thresholds),
                "threshold_coefficient_of_variation": (
                    statistics.pstdev(thresholds) / threshold_mean
                ),
                "proposal_ess_median": statistics.median(
                    batch["proposal_effective_sample_size"] for batch in repeat_records
                ),
            }
        )

    manifest = json.loads((japan_dir / "manifest.json").read_text(encoding="utf-8"))
    report = {
        "experiment": "frozen western aftershock workflow on Japan/Kuril cohort",
        "claim_boundary": (
            "retrospective second-geography transfer test; cohort bounds and selection "
            "rules were frozen before download, while no operational or prospective "
            "earthquake-warning claim is made"
        ),
        "development_population": {
            "cohort": "western North America 2010-2025",
            "sequence_count": len(development_specs),
            "event_ids": [record["event_id"] for record in development_records],
            "selected_pooling_strength": pooling_strength,
            "inner_median_deviance": inner_scores,
        },
        "external_screen": {
            "cohort": manifest["cohort"],
            "candidate_sha256": manifest["candidate_sha256"],
            "candidate_count": manifest["candidate_count"],
            "independent_candidate_count": manifest["independent_candidate_count"],
            "selected_count": manifest["selected_count"],
        },
        "protocol": {
            "population_and_pooling": "western development cohort only",
            "target_calibration": "hour 1 through day 1 only",
            "target_evaluation": "day 1 through day 30",
            "target_future_used_for_model_fit_or_threshold": False,
            "predictive_null_calibrations_per_target": repeats,
            "primary_alarm_rule": "unanimous across all four fresh calibrations",
            "primary_outcome": "miss of raw central 80% predictive total interval",
        },
        "aggregate": aggregate_folds(folds),
        "summary": summarize_transfer(folds),
        "folds": folds,
        "batches": batches,
    }
    return report


def plot_japan_transfer(report: dict, output_path: Path) -> None:
    folds = report["folds"]
    labels = [f"{fold['time'][:4]} {fold['event_id']}" for fold in folds]
    hierarchy = [fold["models"]["frozen_hierarchy"]["poisson_deviance"] for fold in folds]
    comparator = [
        min(
            fold["models"]["robust_pool"]["poisson_deviance"],
            fold["models"]["target_day1"]["poisson_deviance"],
        )
        for fold in folds
    ]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    score_axis, total_axis, alarm_axis, variability_axis = axes.ravel()

    maximum = 1.15 * max(hierarchy + comparator)
    minimum = 0.8 * min(hierarchy + comparator)
    score_axis.loglog(comparator, hierarchy, "o", color="#6c5ce7")
    score_axis.plot([minimum, maximum], [minimum, maximum], ":", color="#2d3436")
    score_axis.set(
        xlabel="better simple-comparator deviance",
        ylabel="frozen hierarchy deviance",
        title="Point-forecast transfer",
    )
    score_axis.grid(alpha=0.2, which="both")

    observed = [fold["evaluation_events"] for fold in folds]
    median = [fold["predictive_distribution"]["total_median"] for fold in folds]
    lower = [fold["predictive_distribution"]["total_p10"] for fold in folds]
    upper = [fold["predictive_distribution"]["total_p90"] for fold in folds]
    total_axis.errorbar(
        observed,
        median,
        yerr=([m - lo for m, lo in zip(median, lower)], [hi - m for m, hi in zip(median, upper)]),
        fmt="o",
        color="#0984e3",
        capsize=3,
    )
    total_max = 1.15 * max(observed + upper)
    total_axis.plot([10, total_max], [10, total_max], ":", color="#2d3436")
    total_axis.set_xscale("log")
    total_axis.set_yscale("log")
    total_axis.set(
        xlabel="observed day-1-to-30 total",
        ylabel="predictive median and central 80%",
        title="Raw predictive totals",
    )
    total_axis.grid(alpha=0.2, which="both")

    alarm_axis.bar(
        range(len(folds)),
        [fold["repeat_alarm_fraction"] for fold in folds],
        color=["#d63031" if fold["raw_interval_miss"] else "#0984e3" for fold in folds],
    )
    alarm_axis.set_xticks(range(len(folds)), labels, rotation=60, ha="right", fontsize=7)
    alarm_axis.set(
        title="Transferred predictive-null consensus",
        ylabel="alarm fraction across four batches",
        ylim=(0, 1.05),
    )
    alarm_axis.grid(axis="y", alpha=0.2)

    variability_axis.scatter(
        [fold["proposal_ess_median"] for fold in folds],
        [100 * fold["threshold_coefficient_of_variation"] for fold in folds],
        c=[fold["repeat_alarm_fraction"] for fold in folds],
        cmap="magma",
        vmin=0,
        vmax=1,
        s=55,
    )
    for fold in folds:
        variability_axis.annotate(
            fold["event_id"],
            (fold["proposal_ess_median"], 100 * fold["threshold_coefficient_of_variation"]),
            fontsize=7,
            xytext=(3, 3),
            textcoords="offset points",
        )
    variability_axis.set(
        xlabel="median proposal effective sample size",
        ylabel="threshold CV (%)",
        title="Sampler stability in the new domain",
    )
    variability_axis.grid(alpha=0.2)

    fig.suptitle("Second-geography transfer: Japan and the Kuril margin")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_japan_transfer()
    (output_dir / "japan_transfer.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_japan_transfer(report, output_dir / "japan_transfer.png")
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["aggregate"], indent=2))
    for fold in report["folds"]:
        print(
            fold["event_id"],
            f"alarms={fold['repeat_alarm_count']}/4",
            f"raw_miss={fold['raw_interval_miss']}",
            f"observed={fold['evaluation_events']}",
            f"median={fold['predictive_distribution']['total_median']:.1f}",
        )


if __name__ == "__main__":
    main()
