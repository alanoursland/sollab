"""Falsify the frozen western aftershock hierarchy on external USGS cohorts."""

from __future__ import annotations

import json
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
from aftershock_transfer_lab import (
    CALIBRATION_END_DAYS,
    SequenceData,
    load_sequence,
    make_transfer_bins,
)


DEVELOPMENT_DATA = Path("data/aftershock_population")
EXTERNAL_ROOT = Path("data/aftershock_external")
TEMPORAL_COHORT = "temporal_2026"
GEOGRAPHIC_COHORT = "alaska_2010_2025"
MODEL_NAMES = ("frozen_hierarchy", "robust_pool", "target_day1")


def fit_frozen_target(
    sequence: SequenceData,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    population,
    pooling_strength: float,
):
    """Fit only target day-one parameters against a frozen population prior."""
    return fit_hierarchical_target(
        sequence, edges, calibration_mask, population, pooling_strength
    )


def aggregate_folds(folds: list[dict]) -> dict[str, dict[str, float | int]]:
    aggregate = {}
    for model in MODEL_NAMES:
        scores = [fold["models"][model]["poisson_deviance"] for fold in folds]
        aggregate[model] = {
            "total_poisson_deviance": sum(scores),
            "median_sequence_deviance": float(
                torch.tensor(scores, dtype=DTYPE).median()
            ),
            "sequence_wins": sum(
                score
                == min(
                    fold["models"][candidate]["poisson_deviance"]
                    for candidate in MODEL_NAMES
                )
                for score, fold in zip(scores, folds)
            ),
        }
    return aggregate


def run_external_validation(
    development_dir: Path = DEVELOPMENT_DATA,
    external_root: Path = EXTERNAL_ROOT,
) -> dict:
    temporal_manifest = json.loads(
        (external_root / TEMPORAL_COHORT / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    external_dir = external_root / GEOGRAPHIC_COHORT
    external_manifest = json.loads(
        (external_dir / "manifest.json").read_text(encoding="utf-8")
    )
    external_specs, external_records = load_population_manifest(
        external_dir / "manifest.json"
    )
    development_specs, development_records = load_population_manifest(
        development_dir / "manifest.json"
    )

    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)

    development_sequences = [
        load_sequence(spec, edges, development_dir) for spec in development_specs
    ]
    development_fits = [
        fit_relaxation_model(
            "omori", edges, sequence.counts, all_mask, sequence.background
        )
        for sequence in development_sequences
    ]
    development_indices = list(range(len(development_sequences)))
    frozen_population = robust_population(development_fits, development_indices)
    frozen_strength, development_inner_scores = choose_pooling_strength(
        development_indices,
        development_sequences,
        development_fits,
        edges,
        calibration_mask,
        evaluation_mask,
    )

    external_sequences = [
        load_sequence(spec, edges, external_dir) for spec in external_specs
    ]
    record_by_id = {record["event_id"]: record for record in external_records}
    folds = []
    for target_index, target in enumerate(external_sequences):
        hierarchy = fit_frozen_target(
            target,
            edges,
            calibration_mask,
            frozen_population,
            frozen_strength,
        )
        pooled_expected, pooled_parameters = expected_from_shape(
            target, frozen_population.center, edges, calibration_mask
        )
        local = fit_relaxation_model(
            "omori",
            edges,
            target.counts,
            calibration_mask,
            target.background,
        )
        predictive = _sample_predictive_distribution(
            target,
            edges,
            calibration_mask,
            evaluation_mask,
            frozen_population,
            seed=20260723 + target_index,
        )
        models = {}
        for name, expected, parameters in (
            ("frozen_hierarchy", hierarchy.expected_counts, hierarchy.parameters),
            ("robust_pool", pooled_expected, pooled_parameters),
            ("target_day1", local.expected_counts, local.parameters),
        ):
            models[name] = {
                "parameters": parameters,
                "poisson_deviance": poisson_deviance(
                    expected[evaluation_mask], target.counts[evaluation_mask]
                ),
                "predicted_total": float(expected[evaluation_mask].sum()),
            }
        record = record_by_id[target.spec.event_id]
        folds.append(
            {
                "event_id": target.spec.event_id,
                "target": target.spec.slug,
                "name": target.spec.name,
                "time": record["time"],
                "magnitude": record["magnitude"],
                "depth_km": record["depth_km"],
                "calibration_events": int(target.counts[calibration_mask].sum()),
                "evaluation_events": int(target.counts[evaluation_mask].sum()),
                "background_rate_per_day": target.background,
                "models": models,
                "predictive_distribution": predictive,
            }
        )

    aggregate = aggregate_folds(folds)
    coverage = {
        "total_intervals_covered": sum(
            fold["predictive_distribution"]["total_covered"] for fold in folds
        ),
        "total_intervals": len(folds),
        "mean_bin_coverage": sum(
            fold["predictive_distribution"]["bin_coverage"] for fold in folds
        )
        / len(folds),
        "nominal_interval": 0.8,
    }
    temporal_records = [
        {
            "event_id": record["event_id"],
            "name": record["name"],
            "calibration_events": record.get("calibration_events"),
            "evaluation_events": record.get("evaluation_events"),
            "selected": record["selected"],
            "rejection_reason": record["rejection_reason"],
        }
        for record in temporal_manifest["records"]
    ]
    center_c = float(torch.exp(frozen_population.center[0]))
    center_p = float(0.3 + 1.7 * torch.sigmoid(frozen_population.center[1]))
    return {
        "experiment": "frozen western hierarchy on external aftershock cohorts",
        "claim_boundary": (
            "retrospective geographic external validation; temporal 2026 cohort "
            "screened first but contained no eligible sequence"
        ),
        "development_population": {
            "cohort": "western North America 2010-2025",
            "sequence_count": len(development_specs),
            "manifest_candidate_sha256": json.loads(
                (development_dir / "manifest.json").read_text(encoding="utf-8")
            )["candidate_sha256"],
            "event_ids": [record["event_id"] for record in development_records],
            "population_c_days": center_c,
            "population_p": center_p,
            "selected_pooling_strength": frozen_strength,
            "inner_median_deviance": development_inner_scores,
        },
        "temporal_external_screen": {
            "cohort": temporal_manifest["cohort"],
            "candidate_sha256": temporal_manifest["candidate_sha256"],
            "candidate_count": temporal_manifest["candidate_count"],
            "selected_count": temporal_manifest["selected_count"],
            "records": temporal_records,
        },
        "geographic_external_screen": {
            "cohort": GEOGRAPHIC_COHORT,
            "candidate_sha256": external_manifest["candidate_sha256"],
            "candidate_count": external_manifest["candidate_count"],
            "independent_candidate_count": external_manifest[
                "independent_candidate_count"
            ],
            "selected_count": len(external_specs),
        },
        "protocol": {
            "population_and_pooling": "frozen before any Alaska target fit",
            "target_calibration": "hour 1 through day 1 only",
            "target_evaluation": "day 1 through day 30",
            "target_future_used_for_selection": False,
        },
        "aggregate": aggregate,
        "predictive_coverage": coverage,
        "folds": folds,
    }


def plot_external_validation(report: dict, output_path: Path) -> None:
    folds = report["folds"]
    labels = [f"{fold['time'][:4]} {fold['event_id']}" for fold in folds]
    hierarchy = torch.tensor(
        [fold["models"]["frozen_hierarchy"]["poisson_deviance"] for fold in folds]
    )
    robust = torch.tensor(
        [fold["models"]["robust_pool"]["poisson_deviance"] for fold in folds]
    )
    local = torch.tensor(
        [fold["models"]["target_day1"]["poisson_deviance"] for fold in folds]
    )
    baseline = torch.minimum(robust, local)
    order = torch.argsort(hierarchy - baseline)

    fig, axes = plt.subplots(2, 2, figsize=(14, 10), constrained_layout=True)
    comparison, regret_axis, totals_axis, domain_axis = axes.ravel()

    maximum = float(torch.stack((hierarchy, robust, local)).max()) * 1.15
    minimum = max(1e-1, float(torch.stack((hierarchy, robust, local)).min()) * 0.8)
    comparison.loglog(robust, hierarchy, "o", label="robust population", alpha=0.75)
    comparison.loglog(local, hierarchy, "^", label="target day 1", alpha=0.75)
    comparison.plot([minimum, maximum], [minimum, maximum], ":", color="#636e72")
    comparison.set(
        xlim=(minimum, maximum),
        ylim=(minimum, maximum),
        xlabel="comparator day-1-to-30 deviance",
        ylabel="frozen hierarchy deviance",
        title="External sequence forecast scores",
    )
    comparison.legend(frameon=False)
    comparison.grid(alpha=0.2, which="both")

    regret = hierarchy - baseline
    colors = ["#00b894" if value <= 0 else "#d63031" for value in regret[order]]
    regret_axis.barh(range(len(order)), regret[order], color=colors)
    regret_axis.axvline(0, color="#2d3436", linewidth=0.8)
    regret_axis.set_yticks(range(len(order)), [labels[index] for index in order], fontsize=7)
    regret_axis.set(
        title="Hierarchy regret versus the better simple comparator",
        xlabel="deviance difference (negative is better)",
    )

    observed = torch.tensor([fold["evaluation_events"] for fold in folds])
    medians = torch.tensor(
        [fold["predictive_distribution"]["total_median"] for fold in folds]
    )
    lower = torch.tensor(
        [fold["predictive_distribution"]["total_p10"] for fold in folds]
    )
    upper = torch.tensor(
        [fold["predictive_distribution"]["total_p90"] for fold in folds]
    )
    totals_axis.errorbar(
        observed.numpy(),
        medians.numpy(),
        yerr=torch.stack((medians - lower, upper - medians)).numpy(),
        fmt="o",
        alpha=0.7,
        capsize=2,
    )
    total_max = float(torch.maximum(observed.max(), upper.max())) * 1.15
    totals_axis.plot([10, total_max], [10, total_max], ":", color="#636e72")
    totals_axis.set_xscale("log")
    totals_axis.set_yscale("log")
    totals_axis.set(
        xlabel="observed evaluation total",
        ylabel="predictive median and central 80%",
        title="Frozen population-predictive totals",
    )
    totals_axis.grid(alpha=0.2, which="both")

    calibration = torch.tensor([fold["calibration_events"] for fold in folds])
    evaluation = torch.tensor([fold["evaluation_events"] for fold in folds])
    magnitudes = [fold["magnitude"] for fold in folds]
    scatter = domain_axis.scatter(
        calibration,
        evaluation,
        c=magnitudes,
        cmap="viridis",
        s=45,
        alpha=0.8,
    )
    domain_axis.set_xscale("log")
    domain_axis.set_yscale("log")
    domain_axis.set(
        xlabel="hour-1-to-day-1 events",
        ylabel="day-1-to-day-30 events",
        title="External cohort scale and mainshock magnitude",
    )
    fig.colorbar(scatter, ax=domain_axis, label="mainshock magnitude")
    domain_axis.grid(alpha=0.2, which="both")

    fig.suptitle(
        "Frozen western aftershock hierarchy · retrospective Alaska/Gulf external test"
    )
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_external_validation()
    (output_dir / "external_aftershock_validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_external_validation(report, output_dir / "external_aftershock_validation.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
