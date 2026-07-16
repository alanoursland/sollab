"""Replay predictive threshold stability across all external sequences."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from predictive_threshold_stability_lab import (
    PREDICTIVE_EVIDENCE,
    run_threshold_stability,
)


FULL_REPEATS = 4
SEED_BASE = 2026073000
PANEL_STABILITY_EVIDENCE = Path("artifacts/predictive_threshold_stability.json")


def decision(target: dict, rule: str) -> bool:
    if rule == "single_batch":
        return bool(target["original_alarm"])
    alarms = int(target["repeat_alarm_count"])
    repeats = int(target["repeat_count"])
    if rule == "any_repeat":
        return alarms >= 1
    if rule == "majority":
        return alarms > repeats / 2
    if rule == "unanimous":
        return alarms == repeats
    raise ValueError("unknown consensus rule")


def outcome_summary(targets: list[dict], outcome_key: str, rule: str) -> dict:
    eligible = [target for target in targets if target[outcome_key] is not None]
    alarmed = [target for target in eligible if decision(target, rule)]
    quiet = [target for target in eligible if not decision(target, rule)]
    misses = [target for target in eligible if target[outcome_key]]
    covered = [target for target in eligible if not target[outcome_key]]
    caught = sum(target[outcome_key] for target in alarmed)
    covered_alarmed = sum(not target[outcome_key] for target in alarmed)
    return {
        "rule": rule,
        "eligible": len(eligible),
        "alarmed": len(alarmed),
        "quiet": len(quiet),
        "retention_if_alarms_rejected": len(quiet) / len(eligible),
        "miss_count": len(misses),
        "covered_count": len(covered),
        "misses_alarmed": caught,
        "covered_alarmed": covered_alarmed,
        "alarm_precision": caught / len(alarmed) if alarmed else None,
        "miss_sensitivity": caught / len(misses) if misses else None,
        "quiet_coverage": (
            sum(not target[outcome_key] for target in quiet) / len(quiet)
            if quiet
            else None
        ),
        "alarm_event_ids": [target["event_id"] for target in alarmed],
    }


def add_consensus_summaries(report: dict) -> dict:
    rules = ("single_batch", "any_repeat", "majority", "unanimous")
    report["consensus"] = {
        "raw_intervals": {
            rule: outcome_summary(report["targets"], "raw_interval_miss", rule)
            for rule in rules
        },
        "rolling_intervals": {
            rule: outcome_summary(report["targets"], "rolling_interval_miss", rule)
            for rule in rules
        },
    }
    report["summary"]["repeat_alarm_fraction_counts"] = {
        str(numerator): sum(
            target["repeat_alarm_count"] == numerator for target in report["targets"]
        )
        for numerator in range(FULL_REPEATS + 1)
    }
    return report


def add_cross_experiment_alarm_repeats(
    report: dict, panel_path: Path = PANEL_STABILITY_EVIDENCE
) -> dict:
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    panel_batches: dict[str, list[dict]] = {}
    for batch in panel["batches"]:
        panel_batches.setdefault(batch["event_id"], []).append(batch)
    combined = {}
    for target in report["targets"]:
        if not target["original_alarm"] or target["event_id"] not in panel_batches:
            continue
        prior = panel_batches[target["event_id"]]
        total_repeats = len(prior) + target["repeat_count"]
        total_alarms = sum(batch["alarm"] for batch in prior) + target[
            "repeat_alarm_count"
        ]
        combined[target["event_id"]] = {
            "panel_repeats": len(prior),
            "panel_alarms": sum(batch["alarm"] for batch in prior),
            "full_replay_repeats": target["repeat_count"],
            "full_replay_alarms": target["repeat_alarm_count"],
            "combined_repeats": total_repeats,
            "combined_alarms": total_alarms,
            "combined_alarm_fraction": total_alarms / total_repeats,
        }
    report["cross_experiment_alarm_repeats"] = combined
    return report


def run_full_stability(
    predictive_path: Path = PREDICTIVE_EVIDENCE,
) -> dict:
    predictive = json.loads(predictive_path.read_text(encoding="utf-8"))
    panel = {
        record["event_id"]: "complete external cohort"
        for record in sorted(predictive["records"], key=lambda record: record["time"])
    }
    report = run_threshold_stability(
        predictive_path=predictive_path,
        target_panel=panel,
        repeats=FULL_REPEATS,
        seed_base=SEED_BASE,
        claim_boundary=(
            "post-hoc complete 37-sequence external replay; four independent "
            "calibrations per target after report 28 defined the sampler"
        ),
    )
    report["experiment"] = (
        "complete external cohort predictive-threshold consensus replay"
    )
    return add_cross_experiment_alarm_repeats(add_consensus_summaries(report))


def plot_full_stability(report: dict, output_path: Path) -> None:
    targets = report["targets"]
    raw = report["consensus"]["raw_intervals"]
    rolling = report["consensus"]["rolling_intervals"]
    rules = ("single_batch", "any_repeat", "majority", "unanimous")
    labels = ("single batch", "any of 4", "majority", "all 4")

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    fraction_axis, raw_axis, rolling_axis, variability_axis = axes.ravel()

    ordered = sorted(
        targets,
        key=lambda target: (target["repeat_alarm_fraction"], target["event_id"]),
        reverse=True,
    )
    fraction_axis.bar(
        range(len(ordered)),
        [target["repeat_alarm_fraction"] for target in ordered],
        color=["#d63031" if target["raw_interval_miss"] else "#0984e3" for target in ordered],
    )
    fraction_axis.set_xticks(
        range(len(ordered)), [target["event_id"] for target in ordered], rotation=75, ha="right", fontsize=6
    )
    fraction_axis.set(
        title="Complete-cohort alarm frequency",
        ylabel="fraction of four fresh batches",
        ylim=(0, 1.05),
    )
    fraction_axis.bar([], [], color="#d63031", label="raw miss")
    fraction_axis.bar([], [], color="#0984e3", label="raw covered")
    fraction_axis.legend(frameon=False, fontsize=8)
    fraction_axis.grid(axis="y", alpha=0.2)

    caught = [raw[rule]["misses_alarmed"] for rule in rules]
    covered = [raw[rule]["covered_alarmed"] for rule in rules]
    raw_axis.bar(labels, caught, color="#d63031", label="raw miss")
    raw_axis.bar(labels, covered, bottom=caught, color="#0984e3", label="raw covered")
    raw_axis.set(title="Consensus alarms against raw totals", ylabel="alarmed sequences")
    raw_axis.tick_params(axis="x", rotation=20)
    raw_axis.legend(frameon=False)
    raw_axis.grid(axis="y", alpha=0.2)

    rolling_axis.scatter(
        [rolling[rule]["retention_if_alarms_rejected"] for rule in rules],
        [rolling[rule]["quiet_coverage"] for rule in rules],
        s=75,
        color=["#636e72", "#e17055", "#6c5ce7", "#00b894"],
    )
    coordinate_labels: dict[tuple[float, float], list[str]] = {}
    for rule, label in zip(rules, labels):
        coordinate = (
            rolling[rule]["retention_if_alarms_rejected"],
            rolling[rule]["quiet_coverage"],
        )
        coordinate_labels.setdefault(coordinate, []).append(label)
    for coordinate, grouped_labels in coordinate_labels.items():
        rolling_axis.annotate(
            " / ".join(grouped_labels),
            coordinate,
            xytext=(4, 4),
            textcoords="offset points",
            fontsize=8,
        )
    rolling_axis.axhline(0.8, color="#2d3436", linestyle="--")
    rolling_axis.set(
        title="Rolling selective coverage",
        xlabel="retention after rejecting alarms",
        ylabel="coverage among quiet forecasts",
    )
    rolling_axis.grid(alpha=0.2)

    for target in targets:
        variability_axis.scatter(
            target["proposal_ess_median"],
            100 * target["threshold_coefficient_of_variation"],
            color=("#d63031" if target["repeat_alarm_count"] else "#0984e3"),
            alpha=0.8,
        )
    variability_axis.scatter([], [], color="#d63031", label="alarms in >=1 repeat")
    variability_axis.scatter([], [], color="#0984e3", label="quiet in all repeats")
    variability_axis.set(
        title="Sampler variability across all targets",
        xlabel="median proposal effective sample size",
        ylabel="threshold CV (%)",
    )
    variability_axis.legend(frameon=False, fontsize=8)
    variability_axis.grid(alpha=0.2)

    fig.suptitle("Full external replay of predictive-null alarm consensus")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_full_stability()
    (output_dir / "full_predictive_stability.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_full_stability(report, output_dir / "full_predictive_stability.png")
    print(json.dumps(report["summary"], indent=2))
    print(json.dumps(report["consensus"], indent=2))


if __name__ == "__main__":
    main()
