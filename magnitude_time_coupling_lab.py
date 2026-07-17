"""Test whether reported magnitude marks are exchangeable across aftershock time."""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt


COHORTS = {
    "western_development": Path("data/aftershock_population"),
    "alaska_external": Path("data/aftershock_external/alaska_2010_2025"),
}
BASE_FLOOR = 2.5
THRESHOLDS = (3.0, 3.5, 4.0)
EARLY_START_DAYS = 1.0 / 24.0
EARLY_END_DAYS = 1.0
LATE_END_DAYS = 30.0
PERMUTATION_SAMPLES = 16384
INVALID_EVENT_IDS = {"alaska_external": {"us6000b56k"}}
ORIGINAL_ALARMS = {
    "ak01479djus2",
    "us10004x1w",
    "us2000cmy3",
    "us6000c9hg",
}
REPLACEMENT_ALARMS = {"usp000j3mq", "us200030aq"}
OUTPUT = Path("artifacts/magnitude_time_coupling.json")
PLOT = Path("artifacts/magnitude_time_coupling.png")


def load_marked_events(root: Path, record: dict) -> tuple[list[float], list[float]]:
    """Load finite M2.5+ forecast-window event times and reported magnitudes."""
    rows = list(
        csv.DictReader(
            (root / f"{record['slug']}.csv").read_text(encoding="utf-8").splitlines()
        )
    )
    origin = datetime.fromisoformat(record["time"].replace("Z", "+00:00"))
    times: list[float] = []
    magnitudes: list[float] = []
    for row in rows:
        if row["id"] == record["event_id"] or not row.get("mag"):
            continue
        magnitude = float(row["mag"])
        if not math.isfinite(magnitude) or magnitude < BASE_FLOOR:
            continue
        event_time = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        days = (event_time - origin).total_seconds() / 86400.0
        if not EARLY_START_DAYS <= days <= LATE_END_DAYS:
            continue
        times.append(days)
        magnitudes.append(magnitude)
    return times, magnitudes


def sequence_mark_summary(
    event_id: str,
    name: str,
    times: list[float],
    magnitudes: list[float],
    threshold: float,
) -> dict:
    """Summarize the exact conditional early/late mark table for one sequence."""
    if len(times) != len(magnitudes):
        raise ValueError("times and magnitudes must have equal length")
    if threshold <= BASE_FLOOR or not math.isfinite(threshold):
        raise ValueError("threshold must be finite and exceed the base floor")
    early = [index for index, time in enumerate(times) if time <= EARLY_END_DAYS]
    late = [index for index, time in enumerate(times) if time > EARLY_END_DAYS]
    early_high = sum(magnitudes[index] >= threshold for index in early)
    late_high = sum(magnitudes[index] >= threshold for index in late)
    early_total = len(early)
    late_total = len(late)
    total = early_total + late_total
    high_total = early_high + late_high
    expected_early_high = early_total * high_total / total if total else 0.0
    variance = 0.0
    if total > 1:
        high_fraction = high_total / total
        variance = (
            early_total
            * high_fraction
            * (1.0 - high_fraction)
            * (total - early_total)
            / (total - 1.0)
        )
    eligible = early_total > 0 and late_total > 0 and variance > 0.0
    deviation = early_high - expected_early_high
    z_score = deviation / math.sqrt(variance) if eligible else None
    early_fraction = early_high / early_total if early_total else None
    late_fraction = late_high / late_total if late_total else None
    early_odds = (early_high + 0.5) / (early_total - early_high + 0.5)
    late_odds = (late_high + 0.5) / (late_total - late_high + 0.5)
    return {
        "event_id": event_id,
        "name": name,
        "threshold": threshold,
        "early_total": early_total,
        "early_high": early_high,
        "late_total": late_total,
        "late_high": late_high,
        "high_total": high_total,
        "early_high_fraction": early_fraction,
        "late_high_fraction": late_fraction,
        "late_minus_early_fraction": (
            late_fraction - early_fraction
            if early_fraction is not None and late_fraction is not None
            else None
        ),
        "late_to_early_odds_ratio": late_odds / early_odds,
        "expected_early_high_under_exchangeability": expected_early_high,
        "conditional_variance": variance,
        "early_enrichment_z": z_score,
        "heterogeneity_contribution": z_score * z_score if eligible else None,
        "eligible_for_conditional_test": eligible,
    }


def conditional_exchangeability_test(
    summaries: list[dict],
    samples: int = PERMUTATION_SAMPLES,
    seed: int = 2026071600,
) -> dict:
    """Condition on every sequence's margins and randomize early high counts."""
    if samples < 1:
        raise ValueError("samples must be positive")
    eligible = [item for item in summaries if item["eligible_for_conditional_test"]]
    if not eligible:
        raise ValueError("at least one eligible sequence is required")
    observed_heterogeneity = sum(
        item["heterogeneity_contribution"] for item in eligible
    )
    observed_deviation = sum(
        item["early_high"] - item["expected_early_high_under_exchangeability"]
        for item in eligible
    )
    total_variance = sum(item["conditional_variance"] for item in eligible)
    observed_direction_z = observed_deviation / math.sqrt(total_variance)

    rng = np.random.default_rng(seed)
    simulated_heterogeneity = np.zeros(samples, dtype=float)
    simulated_deviation = np.zeros(samples, dtype=float)
    for item in eligible:
        high = item["high_total"]
        low = item["early_total"] + item["late_total"] - high
        draws = rng.hypergeometric(high, low, item["early_total"], size=samples)
        deviations = draws - item["expected_early_high_under_exchangeability"]
        simulated_heterogeneity += deviations * deviations / item["conditional_variance"]
        simulated_deviation += deviations
    simulated_direction_z = simulated_deviation / math.sqrt(total_variance)
    heterogeneity_p = (
        1 + int(np.count_nonzero(simulated_heterogeneity >= observed_heterogeneity))
    ) / (samples + 1)
    direction_p = (
        1 + int(np.count_nonzero(np.abs(simulated_direction_z) >= abs(observed_direction_z)))
    ) / (samples + 1)
    ranked = sorted(
        eligible,
        key=lambda item: (-item["heterogeneity_contribution"], item["event_id"]),
    )
    return {
        "eligible_sequence_count": len(eligible),
        "observed_heterogeneity_statistic": observed_heterogeneity,
        "heterogeneity_monte_carlo_p": heterogeneity_p,
        "observed_early_enrichment_z": observed_direction_z,
        "direction_two_sided_monte_carlo_p": direction_p,
        "direction_interpretation": (
            "higher magnitudes enriched early"
            if observed_direction_z > 0
            else "higher magnitudes enriched late"
        ),
        "permutation_samples": samples,
        "seed": seed,
        "null_heterogeneity_q95": float(np.quantile(simulated_heterogeneity, 0.95)),
        "null_heterogeneity_q99": float(np.quantile(simulated_heterogeneity, 0.99)),
        "top_contributors": [
            {
                "event_id": item["event_id"],
                "name": item["name"],
                "contribution": item["heterogeneity_contribution"],
                "early_enrichment_z": item["early_enrichment_z"],
                "late_to_early_odds_ratio": item["late_to_early_odds_ratio"],
            }
            for item in ranked[:10]
        ],
    }


def summarize_cohort(
    label: str,
    root: Path,
    thresholds: tuple[float, ...],
    samples: int,
    seed_base: int,
) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    excluded = INVALID_EVENT_IDS.get(label, set())
    records = [
        record
        for record in manifest["records"]
        if record["selected"] and record["event_id"] not in excluded
    ]
    marked = {
        record["event_id"]: load_marked_events(root, record) for record in records
    }
    threshold_reports = []
    for position, threshold in enumerate(thresholds):
        sequence_summaries = []
        for record in records:
            times, magnitudes = marked[record["event_id"]]
            sequence_summaries.append(
                sequence_mark_summary(
                    record["event_id"],
                    record["name"],
                    times,
                    magnitudes,
                    threshold,
                )
            )
        test = conditional_exchangeability_test(
            sequence_summaries,
            samples=samples,
            seed=seed_base + 1000 * position,
        )
        threshold_reports.append(
            {
                "threshold": threshold,
                "test": test,
                "sequences": sequence_summaries,
            }
        )
    return {
        "cohort": label,
        "selected_sequence_count": len(records),
        "excluded_event_ids": sorted(excluded),
        "threshold_reports": threshold_reports,
    }


def run_magnitude_time_coupling(
    cohorts: dict[str, Path] = COHORTS,
    thresholds: tuple[float, ...] = THRESHOLDS,
    samples: int = PERMUTATION_SAMPLES,
    seed_base: int = 2026071600,
) -> dict:
    reports = {}
    for position, (label, root) in enumerate(cohorts.items()):
        reports[label] = summarize_cohort(
            label,
            root,
            thresholds,
            samples,
            seed_base + 100000 * position,
        )
    return {
        "experiment": "conditional magnitude-time mark exchangeability audit",
        "claim_boundary": (
            "retrospective reported-magnitude diagnostic; conditions on each "
            "sequence's event count, early count, and high-magnitude count, but "
            "does not estimate catalog completeness or homogenize magnitude scales"
        ),
        "base_reported_magnitude_floor": BASE_FLOOR,
        "early_window_days": [EARLY_START_DAYS, EARLY_END_DAYS],
        "late_window_days": [EARLY_END_DAYS, LATE_END_DAYS],
        "tested_high_magnitude_thresholds": list(thresholds),
        "permutation_samples": samples,
        "cohorts": reports,
        "highlighted_event_ids": {
            "original_m2_5_alarm_ids": sorted(ORIGINAL_ALARMS),
            "replacement_higher_floor_alarm_ids": sorted(REPLACEMENT_ALARMS),
        },
    }


def plot_magnitude_time_coupling(report: dict, output_path: Path = PLOT) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    fig.patch.set_facecolor("white")
    fraction_axis, z_axis, global_axis, highlight_axis = axes.ravel()
    colors = {"western_development": "#0984e3", "alaska_external": "#636e72"}
    threshold = 3.0
    selected_ids = ORIGINAL_ALARMS | REPLACEMENT_ALARMS

    for label, cohort in report["cohorts"].items():
        threshold_report = next(
            item for item in cohort["threshold_reports"] if item["threshold"] == threshold
        )
        ordinary = [
            item
            for item in threshold_report["sequences"]
            if item["event_id"] not in selected_ids
        ]
        fraction_axis.scatter(
            [item["early_high_fraction"] for item in ordinary],
            [item["late_high_fraction"] for item in ordinary],
            color=colors[label],
            alpha=0.45,
            label=label.replace("_", " "),
        )
    alaska_m3 = next(
        item
        for item in report["cohorts"]["alaska_external"]["threshold_reports"]
        if item["threshold"] == threshold
    )
    by_id = {item["event_id"]: item for item in alaska_m3["sequences"]}
    for event_id in sorted(selected_ids):
        item = by_id.get(event_id)
        if item is None:
            continue
        marker = "s" if event_id in REPLACEMENT_ALARMS else "o"
        color = "#d63031" if event_id in REPLACEMENT_ALARMS else "#6c5ce7"
        fraction_axis.scatter(
            item["early_high_fraction"],
            item["late_high_fraction"],
            marker=marker,
            s=70,
            color=color,
            edgecolor="white",
            linewidth=0.7,
            zorder=5,
        )
        fraction_axis.annotate(
            event_id,
            (item["early_high_fraction"], item["late_high_fraction"]),
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=7,
        )
    fraction_axis.plot((0, 1), (0, 1), "--", color="#2d3436", linewidth=1)
    fraction_axis.set(
        title="M3 fraction: first day versus days 1–30",
        xlabel="early M3+ fraction",
        ylabel="late M3+ fraction",
        xlim=(0, 1),
        ylim=(0, 1),
    )
    fraction_axis.legend(fontsize=8)
    fraction_axis.grid(alpha=0.2)

    ordered = sorted(
        [item for item in alaska_m3["sequences"] if item["early_enrichment_z"] is not None],
        key=lambda item: item["early_enrichment_z"],
    )
    bar_colors = [
        "#d63031"
        if item["event_id"] in REPLACEMENT_ALARMS
        else "#6c5ce7"
        if item["event_id"] in ORIGINAL_ALARMS
        else "#b2bec3"
        for item in ordered
    ]
    z_axis.bar(range(len(ordered)), [item["early_enrichment_z"] for item in ordered], color=bar_colors)
    z_axis.axhline(0, color="#2d3436", linewidth=1)
    z_axis.set(
        title="Alaska conditional M3 mark timing",
        xlabel="sequences ordered by signed deviation",
        ylabel="early-enrichment z (negative = enriched late)",
    )
    z_axis.set_xticks([])
    z_axis.grid(alpha=0.2, axis="y")

    for label, cohort in report["cohorts"].items():
        thresholds = [item["threshold"] for item in cohort["threshold_reports"]]
        p_values = [
            item["test"]["heterogeneity_monte_carlo_p"]
            for item in cohort["threshold_reports"]
        ]
        global_axis.plot(
            thresholds,
            [-math.log10(value) for value in p_values],
            "o-",
            color=colors[label],
            label=label.replace("_", " "),
        )
    global_axis.axhline(-math.log10(0.05), color="#d63031", linestyle="--", linewidth=1)
    global_axis.set(
        title="Conditional mark-exchangeability test",
        xlabel="high-magnitude threshold",
        ylabel="−log10 Monte Carlo p",
    )
    global_axis.legend(fontsize=8)
    global_axis.grid(alpha=0.2)

    offsets = np.linspace(-0.18, 0.18, len(selected_ids))
    for offset, event_id in zip(offsets, sorted(selected_ids)):
        values = []
        thresholds = []
        for threshold_report in report["cohorts"]["alaska_external"]["threshold_reports"]:
            item = next(
                candidate
                for candidate in threshold_report["sequences"]
                if candidate["event_id"] == event_id
            )
            if item["early_enrichment_z"] is not None:
                thresholds.append(threshold_report["threshold"] + offset * 0.18)
                values.append(item["early_enrichment_z"])
        color = "#d63031" if event_id in REPLACEMENT_ALARMS else "#6c5ce7"
        marker = "s" if event_id in REPLACEMENT_ALARMS else "o"
        highlight_axis.plot(
            thresholds,
            values,
            marker=marker,
            color=color,
            alpha=0.75,
            label=event_id,
        )
    highlight_axis.axhline(0, color="#2d3436", linewidth=1)
    highlight_axis.set(
        title="Alarm-sequence mark timing across thresholds",
        xlabel="high-magnitude threshold",
        ylabel="early-enrichment z",
    )
    highlight_axis.legend(fontsize=7, ncol=2)
    highlight_axis.grid(alpha=0.2)

    fig.suptitle("Reported magnitude is not always an exchangeable aftershock mark")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(output_path: Path = OUTPUT, plot_path: Path = PLOT) -> None:
    report = run_magnitude_time_coupling()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    plot_magnitude_time_coupling(report, plot_path)
    for label, cohort in report["cohorts"].items():
        for threshold_report in cohort["threshold_reports"]:
            test = threshold_report["test"]
            print(
                f"{label} M{threshold_report['threshold']:g}: "
                f"heterogeneity p={test['heterogeneity_monte_carlo_p']:.6g}, "
                f"direction z={test['observed_early_enrichment_z']:.3f}, "
                f"direction p={test['direction_two_sided_monte_carlo_p']:.6g}"
            )


if __name__ == "__main__":
    main()
