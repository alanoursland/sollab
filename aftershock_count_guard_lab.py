"""Let held-out count likelihood decide whether metadata may shift an aftershock prior."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aftershock_hierarchy_lab import (
    PopulationShape,
    fit_hierarchical_target,
    robust_population,
    shape_vector,
)
from aftershock_lab import DTYPE, fit_relaxation_model, poisson_deviance
from aftershock_meta_lab import (
    BLEND_WEIGHTS,
    choose_ridge_strength,
    early_features,
    load_population_manifest,
    ridge_predict,
)
from aftershock_transfer_lab import CALIBRATION_END_DAYS, load_sequence, make_transfer_bins


def choose_count_space_blend(
    outer_training: list[int],
    sequences: list,
    features: torch.Tensor,
    targets: torch.Tensor,
    full_fits: list,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    evaluation_mask: torch.Tensor,
    pooling_strength: float,
    ridge_strength: float,
) -> tuple[float, dict[str, float]]:
    scores = {blend: [] for blend in BLEND_WEIGHTS}
    for validation in outer_training:
        inner_training = [index for index in outer_training if index != validation]
        population = robust_population(full_fits, inner_training)
        learned = ridge_predict(
            features[inner_training],
            targets[inner_training],
            features[validation],
            ridge_strength,
        )
        for blend in BLEND_WEIGHTS:
            prior = PopulationShape(
                center=population.center + blend * (learned - population.center),
                scale=population.scale,
            )
            fit = fit_hierarchical_target(
                sequences[validation],
                edges,
                calibration_mask,
                prior,
                pooling_strength,
            )
            scores[blend].append(
                poisson_deviance(
                    fit.expected_counts[evaluation_mask],
                    sequences[validation].counts[evaluation_mask],
                )
            )
    means = {
        str(blend): sum(values) / len(values) for blend, values in scores.items()
    }
    selected = min(BLEND_WEIGHTS, key=lambda blend: (means[str(blend)], blend))
    return selected, means


def main(
    data_dir: Path = Path("data/aftershock_population"),
    output_dir: Path = Path("artifacts"),
) -> None:
    hierarchy_path = output_dir / "aftershock_population_hierarchy.json"
    if not hierarchy_path.exists():
        raise FileNotFoundError(
            f"{hierarchy_path} is missing; run aftershock_population_hierarchy_lab.py"
        )
    hierarchy = json.loads(hierarchy_path.read_text(encoding="utf-8"))
    specs, records = load_population_manifest(data_dir / "manifest.json")
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)
    sequences = [load_sequence(spec, edges, data_dir) for spec in specs]
    features = torch.stack(
        [early_features(sequence, record) for sequence, record in zip(sequences, records)]
    )
    full_fits = [
        fit_relaxation_model(
            "omori", edges, sequence.counts, all_mask, sequence.background
        )
        for sequence in sequences
    ]
    targets = torch.stack([shape_vector(fit) for fit in full_fits])

    folds = []
    for target_index, target in enumerate(sequences):
        training = [index for index in range(len(sequences)) if index != target_index]
        baseline = hierarchy["folds"][target_index]
        if baseline["event_id"] != target.spec.event_id:
            raise RuntimeError("Hierarchy artifact and population manifest disagree")
        pooling_strength = baseline["selected_pooling_strength"]
        ridge_strength, _ = choose_ridge_strength(
            features[training], targets[training]
        )
        blend, inner_scores = choose_count_space_blend(
            training,
            sequences,
            features,
            targets,
            full_fits,
            edges,
            calibration_mask,
            evaluation_mask,
            pooling_strength,
            ridge_strength,
        )
        population = robust_population(full_fits, training)
        learned = ridge_predict(
            features[training], targets[training], features[target_index], ridge_strength
        )
        guarded_prior = PopulationShape(
            center=population.center + blend * (learned - population.center),
            scale=population.scale,
        )
        fully_conditioned_prior = PopulationShape(
            center=learned,
            scale=population.scale,
        )
        guarded = fit_hierarchical_target(
            target, edges, calibration_mask, guarded_prior, pooling_strength
        )
        fully_conditioned = fit_hierarchical_target(
            target, edges, calibration_mask, fully_conditioned_prior, pooling_strength
        )
        observed = target.counts[evaluation_mask]
        folds.append(
            {
                "event_id": target.spec.event_id,
                "name": target.spec.name,
                "pooling_strength": pooling_strength,
                "ridge_strength": ridge_strength,
                "selected_blend": blend,
                "inner_mean_count_deviance": inner_scores,
                "baseline_deviance": baseline["models"]["hierarchical"][
                    "poisson_deviance"
                ],
                "fully_conditioned_deviance": poisson_deviance(
                    fully_conditioned.expected_counts[evaluation_mask], observed
                ),
                "guarded_deviance": poisson_deviance(
                    guarded.expected_counts[evaluation_mask], observed
                ),
                "observed_total": float(observed.sum()),
                "baseline_predicted_total": baseline["models"]["hierarchical"][
                    "predicted_total"
                ],
                "guarded_predicted_total": float(
                    guarded.expected_counts[evaluation_mask].sum()
                ),
                "guarded_parameters": guarded.parameters,
            }
        )

    baseline_scores = torch.tensor(
        [fold["baseline_deviance"] for fold in folds], dtype=DTYPE
    )
    conditioned_scores = torch.tensor(
        [fold["fully_conditioned_deviance"] for fold in folds], dtype=DTYPE
    )
    guarded_scores = torch.tensor(
        [fold["guarded_deviance"] for fold in folds], dtype=DTYPE
    )
    summary = {
        "experiment": "count-space guard for metadata-conditioned hierarchical priors",
        "protocol": (
            "outer whole-sequence leave-one-out; inner mean future-count deviance "
            "selects metadata blend"
        ),
        "sequence_count": len(folds),
        "aggregate": {
            "baseline_total_deviance": float(baseline_scores.sum()),
            "fully_conditioned_total_deviance": float(conditioned_scores.sum()),
            "guarded_total_deviance": float(guarded_scores.sum()),
            "baseline_median_deviance": float(baseline_scores.median()),
            "fully_conditioned_median_deviance": float(conditioned_scores.median()),
            "guarded_median_deviance": float(guarded_scores.median()),
            "fully_conditioned_wins": int(
                (conditioned_scores < baseline_scores).sum()
            ),
            "guarded_wins": int((guarded_scores < baseline_scores).sum()),
            "zero_blend_folds": sum(fold["selected_blend"] == 0.0 for fold in folds),
        },
        "folds": folds,
    }
    result_path = output_dir / "aftershock_count_guard.json"
    result_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    positions = torch.arange(len(folds)).numpy()
    width = 0.26
    fig, ax = plt.subplots(figsize=(12, 6.8))
    ax.bar(positions - width, baseline_scores.numpy(), width, label="partial pooling")
    ax.bar(
        positions,
        conditioned_scores.numpy(),
        width,
        label="fully metadata-shifted prior",
    )
    ax.bar(
        positions + width,
        guarded_scores.numpy(),
        width,
        label="count-space guarded prior",
    )
    ax.set_yscale("log")
    ax.set_xticks(
        positions,
        [fold["event_id"] for fold in folds],
        rotation=38,
        ha="right",
    )
    ax.set_ylabel("Day 1–30 Poisson deviance (log scale)")
    ax.set_title("Can count-space validation make metadata corrections safe?")
    ax.legend(frameon=False)
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    figure_path = output_dir / "aftershock_count_guard.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)
    print(json.dumps(summary["aggregate"], indent=2))
    print(f"Wrote {result_path} and {figure_path}")


if __name__ == "__main__":
    main()
