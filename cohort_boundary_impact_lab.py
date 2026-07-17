"""Measure how strict local-dominance filtering changes Alaska conclusions."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from external_aftershock_lab import aggregate_folds
from full_predictive_stability_lab import outcome_summary
from predictive_sequential_monitor_lab import summarize as summarize_predictive_monitor


AUDIT_EVIDENCE = Path("artifacts/cohort_boundary_audit.json")
EXTERNAL_EVIDENCE = Path("artifacts/external_aftershock_validation.json")
PREDICTIVE_EVIDENCE = Path("artifacts/predictive_sequential_monitor.json")
STABILITY_EVIDENCE = Path("artifacts/full_predictive_stability.json")
OUTPUT = Path("artifacts/cohort_boundary_impact.json")
PLOT = Path("artifacts/cohort_boundary_impact.png")
RULES = ("single_batch", "any_repeat", "majority", "unanimous")


def predictive_coverage(folds: list[dict]) -> dict:
    covered = sum(fold["predictive_distribution"]["total_covered"] for fold in folds)
    return {
        "sequence_count": len(folds),
        "covered": covered,
        "missed": len(folds) - covered,
        "coverage": covered / len(folds),
        "mean_bin_coverage": sum(
            fold["predictive_distribution"]["bin_coverage"] for fold in folds
        )
        / len(folds),
    }


def consensus_summary(targets: list[dict]) -> dict:
    return {
        "raw_intervals": {
            rule: outcome_summary(targets, "raw_interval_miss", rule)
            for rule in RULES
        },
        "rolling_intervals": {
            rule: outcome_summary(targets, "rolling_interval_miss", rule)
            for rule in RULES
        },
    }


def run_boundary_impact(
    audit_path: Path = AUDIT_EVIDENCE,
    external_path: Path = EXTERNAL_EVIDENCE,
    predictive_path: Path = PREDICTIVE_EVIDENCE,
    stability_path: Path = STABILITY_EVIDENCE,
) -> dict:
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    alaska_audit = audit["audits"]["alaska_external"]
    strict_failures = {
        record["event_id"]
        for record in alaska_audit["records"]
        if not record["passes_boundary_free_priority"]
    }
    direct_contamination = {
        record["event_id"]
        for record in alaska_audit["records"]
        if not record["passes_boundary_free_priority"]
        and record["higher_priority_neighbor"]["inside_target_catalog_radius"]
    }

    external = json.loads(external_path.read_text(encoding="utf-8"))
    predictive = json.loads(predictive_path.read_text(encoding="utf-8"))
    stability = json.loads(stability_path.read_text(encoding="utf-8"))
    original_folds = external["folds"]
    filtered_folds = [fold for fold in original_folds if fold["event_id"] not in strict_failures]
    original_predictive = predictive["records"]
    filtered_predictive = [
        record for record in original_predictive if record["event_id"] not in strict_failures
    ]
    original_targets = stability["targets"]
    filtered_targets = [
        target for target in original_targets if target["event_id"] not in strict_failures
    ]

    removed = [fold for fold in original_folds if fold["event_id"] in strict_failures]
    return {
        "experiment": "sensitivity of Alaska conclusions to strict local-dominance filtering",
        "claim_boundary": (
            "post-hoc protocol sensitivity; original greedy retained-set independence "
            "and stricter all-neighbor local dominance are both reported"
        ),
        "audit_interpretation": {
            "western_development_failures": audit["summary"]["failures_by_cohort"][
                "western_development"
            ],
            "alaska_strict_local_dominance_failures": len(strict_failures),
            "alaska_failures_inside_target_catalog_radius": len(direct_contamination),
            "strict_failure_event_ids": sorted(strict_failures),
            "direct_contamination_event_ids": sorted(direct_contamination),
        },
        "removed_targets": removed,
        "original": {
            "point_models": aggregate_folds(original_folds),
            "predictive_coverage": predictive_coverage(original_folds),
            "predictive_monitor": summarize_predictive_monitor(original_predictive),
            "consensus": consensus_summary(original_targets),
        },
        "strict_local_dominance_sensitivity": {
            "point_models": aggregate_folds(filtered_folds),
            "predictive_coverage": predictive_coverage(filtered_folds),
            "predictive_monitor": summarize_predictive_monitor(filtered_predictive),
            "consensus": consensus_summary(filtered_targets),
        },
    }


def plot_boundary_impact(report: dict, output_path: Path = PLOT) -> None:
    original = report["original"]
    filtered = report["strict_local_dominance_sensitivity"]
    models = ("frozen_hierarchy", "robust_pool", "target_day1")
    model_labels = ("hierarchy", "robust pool", "target day 1")

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    point_axis, coverage_axis, alarm_axis, rolling_axis = axes.ravel()

    x = range(len(models))
    point_axis.bar(
        [value - 0.18 for value in x],
        [original["point_models"][model]["total_poisson_deviance"] for model in models],
        width=0.36,
        color="#636e72",
        label="original 37",
    )
    point_axis.bar(
        [value + 0.18 for value in x],
        [filtered["point_models"][model]["total_poisson_deviance"] for model in models],
        width=0.36,
        color="#0984e3",
        label="strict 36",
    )
    point_axis.set_xticks(list(x), model_labels)
    point_axis.set(title="Point-score sensitivity", ylabel="total Poisson deviance")
    point_axis.legend(frameon=False)
    point_axis.grid(axis="y", alpha=0.2)

    coverage_axis.bar(
        (0, 1),
        [original["predictive_coverage"]["coverage"], filtered["predictive_coverage"]["coverage"]],
        color=["#636e72", "#0984e3"],
    )
    coverage_axis.axhline(0.8, color="#d63031", linestyle="--", label="nominal")
    coverage_axis.set_xticks((0, 1), ("original 37", "strict 36"))
    coverage_axis.set(title="Raw predictive-total coverage", ylabel="coverage", ylim=(0, 1))
    coverage_axis.legend(frameon=False)
    coverage_axis.grid(axis="y", alpha=0.2)

    raw_original = original["consensus"]["raw_intervals"]
    raw_filtered = filtered["consensus"]["raw_intervals"]
    alarm_axis.plot(
        range(len(RULES)),
        [raw_original[rule]["miss_sensitivity"] for rule in RULES],
        "o-",
        color="#636e72",
        label="original 37",
    )
    alarm_axis.plot(
        range(len(RULES)),
        [raw_filtered[rule]["miss_sensitivity"] for rule in RULES],
        "o-",
        color="#0984e3",
        label="strict 36",
    )
    alarm_axis.set_xticks(range(len(RULES)), ("single", "any", "majority", "all 4"))
    alarm_axis.set(title="Raw-miss alarm sensitivity", ylabel="miss sensitivity", ylim=(0, 0.5))
    alarm_axis.legend(frameon=False)
    alarm_axis.grid(alpha=0.2)

    rolling_original = original["consensus"]["rolling_intervals"]["unanimous"]
    rolling_filtered = filtered["consensus"]["rolling_intervals"]["unanimous"]
    rolling_axis.scatter(
        [rolling_original["retention_if_alarms_rejected"], rolling_filtered["retention_if_alarms_rejected"]],
        [rolling_original["quiet_coverage"], rolling_filtered["quiet_coverage"]],
        color=["#636e72", "#0984e3"],
        s=90,
    )
    rolling_axis.annotate("original 37", (rolling_original["retention_if_alarms_rejected"], rolling_original["quiet_coverage"]), xytext=(5, 5), textcoords="offset points")
    rolling_axis.annotate("strict 36", (rolling_filtered["retention_if_alarms_rejected"], rolling_filtered["quiet_coverage"]), xytext=(5, -14), textcoords="offset points")
    rolling_axis.axhline(0.8, color="#d63031", linestyle="--")
    rolling_axis.set(
        title="Unanimous rolling selective coverage",
        xlabel="retention",
        ylabel="quiet-set coverage",
        xlim=(0.85, 0.96),
        ylim=(0.8, 0.92),
    )
    rolling_axis.grid(alpha=0.2)

    fig.suptitle("One graph-definition failure changes denominators, not conclusions")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_path: Path = OUTPUT, plot_path: Path = PLOT) -> None:
    report = run_boundary_impact()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_boundary_impact(report, plot_path)
    print(json.dumps(report["audit_interpretation"], indent=2))
    print(json.dumps(report["strict_local_dominance_sensitivity"]["predictive_coverage"], indent=2))
    print(json.dumps(report["strict_local_dominance_sensitivity"]["predictive_monitor"], indent=2))


if __name__ == "__main__":
    main()
