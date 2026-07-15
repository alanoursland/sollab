"""Re-test robust aftershock partial pooling on the screened 12-sequence population."""

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
    load_sequence,
    make_transfer_bins,
)


def main(
    data_dir: Path = Path("data/aftershock_population"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    specs, _ = load_population_manifest(data_dir / "manifest.json")
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)
    sequences = [load_sequence(spec, edges, data_dir) for spec in specs]
    full_fits = [
        fit_relaxation_model(
            "omori", edges, sequence.counts, all_mask, sequence.background
        )
        for sequence in sequences
    ]

    folds = []
    for target_index, target in enumerate(sequences):
        training = [index for index in range(len(sequences)) if index != target_index]
        population = robust_population(full_fits, training)
        strength, inner_scores = choose_pooling_strength(
            training,
            sequences,
            full_fits,
            edges,
            calibration_mask,
            evaluation_mask,
        )
        hierarchical = fit_hierarchical_target(
            target, edges, calibration_mask, population, strength
        )
        pooled_expected, pooled_parameters = expected_from_shape(
            target, population.center, edges, calibration_mask
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
            population,
            seed=20260716 + target_index,
        )
        models = {}
        for name, expected, parameters in (
            ("hierarchical", hierarchical.expected_counts, hierarchical.parameters),
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
        folds.append(
            {
                "event_id": target.spec.event_id,
                "target": target.spec.slug,
                "name": target.spec.name,
                "evaluation_events": int(target.counts[evaluation_mask].sum()),
                "selected_pooling_strength": strength,
                "inner_median_deviance": inner_scores,
                "models": models,
                "predictive_distribution": predictive,
            }
        )

    model_names = ("hierarchical", "robust_pool", "target_day1")
    aggregate = {}
    for model in model_names:
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
                    for candidate in model_names
                )
                for score, fold in zip(scores, folds)
            ),
        }
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
    report = {
        "experiment": "screened-population robust hierarchical aftershock transfer",
        "sequence_count": len(folds),
        "outer_protocol": "whole-sequence leave-one-out; target uses hour 1-day 1",
        "inner_protocol": "nested leave-one-sequence-out selection of pooling strength",
        "folds": folds,
        "aggregate": aggregate,
        "predictive_coverage": coverage,
    }
    target = output_dir / "aftershock_population_hierarchy.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    positions = torch.arange(len(folds), dtype=DTYPE).numpy()
    width = 0.26
    colors = ("#0984e3", "#00b894", "#6c5ce7")
    labels = ("partial pooling", "robust population", "target day 1")
    fig, (score_axis, interval_axis) = plt.subplots(
        2, 1, figsize=(12, 9), constrained_layout=True
    )
    for offset, model, color, label in zip(
        (-width, 0.0, width), model_names, colors, labels
    ):
        score_axis.bar(
            positions + offset,
            [fold["models"][model]["poisson_deviance"] for fold in folds],
            width,
            color=color,
            label=label,
        )
    short_names = [fold["event_id"] for fold in folds]
    score_axis.set_yscale("log")
    score_axis.set_xticks(positions, short_names, rotation=35, ha="right")
    score_axis.set_ylabel("Day 1–30 Poisson deviance (log scale)")
    score_axis.set_title("Expanded whole-sequence validation")
    score_axis.legend(frameon=False)
    score_axis.grid(axis="y", alpha=0.2)

    observed = torch.tensor([fold["evaluation_events"] for fold in folds], dtype=DTYPE)
    median = torch.tensor(
        [fold["predictive_distribution"]["total_median"] for fold in folds],
        dtype=DTYPE,
    )
    lower = torch.tensor(
        [fold["predictive_distribution"]["total_p10"] for fold in folds], dtype=DTYPE
    )
    upper = torch.tensor(
        [fold["predictive_distribution"]["total_p90"] for fold in folds], dtype=DTYPE
    )
    interval_axis.errorbar(
        positions,
        median,
        yerr=torch.stack((median - lower, upper - median)).numpy(),
        fmt="o",
        capsize=4,
        label="population predictive 80%",
    )
    interval_axis.scatter(positions, observed, marker="x", s=60, label="observed")
    interval_axis.set_yscale("log")
    interval_axis.set_xticks(positions, short_names, rotation=35, ha="right")
    interval_axis.set_ylabel("Day 1–30 event total (log scale)")
    interval_axis.set_title(
        f"Predictive totals cover {coverage['total_intervals_covered']}/{len(folds)} sequences"
    )
    interval_axis.legend(frameon=False)
    interval_axis.grid(axis="y", alpha=0.2)
    figure = output_dir / "aftershock_population_hierarchy.png"
    fig.savefig(figure, dpi=180)
    plt.close(fig)
    print(json.dumps({"aggregate": aggregate, "coverage": coverage}, indent=2))
    print(f"Wrote {target} and {figure}")


if __name__ == "__main__":
    main()
