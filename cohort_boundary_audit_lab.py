"""Apply the boundary-free isolation audit to foundational cohorts."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from audit_japan_cohort_isolation import audit_isolation


COHORT_MANIFESTS = {
    "western_development": Path("data/aftershock_population/manifest.json"),
    "alaska_external": Path(
        "data/aftershock_external/alaska_2010_2025/manifest.json"
    ),
}
OUTPUT = Path("artifacts/cohort_boundary_audit.json")
PLOT = Path("artifacts/cohort_boundary_audit.png")


def summarize_audits(audits: dict[str, dict]) -> dict:
    selected = sum(audit["summary"]["selected_targets"] for audit in audits.values())
    failures = [
        {"cohort": cohort, **record}
        for cohort, audit in audits.items()
        for record in audit["records"]
        if not record["passes_boundary_free_priority"]
    ]
    return {
        "cohort_count": len(audits),
        "selected_targets": selected,
        "passes_boundary_free_priority": selected - len(failures),
        "fails_boundary_free_priority": len(failures),
        "failure_fraction": len(failures) / selected,
        "failures_by_cohort": {
            cohort: audit["summary"]["fails_boundary_free_priority"]
            for cohort, audit in audits.items()
        },
        "failed_targets": [
            {
                "cohort": failure["cohort"],
                "event_id": failure["event_id"],
                "neighbor_event_id": failure["higher_priority_neighbor"]["event_id"],
                "neighbor_inside_original_rectangle": failure[
                    "higher_priority_neighbor"
                ]["inside_original_rectangle"],
                "neighbor_inside_target_catalog_radius": failure[
                    "higher_priority_neighbor"
                ]["inside_target_catalog_radius"],
            }
            for failure in failures
        ],
    }


def run_boundary_audits(
    manifests: dict[str, Path] = COHORT_MANIFESTS,
) -> dict:
    audits = {}
    for label, path in manifests.items():
        print(f"Auditing {label}: {path}")
        audits[label] = audit_isolation(path)
    return {
        "experiment": "boundary-free isolation audit of foundational aftershock cohorts",
        "claim_boundary": (
            "post-selection protocol audit using current USGS representations; "
            "diagnoses cohort construction without retroactively freezing replacements"
        ),
        "policy": {
            "radius_km": 150,
            "window_days_before_and_after": 45,
            "minimum_magnitude": 5.8,
            "priority": "larger magnitude, then earlier origin",
            "rectangle_clipping": False,
        },
        "summary": summarize_audits(audits),
        "audits": audits,
    }


def plot_boundary_audits(report: dict, output_path: Path = PLOT) -> None:
    audits = report["audits"]
    labels = list(audits)
    selected = [audits[label]["summary"]["selected_targets"] for label in labels]
    failures = [
        audits[label]["summary"]["fails_boundary_free_priority"] for label in labels
    ]
    passes = [total - failed for total, failed in zip(selected, failures)]

    fig, (count_axis, map_axis) = plt.subplots(
        1, 2, figsize=(13, 5.5), constrained_layout=True
    )
    fig.patch.set_facecolor("white")
    count_axis.bar(labels, passes, color="#0984e3", label="passes")
    count_axis.bar(labels, failures, bottom=passes, color="#d63031", label="fails")
    count_axis.set(title="Boundary-free isolation results", ylabel="selected sequences")
    count_axis.legend(frameon=False)
    count_axis.grid(axis="y", alpha=0.2)

    colors = {"western_development": "#6c5ce7", "alaska_external": "#00b894"}
    for label, audit in audits.items():
        for record in audit["records"]:
            map_axis.scatter(
                record["longitude"],
                record["latitude"],
                color="#d63031" if not record["passes_boundary_free_priority"] else colors[label],
                marker="x" if not record["passes_boundary_free_priority"] else "o",
                s=65 if not record["passes_boundary_free_priority"] else 30,
                alpha=0.9 if not record["passes_boundary_free_priority"] else 0.65,
            )
    for label, color in colors.items():
        map_axis.scatter([], [], color=color, label=label.replace("_", " "))
    map_axis.scatter([], [], color="#d63031", marker="x", label="fails isolation")
    map_axis.set(
        xlabel="longitude",
        ylabel="latitude",
        title="Selected target centers",
    )
    map_axis.legend(frameon=False, fontsize=8)
    map_axis.grid(alpha=0.2)
    fig.suptitle("Do rectangular cohort edges contaminate foundational populations?")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_path: Path = OUTPUT, plot_path: Path = PLOT) -> None:
    report = run_boundary_audits()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_boundary_audits(report, plot_path)
    print(json.dumps(report["summary"], indent=2))
    for failure in report["summary"]["failed_targets"]:
        print(failure)


if __name__ == "__main__":
    main()
