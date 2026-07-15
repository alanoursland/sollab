"""Predict aftershock decay personalities from information available by day one."""

from __future__ import annotations

import json
import math
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.opt.least_squares import ridge_solve

from aftershock_hierarchy_lab import robust_population, shape_vector
from aftershock_lab import DTYPE, fit_relaxation_model, poisson_deviance
from aftershock_transfer_lab import (
    CALIBRATION_END_DAYS,
    SequenceData,
    calibrate_amplitude,
    load_sequence,
    make_transfer_bins,
)
from fetch_aftershock_benchmark import SequenceSpec


RIDGE_STRENGTHS = (0.01, 0.1, 1.0, 10.0, 100.0)
BLEND_WEIGHTS = (0.0, 0.25, 0.5, 0.75, 1.0)
FEATURE_NAMES = (
    "mainshock_magnitude",
    "log1p_depth_km",
    "log1p_first_day_count",
    "early_vs_late_log_ratio",
    "log1p_background_rate",
)


def load_population_manifest(
    path: Path = Path("data/aftershock_population/manifest.json"),
) -> tuple[list[SequenceSpec], list[dict]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    records = [record for record in document["records"] if record["selected"]]
    specs = [
        SequenceSpec(
            slug=record["slug"],
            name=record["name"],
            event_id=record["event_id"],
            time=record["time"],
            latitude=record["latitude"],
            longitude=record["longitude"],
            magnitude=record["magnitude"],
        )
        for record in records
    ]
    return specs, records


def early_features(sequence: SequenceData, record: dict) -> torch.Tensor:
    times = sequence.times_days
    first_quarter = int(((times >= 1.0 / 24.0) & (times <= 0.25)).sum())
    later = int(((times > 0.25) & (times <= CALIBRATION_END_DAYS)).sum())
    first_day = first_quarter + later
    return torch.tensor(
        [
            record["magnitude"],
            math.log1p(max(0.0, record["depth_km"])),
            math.log1p(first_day),
            math.log((first_quarter + 1.0) / (later + 1.0)),
            math.log1p(sequence.background),
        ],
        dtype=DTYPE,
    )


def ridge_predict(
    training_features: torch.Tensor,
    training_targets: torch.Tensor,
    target_features: torch.Tensor,
    strength: float,
) -> torch.Tensor:
    feature_center = training_features.mean(dim=0)
    feature_scale = training_features.std(dim=0, unbiased=False).clamp_min(1e-8)
    target_center = training_targets.mean(dim=0)
    design = (training_features - feature_center) / feature_scale
    centered_targets = training_targets - target_center
    coefficients = ridge_solve(design, centered_targets, strength)
    target_design = (target_features - feature_center) / feature_scale
    return target_center + target_design @ coefficients


def choose_ridge_strength(
    features: torch.Tensor,
    targets: torch.Tensor,
) -> tuple[float, dict[str, float]]:
    scores = {strength: [] for strength in RIDGE_STRENGTHS}
    for validation in range(len(features)):
        training = [index for index in range(len(features)) if index != validation]
        target_scale = targets[training].std(dim=0, unbiased=False).clamp_min(0.35)
        for strength in RIDGE_STRENGTHS:
            predicted = ridge_predict(
                features[training], targets[training], features[validation], strength
            )
            error = ((predicted - targets[validation]) / target_scale).square().mean()
            scores[strength].append(float(error))
    means = {
        str(strength): sum(values) / len(values)
        for strength, values in scores.items()
    }
    selected = min(RIDGE_STRENGTHS, key=lambda value: (means[str(value)], value))
    return selected, means


def choose_guarded_configuration(
    features: torch.Tensor,
    targets: torch.Tensor,
    full_fits: list,
    outer_training: list[int],
) -> tuple[float, float, dict[str, float]]:
    """Choose ridge and trust using inner folds of the historical population."""
    scores = {
        (strength, blend): []
        for strength in RIDGE_STRENGTHS
        for blend in BLEND_WEIGHTS
    }
    for validation in outer_training:
        inner_training = [index for index in outer_training if index != validation]
        population = robust_population(full_fits, inner_training)
        for strength in RIDGE_STRENGTHS:
            learned = ridge_predict(
                features[inner_training],
                targets[inner_training],
                features[validation],
                strength,
            )
            for blend in BLEND_WEIGHTS:
                predicted = population.center + blend * (learned - population.center)
                error = (
                    (predicted - targets[validation]) / population.scale
                ).square().mean()
                scores[(strength, blend)].append(float(error))
    means = {
        f"alpha={strength},blend={blend}": sum(values) / len(values)
        for (strength, blend), values in scores.items()
    }
    selected_strength, selected_blend = min(
        scores,
        key=lambda item: (
            sum(scores[item]) / len(scores[item]),
            item[1],
            item[0],
        ),
    )
    return selected_strength, selected_blend, means


def expected_from_shape(
    sequence: SequenceData,
    shape: torch.Tensor,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
) -> tuple[torch.Tensor, dict[str, float]]:
    log_c = float(shape[0].clamp(math.log(1e-4), math.log(2.0)))
    encoded_p = float(shape[1].clamp(-12.0, 12.0))
    parameters = {
        "c_days": math.exp(log_c),
        "p": 0.3 + 1.7 / (1.0 + math.exp(-encoded_p)),
    }
    amplitude, expected = calibrate_amplitude(
        sequence.counts,
        edges,
        calibration_mask,
        sequence.background,
        "omori",
        parameters,
    )
    return expected, {**parameters, "amplitude": amplitude}


def main(
    data_dir: Path = Path("data/aftershock_population"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    specs, records = load_population_manifest(data_dir / "manifest.json")
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    sequences = [load_sequence(spec, edges, data_dir) for spec in specs]
    features = torch.stack(
        [early_features(sequence, record) for sequence, record in zip(sequences, records)]
    )
    full_fits = [
        fit_relaxation_model(
            "omori",
            edges,
            sequence.counts,
            torch.ones_like(sequence.counts, dtype=torch.bool),
            sequence.background,
        )
        for sequence in sequences
    ]
    targets = torch.stack([shape_vector(fit) for fit in full_fits])

    folds = []
    for target_index, sequence in enumerate(sequences):
        training = [index for index in range(len(sequences)) if index != target_index]
        population = robust_population(full_fits, training)
        strength, inner_scores = choose_ridge_strength(features[training], targets[training])
        conditioned_shape = ridge_predict(
            features[training], targets[training], features[target_index], strength
        )
        guarded_strength, blend, guarded_inner_scores = choose_guarded_configuration(
            features, targets, full_fits, training
        )
        guarded_learned_shape = ridge_predict(
            features[training],
            targets[training],
            features[target_index],
            guarded_strength,
        )
        guarded_shape = population.center + blend * (
            guarded_learned_shape - population.center
        )
        pooled_expected, pooled_parameters = expected_from_shape(
            sequence, population.center, edges, calibration_mask
        )
        conditioned_expected, conditioned_parameters = expected_from_shape(
            sequence, conditioned_shape, edges, calibration_mask
        )
        guarded_expected, guarded_parameters = expected_from_shape(
            sequence, guarded_shape, edges, calibration_mask
        )
        observed = sequence.counts[evaluation_mask]
        pooled_deviance = poisson_deviance(pooled_expected[evaluation_mask], observed)
        conditioned_deviance = poisson_deviance(
            conditioned_expected[evaluation_mask], observed
        )
        guarded_deviance = poisson_deviance(
            guarded_expected[evaluation_mask], observed
        )
        folds.append(
            {
                "slug": sequence.spec.slug,
                "name": sequence.spec.name,
                "event_id": sequence.spec.event_id,
                "features": dict(zip(FEATURE_NAMES, features[target_index].tolist())),
                "selected_ridge_strength": strength,
                "inner_cv_scores": inner_scores,
                "guarded_ridge_strength": guarded_strength,
                "guarded_blend_weight": blend,
                "guarded_inner_cv_scores": guarded_inner_scores,
                "population_parameters": pooled_parameters,
                "conditioned_parameters": conditioned_parameters,
                "guarded_parameters": guarded_parameters,
                "oracle_full_fit_parameters": full_fits[target_index].parameters,
                "pooled_deviance": pooled_deviance,
                "conditioned_deviance": conditioned_deviance,
                "conditioned_wins": conditioned_deviance < pooled_deviance,
                "guarded_deviance": guarded_deviance,
                "guarded_wins": guarded_deviance < pooled_deviance,
                "observed_evaluation_count": float(observed.sum()),
                "pooled_predicted_count": float(pooled_expected[evaluation_mask].sum()),
                "conditioned_predicted_count": float(
                    conditioned_expected[evaluation_mask].sum()
                ),
                "guarded_predicted_count": float(
                    guarded_expected[evaluation_mask].sum()
                ),
            }
        )

    pooled = torch.tensor([fold["pooled_deviance"] for fold in folds], dtype=DTYPE)
    conditioned = torch.tensor(
        [fold["conditioned_deviance"] for fold in folds], dtype=DTYPE
    )
    guarded = torch.tensor([fold["guarded_deviance"] for fold in folds], dtype=DTYPE)
    summary = {
        "sequence_count": len(sequences),
        "feature_names": FEATURE_NAMES,
        "ridge_strengths": RIDGE_STRENGTHS,
        "blend_weights": BLEND_WEIGHTS,
        "method": "nested leave-one-sequence-out ridge conditioning",
        "pooled_total_deviance": float(pooled.sum()),
        "conditioned_total_deviance": float(conditioned.sum()),
        "guarded_total_deviance": float(guarded.sum()),
        "pooled_median_deviance": float(pooled.median()),
        "conditioned_median_deviance": float(conditioned.median()),
        "guarded_median_deviance": float(guarded.median()),
        "conditioned_wins": int((conditioned < pooled).sum()),
        "guarded_wins": int((guarded < pooled).sum()),
        "folds": folds,
    }
    json_path = output_dir / "aftershock_meta_results.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    labels = [fold["name"].replace(" Earthquake", "")[:28] for fold in folds]
    positions = torch.arange(len(folds)).numpy()
    width = 0.26
    fig, ax = plt.subplots(figsize=(12, 6.8))
    ax.bar(positions - width, pooled.numpy(), width, label="robust pooled shape")
    ax.bar(
        positions,
        conditioned.numpy(),
        width,
        label="first-day conditioned shape",
    )
    ax.bar(
        positions + width,
        guarded.numpy(),
        width,
        label="inner-CV guarded correction",
    )
    ax.set_yscale("log")
    ax.set_ylabel("Held-out day 1–30 Poisson deviance (log scale)")
    ax.set_xticks(positions, labels, rotation=42, ha="right")
    ax.set_title("Do early signals reveal an aftershock sequence's decay personality?")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    figure_path = output_dir / "aftershock_meta_prediction.png"
    fig.savefig(figure_path, dpi=180)
    plt.close(fig)
    print(json.dumps({key: value for key, value in summary.items() if key != "folds"}, indent=2))
    print(f"Wrote {json_path} and {figure_path}")


if __name__ == "__main__":
    main()
