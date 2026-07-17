"""Separate magnitude-time coupling from reporting-provenance composition."""

from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from magnitude_time_coupling_lab import (
    BASE_FLOOR,
    COHORTS,
    EARLY_END_DAYS,
    EARLY_START_DAYS,
    INVALID_EVENT_IDS,
    LATE_END_DAYS,
    PERMUTATION_SAMPLES,
    THRESHOLDS,
    conditional_exchangeability_test,
    sequence_mark_summary,
)


SCHEMES = (
    "sequence",
    "sequence_network",
    "sequence_magnitude_type",
    "sequence_network_magnitude_type",
)
OUTPUT = Path("artifacts/magnitude_provenance_stratification.json")
PLOT = Path("artifacts/magnitude_provenance_stratification.png")


def load_provenance_events(root: Path, record: dict) -> list[dict]:
    rows = list(
        csv.DictReader(
            (root / f"{record['slug']}.csv").read_text(encoding="utf-8").splitlines()
        )
    )
    origin = datetime.fromisoformat(record["time"].replace("Z", "+00:00"))
    events = []
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
        events.append(
            {
                "event_id": record["event_id"],
                "name": record["name"],
                "time_days": days,
                "magnitude": magnitude,
                "network": row.get("net") or "unknown",
                "magnitude_type": row.get("magType") or "unknown",
            }
        )
    return events


def stratum_key(event: dict, scheme: str) -> tuple[str, ...]:
    if scheme == "sequence":
        return (event["event_id"],)
    if scheme == "sequence_network":
        return event["event_id"], event["network"]
    if scheme == "sequence_magnitude_type":
        return event["event_id"], event["magnitude_type"]
    if scheme == "sequence_network_magnitude_type":
        return event["event_id"], event["network"], event["magnitude_type"]
    raise ValueError(f"unknown stratification scheme: {scheme}")


def build_stratum_summaries(
    events: list[dict], threshold: float, scheme: str
) -> list[dict]:
    grouped: dict[tuple[str, ...], list[dict]] = defaultdict(list)
    for event in events:
        grouped[stratum_key(event, scheme)].append(event)
    summaries = []
    for key in sorted(grouped):
        group = grouped[key]
        parent_id = group[0]["event_id"]
        label = "|".join(key)
        summary = sequence_mark_summary(
            label,
            group[0]["name"],
            [event["time_days"] for event in group],
            [event["magnitude"] for event in group],
            threshold,
        )
        summaries.append(
            {
                **summary,
                "parent_event_id": parent_id,
                "network": group[0]["network"] if "network" in scheme else None,
                "magnitude_type": (
                    group[0]["magnitude_type"]
                    if "magnitude_type" in scheme
                    else None
                ),
            }
        )
    return summaries


def summarize_scheme(
    events: list[dict],
    threshold: float,
    scheme: str,
    samples: int,
    seed: int,
) -> dict:
    summaries = build_stratum_summaries(events, threshold, scheme)
    test = conditional_exchangeability_test(summaries, samples=samples, seed=seed)
    eligible = [item for item in summaries if item["eligible_for_conditional_test"]]
    eligible_events = sum(item["early_total"] + item["late_total"] for item in eligible)
    total_events = sum(item["early_total"] + item["late_total"] for item in summaries)
    early_excess = sum(
        item["early_high"] - item["expected_early_high_under_exchangeability"]
        for item in eligible
    )
    return {
        "scheme": scheme,
        "stratum_count": len(summaries),
        "eligible_stratum_count": len(eligible),
        "eligible_parent_sequence_count": len(
            {item["parent_event_id"] for item in eligible}
        ),
        "eligible_event_count": eligible_events,
        "total_event_count": total_events,
        "eligible_event_fraction": eligible_events / total_events,
        "observed_early_high_excess": early_excess,
        "test": test,
        "strata": summaries,
    }


def total_variation(first: Counter, second: Counter) -> float:
    first_total = sum(first.values())
    second_total = sum(second.values())
    if first_total == 0 or second_total == 0:
        raise ValueError("both compositions must be nonempty")
    keys = set(first) | set(second)
    return 0.5 * sum(
        abs(first[key] / first_total - second[key] / second_total) for key in keys
    )


def provenance_composition(events: list[dict], field: str) -> dict:
    if field not in {"network", "magnitude_type"}:
        raise ValueError("field must be network or magnitude_type")
    early = Counter(
        event[field] for event in events if event["time_days"] <= EARLY_END_DAYS
    )
    late = Counter(
        event[field] for event in events if event["time_days"] > EARLY_END_DAYS
    )
    categories = sorted(set(early) | set(late), key=lambda key: (-(early[key] + late[key]), key))
    return {
        "field": field,
        "early_total": sum(early.values()),
        "late_total": sum(late.values()),
        "early_counts": dict(early.most_common()),
        "late_counts": dict(late.most_common()),
        "total_variation_distance": total_variation(early, late),
        "categories": [
            {
                "value": category,
                "early_fraction": early[category] / sum(early.values()),
                "late_fraction": late[category] / sum(late.values()),
                "early_count": early[category],
                "late_count": late[category],
            }
            for category in categories
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
    events = [
        event
        for record in records
        for event in load_provenance_events(root, record)
    ]
    threshold_reports = []
    for threshold_position, threshold in enumerate(thresholds):
        scheme_reports = []
        for scheme_position, scheme in enumerate(SCHEMES):
            scheme_reports.append(
                summarize_scheme(
                    events,
                    threshold,
                    scheme,
                    samples,
                    seed_base + 10000 * threshold_position + 1000 * scheme_position,
                )
            )
        threshold_reports.append(
            {"threshold": threshold, "schemes": scheme_reports}
        )
    return {
        "cohort": label,
        "selected_sequence_count": len(records),
        "event_count": len(events),
        "excluded_event_ids": sorted(excluded),
        "network_composition": provenance_composition(events, "network"),
        "magnitude_type_composition": provenance_composition(events, "magnitude_type"),
        "threshold_reports": threshold_reports,
    }


def run_provenance_stratification(
    cohorts: dict[str, Path] = COHORTS,
    thresholds: tuple[float, ...] = THRESHOLDS,
    samples: int = PERMUTATION_SAMPLES,
    seed_base: int = 2026071700,
) -> dict:
    cohort_reports = {}
    for position, (label, root) in enumerate(cohorts.items()):
        cohort_reports[label] = summarize_cohort(
            label,
            root,
            thresholds,
            samples,
            seed_base + 1000000 * position,
        )
    return {
        "experiment": "reporting-provenance stratification of magnitude-time coupling",
        "claim_boundary": (
            "retrospective conditional diagnostic; network and magnitude-type fields "
            "are reporting provenance, not calibrated sensor or physical covariates"
        ),
        "base_reported_magnitude_floor": BASE_FLOOR,
        "tested_high_magnitude_thresholds": list(thresholds),
        "stratification_schemes": list(SCHEMES),
        "permutation_samples": samples,
        "cohorts": cohort_reports,
    }


def plot_provenance_stratification(report: dict, output_path: Path = PLOT) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    fig.patch.set_facecolor("white")
    western_axis, alaska_axis, coverage_axis, composition_axis = axes.ravel()
    scheme_labels = {
        "sequence": "sequence only",
        "sequence_network": "+ network",
        "sequence_magnitude_type": "+ magnitude type",
        "sequence_network_magnitude_type": "+ both",
    }
    scheme_colors = {
        "sequence": "#2d3436",
        "sequence_network": "#0984e3",
        "sequence_magnitude_type": "#e17055",
        "sequence_network_magnitude_type": "#6c5ce7",
    }
    for axis, label in (
        (western_axis, "western_development"),
        (alaska_axis, "alaska_external"),
    ):
        cohort = report["cohorts"][label]
        for scheme in SCHEMES:
            values = []
            thresholds = []
            for threshold_report in cohort["threshold_reports"]:
                scheme_report = next(
                    item for item in threshold_report["schemes"] if item["scheme"] == scheme
                )
                thresholds.append(threshold_report["threshold"])
                values.append(scheme_report["test"]["observed_early_enrichment_z"])
            axis.plot(
                thresholds,
                values,
                "o-",
                color=scheme_colors[scheme],
                label=scheme_labels[scheme],
            )
        axis.axhline(0, color="#636e72", linewidth=1)
        axis.set(
            title=label.replace("_", " "),
            xlabel="high-magnitude threshold",
            ylabel="conditional early-enrichment z",
        )
        axis.grid(alpha=0.2)
        axis.legend(fontsize=8)

    plot_thresholds = report["tested_high_magnitude_thresholds"]
    x = np.arange(len(plot_thresholds))
    width = 0.18
    alaska = report["cohorts"]["alaska_external"]
    for position, scheme in enumerate(SCHEMES):
        fractions = []
        for threshold_report in alaska["threshold_reports"]:
            scheme_report = next(
                item for item in threshold_report["schemes"] if item["scheme"] == scheme
            )
            fractions.append(scheme_report["eligible_event_fraction"])
        coverage_axis.bar(
            x + (position - 1.5) * width,
            fractions,
            width,
            color=scheme_colors[scheme],
            label=scheme_labels[scheme],
        )
    coverage_axis.set_xticks(x, [f"M{threshold:g}" for threshold in plot_thresholds])
    coverage_axis.set(
        title="Alaska information retained after stratification",
        ylabel="fraction of events in informative strata",
        ylim=(0, 1.05),
    )
    coverage_axis.legend(fontsize=8)
    coverage_axis.grid(alpha=0.2, axis="y")

    magnitude_types = alaska["magnitude_type_composition"]["categories"][:6]
    labels = [item["value"] for item in magnitude_types]
    early = [item["early_fraction"] for item in magnitude_types]
    late = [item["late_fraction"] for item in magnitude_types]
    y = np.arange(len(labels))
    composition_axis.barh(y - 0.18, early, 0.36, label="first day", color="#d63031")
    composition_axis.barh(y + 0.18, late, 0.36, label="days 1–30", color="#00b894")
    composition_axis.set_yticks(y, labels)
    composition_axis.invert_yaxis()
    composition_axis.set(
        title=(
            "Alaska magnitude-type composition "
            f"(TV={alaska['magnitude_type_composition']['total_variation_distance']:.3f})"
        ),
        xlabel="fraction of forecast-window events",
    )
    composition_axis.legend(fontsize=8)
    composition_axis.grid(alpha=0.2, axis="x")

    fig.suptitle("Does reporting provenance explain magnitude–time coupling?")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(output_path: Path = OUTPUT, plot_path: Path = PLOT) -> None:
    report = run_provenance_stratification()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    plot_provenance_stratification(report, plot_path)
    for label, cohort in report["cohorts"].items():
        for threshold_report in cohort["threshold_reports"]:
            values = ", ".join(
                f"{item['scheme']} z={item['test']['observed_early_enrichment_z']:.2f}"
                for item in threshold_report["schemes"]
            )
            print(f"{label} M{threshold_report['threshold']:g}: {values}")


if __name__ == "__main__":
    main()
