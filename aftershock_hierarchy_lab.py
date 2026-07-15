"""Robust partial pooling for whole-sequence aftershock prediction."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.identification.parametric import LevenbergMarquardt

from aftershock_lab import (
    DTYPE,
    FitResult,
    _encode_p,
    anscombe_residual,
    decode_omori,
    fit_relaxation_model,
    omori_expected_counts,
    poisson_deviance,
)
from aftershock_transfer_lab import (
    CALIBRATION_END_DAYS,
    SequenceData,
    calibrate_amplitude,
    fit_shared_shape,
    load_sequence,
    make_transfer_bins,
)
from fetch_aftershock_benchmark import SEQUENCES


POOLING_STRENGTHS = (0.25, 1.0, 4.0, 16.0)
PREDICTIVE_SAMPLES = 1024


@dataclass
class PopulationShape:
    center: torch.Tensor
    scale: torch.Tensor


@dataclass
class HierarchicalFit:
    theta: torch.Tensor
    parameters: dict[str, float]
    expected_counts: torch.Tensor
    objective: float
    iterations: int


def shape_vector(fit: FitResult) -> torch.Tensor:
    c_days = min(2.0, max(1e-4, fit.parameters["c_days"]))
    exponent = min(1.95, max(0.35, fit.parameters["p"]))
    return torch.tensor(
        [math.log(c_days), _encode_p(exponent)], dtype=DTYPE
    )


def robust_population(
    full_fits: list[FitResult], indices: list[int]
) -> PopulationShape:
    values = torch.stack([shape_vector(full_fits[index]) for index in indices])
    center = values.median(dim=0).values
    mad = (values - center).abs().median(dim=0).values
    scale = (1.4826 * mad).clamp(min=0.35, max=3.0)
    return PopulationShape(center=center, scale=scale)


def fit_hierarchical_target(
    sequence: SequenceData,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    population: PopulationShape,
    pooling_strength: float,
) -> HierarchicalFit:
    widths = torch.diff(edges)
    center_c = torch.exp(population.center[0])
    center_p = 0.3 + 1.7 * torch.sigmoid(population.center[1])
    center_theta = torch.tensor(
        [0.0, population.center[0], population.center[1]], dtype=DTYPE
    )
    center_kernel = omori_expected_counts(
        center_theta, edges, 0.0
    )
    transient = (
        sequence.counts[calibration_mask]
        - sequence.background * widths[calibration_mask]
    ).sum().clamp_min(1.0)
    amplitude = float(
        transient / center_kernel[calibration_mask].sum().clamp_min(1e-12)
    )
    initial = torch.tensor(
        [math.log(amplitude), population.center[0], population.center[1]],
        dtype=DTYPE,
    )

    def residual(theta: torch.Tensor) -> torch.Tensor:
        data_residual = anscombe_residual(
            omori_expected_counts(theta, edges, sequence.background)[
                calibration_mask
            ],
            sequence.counts[calibration_mask],
        )
        prior_residual = math.sqrt(pooling_strength) * (
            theta[1:] - population.center
        ) / population.scale
        return torch.cat((data_residual, prior_residual))

    alternative = torch.tensor(
        [
            math.log(amplitude),
            population.center[0] + 0.25 * population.scale[0],
            population.center[1] - 0.25 * population.scale[1],
        ],
        dtype=DTYPE,
    )
    candidates = []
    for start in (initial, alternative):
        optimizer = LevenbergMarquardt(residual, start)
        try:
            theta = optimizer.optimize(max_iter=60, tolerance=1e-8)
            objective = float(residual(theta).square().sum())
        except (RuntimeError, ValueError):
            continue
        if math.isfinite(objective):
            candidates.append((objective, theta, len(optimizer.history)))
    if not candidates:
        raise RuntimeError("All KinoPulse hierarchical target fits failed")

    objective, theta, iterations = min(candidates, key=lambda item: item[0])
    productivity, offset, exponent = decode_omori(theta)
    return HierarchicalFit(
        theta=theta,
        parameters={
            "productivity": float(productivity),
            "c_days": float(offset),
            "p": float(exponent),
            "pooling_strength": pooling_strength,
            "population_c_days": float(center_c),
            "population_p": float(center_p),
            "population_log_c_scale": float(population.scale[0]),
            "population_p_transform_scale": float(population.scale[1]),
        },
        expected_counts=omori_expected_counts(
            theta, edges, sequence.background
        ).detach(),
        objective=objective,
        iterations=iterations,
    )


def choose_pooling_strength(
    outer_training_indices: list[int],
    sequences: list[SequenceData],
    full_fits: list[FitResult],
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    evaluation_mask: torch.Tensor,
) -> tuple[float, dict[str, float]]:
    scores: dict[float, list[float]] = {
        strength: [] for strength in POOLING_STRENGTHS
    }
    for validation_index in outer_training_indices:
        population_indices = [
            index
            for index in outer_training_indices
            if index != validation_index
        ]
        population = robust_population(full_fits, population_indices)
        validation = sequences[validation_index]
        for strength in POOLING_STRENGTHS:
            fit = fit_hierarchical_target(
                validation,
                edges,
                calibration_mask,
                population,
                strength,
            )
            scores[strength].append(
                poisson_deviance(
                    fit.expected_counts[evaluation_mask],
                    validation.counts[evaluation_mask],
                )
            )
    medians = {
        str(strength): float(torch.tensor(values, dtype=DTYPE).median())
        for strength, values in scores.items()
    }
    selected = min(
        POOLING_STRENGTHS,
        key=lambda strength: (medians[str(strength)], strength),
    )
    return selected, medians


def _sample_predictive_distribution(
    sequence: SequenceData,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    evaluation_mask: torch.Tensor,
    population: PopulationShape,
    seed: int,
) -> dict[str, float | list[float]]:
    generator = torch.Generator().manual_seed(seed)
    proposal_count = 4096
    proposed = (
        population.center[None, :]
        + population.scale[None, :]
        * torch.randn(
            (proposal_count, 2), dtype=DTYPE, generator=generator
        )
    )
    proposed[:, 0].clamp_(math.log(1e-4), math.log(2.0))
    proposed[:, 1].clamp_(_encode_p(0.35), _encode_p(1.95))
    offset = torch.exp(proposed[:, 0])
    exponent = 0.3 + 1.7 * torch.sigmoid(proposed[:, 1])
    start, end = edges[:-1], edges[1:]
    log_start = torch.log(start[None, :] + offset[:, None])
    log_ratio = torch.log(
        (end[None, :] + offset[:, None])
        / (start[None, :] + offset[:, None])
    )
    one_minus_p = 1.0 - exponent[:, None]
    safe = torch.where(
        (one_minus_p * log_ratio).abs() < 1e-7,
        torch.ones_like(log_ratio),
        one_minus_p * log_ratio,
    )
    exprel = torch.expm1(one_minus_p * log_ratio) / safe
    near_zero = (one_minus_p * log_ratio).abs() < 1e-5
    value = one_minus_p * log_ratio
    series = 1.0 + value / 2.0 + value.square() / 6.0
    exprel = torch.where(near_zero, series, exprel)
    kernel = torch.exp(one_minus_p * log_start) * log_ratio * exprel
    widths = torch.diff(edges)
    transient = (
        sequence.counts[calibration_mask]
        - sequence.background * widths[calibration_mask]
    ).sum().clamp_min(1.0)
    amplitude = transient / kernel[:, calibration_mask].sum(dim=1).clamp_min(1e-12)
    expected = (
        amplitude[:, None] * kernel
        + sequence.background * widths[None, :]
    )
    observed_calibration = sequence.counts[calibration_mask][None, :]
    expected_calibration = expected[:, calibration_mask].clamp_min(1e-12)
    log_term = torch.where(
        observed_calibration > 0,
        observed_calibration
        * torch.log(observed_calibration / expected_calibration),
        torch.zeros_like(expected_calibration),
    )
    calibration_deviance = 2.0 * (
        log_term - (observed_calibration - expected_calibration)
    ).sum(dim=1)
    log_weight = -0.5 * (
        calibration_deviance - calibration_deviance.min()
    )
    weights = torch.softmax(log_weight, dim=0)
    selected = torch.multinomial(
        weights,
        PREDICTIVE_SAMPLES,
        replacement=True,
        generator=generator,
    )
    selected_expected = expected[selected][:, evaluation_mask]
    predictive_counts = torch.poisson(
        selected_expected, generator=generator
    )
    total_samples = predictive_counts.sum(dim=1)
    quantiles = torch.tensor([0.1, 0.5, 0.9], dtype=DTYPE)
    bin_quantiles = torch.quantile(predictive_counts, quantiles, dim=0)
    total_quantiles = torch.quantile(total_samples, quantiles)
    observed = sequence.counts[evaluation_mask]
    bin_coverage = (
        (observed >= bin_quantiles[0])
        & (observed <= bin_quantiles[2])
    ).to(dtype=DTYPE).mean()
    observed_total = float(observed.sum())
    effective_sample_size = float(1.0 / weights.square().sum())
    return {
        "lower_by_bin": bin_quantiles[0].tolist(),
        "median_by_bin": bin_quantiles[1].tolist(),
        "upper_by_bin": bin_quantiles[2].tolist(),
        "total_p10": float(total_quantiles[0]),
        "total_median": float(total_quantiles[1]),
        "total_p90": float(total_quantiles[2]),
        "observed_total": observed_total,
        "total_covered": bool(
            total_quantiles[0] <= observed_total <= total_quantiles[2]
        ),
        "bin_coverage": float(bin_coverage),
        "proposal_effective_sample_size": effective_sample_size,
    }


def main(
    data_dir: Path = Path("data/aftershock_benchmark"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    all_mask = edges[1:] <= edges[-1]
    sequences = [load_sequence(spec, edges, data_dir) for spec in SEQUENCES]
    full_fits = [
        fit_relaxation_model(
            "omori", edges, sequence.counts, all_mask, sequence.background
        )
        for sequence in sequences
    ]

    folds = []
    for target_index, target in enumerate(sequences):
        training_indices = [
            index for index in range(len(sequences)) if index != target_index
        ]
        population = robust_population(full_fits, training_indices)
        pooling_strength, inner_scores = choose_pooling_strength(
            training_indices,
            sequences,
            full_fits,
            edges,
            calibration_mask,
            evaluation_mask,
        )
        hierarchical = fit_hierarchical_target(
            target,
            edges,
            calibration_mask,
            population,
            pooling_strength,
        )
        training_sequences = [sequences[index] for index in training_indices]
        pooled_shape = fit_shared_shape(training_sequences, edges, "omori")
        _, pooled_expected = calibrate_amplitude(
            target.counts,
            edges,
            calibration_mask,
            target.background,
            "omori",
            pooled_shape.parameters,
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
            seed=20260715 + target_index,
        )
        models = {}
        for name, expected, parameters in (
            ("hierarchical", hierarchical.expected_counts, hierarchical.parameters),
            ("fully_pooled", pooled_expected, pooled_shape.parameters),
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
                "target": target.spec.slug,
                "name": target.spec.name,
                "evaluation_events": int(target.counts[evaluation_mask].sum()),
                "selected_pooling_strength": pooling_strength,
                "inner_median_deviance": inner_scores,
                "models": models,
                "predictive_distribution": predictive,
            }
        )

    model_names = ("hierarchical", "fully_pooled", "target_day1")
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
        "experiment": "robust hierarchical aftershock transfer",
        "outer_protocol": "whole-sequence leave-one-out; target uses hour 1-day 1",
        "inner_protocol": "nested leave-one-sequence-out selection of pooling strength",
        "pooling_strengths": list(POOLING_STRENGTHS),
        "folds": folds,
        "aggregate": aggregate,
        "predictive_coverage": coverage,
    }
    (output_dir / "aftershock_hierarchy_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    positions = torch.arange(len(folds), dtype=DTYPE)
    names = [fold["name"].rsplit(" ", 1)[0] for fold in folds]
    colors = {
        "hierarchical": "#0984e3",
        "fully_pooled": "#00b894",
        "target_day1": "#6c5ce7",
    }
    labels = {
        "hierarchical": "partial pooling",
        "fully_pooled": "full pooling",
        "target_day1": "target only",
    }
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)
    score_axis, parameter_axis, interval_axis, coverage_axis = axes.ravel()
    width = 0.25
    for offset, model in zip((-width, 0.0, width), model_names):
        score_axis.bar(
            positions + offset,
            [fold["models"][model]["poisson_deviance"] for fold in folds],
            width=width,
            color=colors[model],
            label=labels[model],
        )
    score_axis.set_yscale("log")
    score_axis.set_xticks(positions, names)
    score_axis.tick_params(axis="x", labelrotation=25, labelsize=8)
    score_axis.set(
        title="Nested whole-sequence validation",
        ylabel="day 1-30 Poisson deviance (log scale)",
    )
    score_axis.legend(frameon=False, fontsize=8)
    score_axis.grid(alpha=0.2, axis="y")

    hierarchical_c = [
        fold["models"]["hierarchical"]["parameters"]["c_days"]
        for fold in folds
    ]
    hierarchical_p = [
        fold["models"]["hierarchical"]["parameters"]["p"]
        for fold in folds
    ]
    scatter = parameter_axis.scatter(
        hierarchical_c,
        hierarchical_p,
        c=[fold["selected_pooling_strength"] for fold in folds],
        cmap="plasma",
        s=75,
    )
    for c_value, p_value, fold in zip(hierarchical_c, hierarchical_p, folds):
        parameter_axis.annotate(
            fold["target"].split("_")[0],
            (c_value, p_value),
            fontsize=7,
        )
    parameter_axis.set_xscale("log")
    parameter_axis.set(
        title="Partially pooled target shapes",
        xlabel="c (days, log scale)",
        ylabel="p",
    )
    parameter_axis.grid(alpha=0.2)
    fig.colorbar(scatter, ax=parameter_axis, label="selected pooling strength")

    observed_totals = torch.tensor(
        [fold["evaluation_events"] for fold in folds], dtype=DTYPE
    )
    medians = torch.tensor(
        [fold["predictive_distribution"]["total_median"] for fold in folds],
        dtype=DTYPE,
    )
    lower = torch.tensor(
        [fold["predictive_distribution"]["total_p10"] for fold in folds],
        dtype=DTYPE,
    )
    upper = torch.tensor(
        [fold["predictive_distribution"]["total_p90"] for fold in folds],
        dtype=DTYPE,
    )
    interval_axis.errorbar(
        positions.numpy(),
        medians.numpy(),
        yerr=torch.stack((medians - lower, upper - medians)).numpy(),
        fmt="o",
        color="#0984e3",
        ecolor="#74b9ff",
        capsize=4,
        label="population predictive 80%",
    )
    interval_axis.scatter(
        positions,
        observed_totals,
        marker="x",
        s=55,
        color="#d63031",
        label="observed",
    )
    interval_axis.set_yscale("log")
    interval_axis.set_xticks(positions, names)
    interval_axis.tick_params(axis="x", labelrotation=25, labelsize=8)
    interval_axis.set(
        title="Population predictive totals",
        ylabel="day 1-30 events (log scale)",
    )
    interval_axis.legend(frameon=False, fontsize=8)
    interval_axis.grid(alpha=0.2, axis="y")

    aggregate_values = [
        aggregate[model]["median_sequence_deviance"] for model in model_names
    ]
    coverage_axis.bar(
        range(3),
        aggregate_values,
        color=[colors[model] for model in model_names],
    )
    coverage_axis.set_xticks(
        range(3), ["partial\npooling", "full\npooling", "target\nonly"]
    )
    coverage_axis.set(
        title=(
            "Equal-sequence score; predictive totals cover "
            f'{coverage["total_intervals_covered"]}/8'
        ),
        ylabel="median sequence Poisson deviance",
    )
    for index, model in enumerate(model_names):
        coverage_axis.text(
            index,
            aggregate_values[index],
            f'{aggregate[model]["sequence_wins"]}/8 wins',
            ha="center",
            va="bottom",
            fontsize=8,
        )
    coverage_axis.grid(alpha=0.2, axis="y")

    fig.suptitle(
        "KinoPulse aftershock hierarchy - when should a new sequence escape the population?"
    )
    fig.savefig(output_dir / "aftershock_hierarchy_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
