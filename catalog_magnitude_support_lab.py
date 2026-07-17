"""Audit reported magnitude support across earthquake cohorts."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


COHORTS = {
    "western_development": Path("data/aftershock_population"),
    "alaska_external": Path("data/aftershock_external/alaska_2010_2025"),
    "japan_kuril": Path("data/aftershock_external/japan_kuril_2016_2025"),
}
THRESHOLDS = (2.5, 3.0, 3.5, 4.0, 4.2, 4.5)
MINIMUM_CALIBRATION_EVENTS = 15
MINIMUM_EVALUATION_EVENTS = 15
OUTPUT = Path("artifacts/catalog_magnitude_support.json")
PLOT = Path("artifacts/catalog_magnitude_support.png")


def quantile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("quantile requires at least one value")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must lie in [0, 1]")
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def window_counts(
    rows: list[dict], origin: datetime, target_id: str, threshold: float
) -> tuple[int, int]:
    calibration = evaluation = 0
    for row in rows:
        if row["id"] == target_id or not row.get("mag"):
            continue
        if float(row["mag"]) < threshold:
            continue
        event_time = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        days = (event_time - origin).total_seconds() / 86400.0
        calibration += 1.0 / 24.0 <= days <= 1.0
        evaluation += 1.0 < days <= 30.0
    return calibration, evaluation


def summarize_cohort(label: str, root: Path) -> dict:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    selected = [record for record in manifest["records"] if record["selected"]]
    all_magnitudes: list[float] = []
    networks: Counter[str] = Counter()
    magnitude_types: Counter[str] = Counter()
    sequence_records = []
    for record in selected:
        rows = list(
            csv.DictReader(
                (root / f"{record['slug']}.csv").read_text(encoding="utf-8").splitlines()
            )
        )
        aftershock_rows = [
            row for row in rows if row["id"] != record["event_id"] and row.get("mag")
        ]
        magnitudes = [float(row["mag"]) for row in aftershock_rows]
        all_magnitudes.extend(magnitudes)
        networks.update(row["net"] or "unknown" for row in aftershock_rows)
        magnitude_types.update(row["magType"] or "unknown" for row in aftershock_rows)
        origin = datetime.fromisoformat(record["time"].replace("Z", "+00:00"))
        threshold_counts = {}
        for threshold in THRESHOLDS:
            calibration, evaluation = window_counts(
                rows, origin, record["event_id"], threshold
            )
            threshold_counts[str(threshold)] = {
                "calibration_events": calibration,
                "evaluation_events": evaluation,
                "eligible": (
                    calibration >= MINIMUM_CALIBRATION_EVENTS
                    and evaluation >= MINIMUM_EVALUATION_EVENTS
                ),
            }
        sequence_records.append(
            {
                "event_id": record["event_id"],
                "name": record["name"],
                "time": record["time"],
                "reported_event_count": len(magnitudes),
                "minimum_magnitude": min(magnitudes),
                "magnitude_q10": quantile(magnitudes, 0.1),
                "median_magnitude": quantile(magnitudes, 0.5),
                "magnitude_q90": quantile(magnitudes, 0.9),
                "fraction_below_m3": sum(value < 3.0 for value in magnitudes)
                / len(magnitudes),
                "fraction_m4_or_greater": sum(value >= 4.0 for value in magnitudes)
                / len(magnitudes),
                "threshold_counts": threshold_counts,
            }
        )
    dominant_network, dominant_count = networks.most_common(1)[0]
    return {
        "cohort": label,
        "selected_sequence_count": len(selected),
        "reported_aftershock_rows": len(all_magnitudes),
        "minimum_magnitude": min(all_magnitudes),
        "magnitude_q10": quantile(all_magnitudes, 0.1),
        "median_magnitude": quantile(all_magnitudes, 0.5),
        "magnitude_q90": quantile(all_magnitudes, 0.9),
        "fraction_below_m3": sum(value < 3.0 for value in all_magnitudes)
        / len(all_magnitudes),
        "fraction_m4_or_greater": sum(value >= 4.0 for value in all_magnitudes)
        / len(all_magnitudes),
        "network_counts": dict(networks.most_common()),
        "magnitude_type_counts": dict(magnitude_types.most_common()),
        "dominant_network": dominant_network,
        "dominant_network_fraction": dominant_count / len(all_magnitudes),
        "eligible_sequences_by_threshold": {
            str(threshold): sum(
                sequence["threshold_counts"][str(threshold)]["eligible"]
                for sequence in sequence_records
            )
            for threshold in THRESHOLDS
        },
        "sequences": sequence_records,
        "magnitudes": all_magnitudes,
    }


def run_magnitude_support_audit(
    cohorts: dict[str, Path] = COHORTS,
) -> dict:
    summaries = {label: summarize_cohort(label, root) for label, root in cohorts.items()}
    common_m4 = {
        label: summary["eligible_sequences_by_threshold"]["4.0"]
        for label, summary in summaries.items()
    }
    return {
        "experiment": "reported magnitude-support audit across earthquake cohorts",
        "claim_boundary": (
            "describes the downloaded USGS rows and re-applies magnitude floors; "
            "observed support is not a formal magnitude-of-completeness estimate"
        ),
        "requested_query_minimum_magnitude": 2.5,
        "minimum_count_rule": {
            "calibration_events": MINIMUM_CALIBRATION_EVENTS,
            "evaluation_events": MINIMUM_EVALUATION_EVENTS,
        },
        "thresholds": THRESHOLDS,
        "cohorts": summaries,
        "common_m4_support": {
            "eligible_sequences": common_m4,
            "western_population_sufficient_for_existing_12-sequence_hierarchy": (
                common_m4["western_development"] >= 12
            ),
            "interpretation": (
                "M4 harmonization leaves too few western development sequences "
                "to reproduce the existing population hierarchy"
            ),
        },
    }


def plot_magnitude_support(report: dict, output_path: Path = PLOT) -> None:
    cohorts = report["cohorts"]
    colors = {
        "western_development": "#6c5ce7",
        "alaska_external": "#00b894",
        "japan_kuril": "#d63031",
    }
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    ecdf_axis, eligibility_axis, sequence_axis, network_axis = axes.ravel()

    for label, cohort in cohorts.items():
        values = sorted(cohort["magnitudes"])
        ecdf_axis.plot(
            values,
            [(index + 1) / len(values) for index in range(len(values))],
            color=colors[label],
            label=label.replace("_", " "),
        )
    ecdf_axis.axvline(2.5, color="#2d3436", linestyle="--", label="requested M2.5")
    ecdf_axis.set(
        title="Reported magnitude support",
        xlabel="reported magnitude",
        ylabel="empirical cumulative fraction",
        xlim=(1.8, 6.5),
    )
    ecdf_axis.legend(frameon=False, fontsize=8)
    ecdf_axis.grid(alpha=0.2)

    for label, cohort in cohorts.items():
        eligibility_axis.plot(
            THRESHOLDS,
            [cohort["eligible_sequences_by_threshold"][str(value)] for value in THRESHOLDS],
            "o-",
            color=colors[label],
            label=label.replace("_", " "),
        )
    eligibility_axis.set(
        title="Sequences retaining 15+15 events",
        xlabel="re-applied common magnitude floor",
        ylabel="eligible selected sequences",
    )
    eligibility_axis.legend(frameon=False, fontsize=8)
    eligibility_axis.grid(alpha=0.2)

    position = 0
    ticks = []
    tick_labels = []
    for label, cohort in cohorts.items():
        values = [sequence["median_magnitude"] for sequence in cohort["sequences"]]
        xs = list(range(position, position + len(values)))
        sequence_axis.scatter(xs, values, color=colors[label], alpha=0.8)
        ticks.append(position + (len(values) - 1) / 2)
        tick_labels.append(label.replace("_", "\n"))
        position += len(values) + 2
    sequence_axis.axhline(2.5, color="#2d3436", linestyle="--")
    sequence_axis.set_xticks(ticks, tick_labels)
    sequence_axis.set(
        title="Per-sequence reported median",
        ylabel="median reported magnitude",
    )
    sequence_axis.grid(axis="y", alpha=0.2)

    network_groups = ("regional_local", "us_global", "other")
    bottoms = [0.0] * len(cohorts)
    labels = list(cohorts)
    for group, color in zip(network_groups, ("#0984e3", "#e17055", "#b2bec3")):
        fractions = []
        for label in labels:
            counts = cohorts[label]["network_counts"]
            total = sum(counts.values())
            if group == "us_global":
                count = counts.get("us", 0)
            elif group == "regional_local":
                count = sum(value for key, value in counts.items() if key in {"ci", "nc", "nn", "ak", "av"})
            else:
                count = total - counts.get("us", 0) - sum(
                    value for key, value in counts.items() if key in {"ci", "nc", "nn", "ak", "av"}
                )
            fractions.append(count / total)
        network_axis.bar(labels, fractions, bottom=bottoms, color=color, label=group.replace("_", " "))
        bottoms = [bottom + value for bottom, value in zip(bottoms, fractions)]
    network_axis.set(
        title="Reporting-network composition",
        ylabel="fraction of downloaded rows",
        ylim=(0, 1),
    )
    network_axis.tick_params(axis="x", rotation=15)
    network_axis.legend(frameon=False, fontsize=8)
    network_axis.grid(axis="y", alpha=0.2)

    fig.suptitle("The Japan transfer crosses measurement systems, not only geography")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_path: Path = OUTPUT, plot_path: Path = PLOT) -> None:
    report = run_magnitude_support_audit()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_magnitude_support(report, plot_path)
    printable = {
        label: {
            key: value
            for key, value in cohort.items()
            if key not in {"sequences", "magnitudes", "network_counts", "magnitude_type_counts"}
        }
        for label, cohort in report["cohorts"].items()
    }
    print(json.dumps(printable, indent=2))
    print(json.dumps(report["common_m4_support"], indent=2))


if __name__ == "__main__":
    main()
