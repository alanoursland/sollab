"""Test an online self-exciting extension of the Ridgecrest Omori model."""

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
    CONTROL_END_DAYS,
    CONTROL_START_DAYS,
    DTYPE,
    MAX_TIME_DAYS,
    MIN_TIME_DAYS,
    TRAIN_END_DAYS,
    _exprel,
    anscombe_residual,
    bin_events,
    fit_relaxation_model,
    load_catalog,
    model_metrics,
    poisson_deviance,
)


MAGNITUDE_THRESHOLD = 2.5
ALPHA_MAX = 3.0


@dataclass
class ExcitationFit:
    name: str
    theta: torch.Tensor
    parameters: dict[str, float]
    expected_counts: torch.Tensor
    objective: float
    iterations: int


def make_conditional_bins(train_bins: int = 56, holdout_bins: int = 92) -> torch.Tensor:
    training = torch.linspace(
        MIN_TIME_DAYS, TRAIN_END_DAYS, train_bins + 1, dtype=DTYPE
    )
    holdout = torch.linspace(
        TRAIN_END_DAYS, MAX_TIME_DAYS, holdout_bins + 1, dtype=DTYPE
    )
    return torch.cat((training, holdout[1:]))


def _power_integral(
    start: torch.Tensor,
    end: torch.Tensor,
    offset: torch.Tensor,
    exponent: torch.Tensor,
) -> torch.Tensor:
    log_start = torch.log(start + offset)
    log_ratio = torch.log((end + offset) / (start + offset))
    one_minus_p = 1.0 - exponent
    return (
        torch.exp(one_minus_p * log_start)
        * log_ratio
        * _exprel(one_minus_p * log_ratio)
    )


def decode_excitation(
    theta: torch.Tensor, magnitude_weighted: bool
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    primary_productivity = torch.exp(theta[0])
    secondary_productivity = torch.exp(theta[1])
    alpha = (
        ALPHA_MAX * torch.sigmoid(theta[2])
        if magnitude_weighted
        else theta.new_zeros(())
    )
    return primary_productivity, secondary_productivity, alpha


def excitation_expected_counts(
    theta: torch.Tensor,
    edges: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    *,
    offset: float,
    exponent: float,
    background: float,
    magnitude_weighted: bool,
) -> torch.Tensor:
    primary, secondary, alpha = decode_excitation(theta, magnitude_weighted)
    offset_tensor = theta.new_tensor(offset)
    exponent_tensor = theta.new_tensor(exponent)
    start, end = edges[:-1], edges[1:]

    primary_integral = _power_integral(
        start, end, offset_tensor, exponent_tensor
    )
    lag_start = start[:, None] - event_times[None, :]
    lag_end = end[:, None] - event_times[None, :]
    available = lag_start > 0
    safe_start = lag_start.clamp_min(0)
    safe_end = lag_end.clamp_min(0)
    secondary_integral = _power_integral(
        safe_start, safe_end, offset_tensor, exponent_tensor
    )
    magnitude_weight = torch.exp(
        alpha * (event_magnitudes - MAGNITUDE_THRESHOLD)
    )
    triggered = (
        secondary_integral * available * magnitude_weight[None, :]
    ).sum(dim=1)
    return (
        primary * primary_integral
        + secondary * triggered
        + background * (end - start)
    )


def _encode_alpha(alpha: float) -> float:
    scaled = alpha / ALPHA_MAX
    return math.log(scaled / (1.0 - scaled))


def fit_excitation_model(
    name: str,
    edges: torch.Tensor,
    observed: torch.Tensor,
    train_mask: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    *,
    offset: float,
    exponent: float,
    background: float,
    initial_primary: float,
) -> ExcitationFit:
    magnitude_weighted = name == "magnitude_weighted"
    if name not in {"magnitude_blind", "magnitude_weighted"}:
        raise ValueError(f"Unknown excitation model: {name}")

    starts = [
        (initial_primary * 0.8, 0.001, 0.5),
        (initial_primary * 0.5, 0.01, 1.0),
        (initial_primary * 0.2, 0.1, 1.5),
        (initial_primary * 0.8, 1.0, 2.0),
    ]

    def expected(theta: torch.Tensor) -> torch.Tensor:
        return excitation_expected_counts(
            theta,
            edges,
            event_times,
            event_magnitudes,
            offset=offset,
            exponent=exponent,
            background=background,
            magnitude_weighted=magnitude_weighted,
        )

    def residual(theta: torch.Tensor) -> torch.Tensor:
        return anscombe_residual(expected(theta)[train_mask], observed[train_mask])

    candidates = []
    for primary, secondary, alpha in starts:
        values = [math.log(primary), math.log(secondary)]
        if magnitude_weighted:
            values.append(_encode_alpha(alpha))
        initial = torch.tensor(values, dtype=DTYPE)
        optimizer = LevenbergMarquardt(residual, initial)
        try:
            theta = optimizer.optimize(max_iter=80, tolerance=1e-8)
            objective = float(residual(theta).square().sum())
        except (RuntimeError, ValueError):
            continue
        if math.isfinite(objective):
            candidates.append((objective, theta, len(optimizer.history)))
    if not candidates:
        raise RuntimeError(f"All KinoPulse excitation fits failed for {name}")

    objective, theta, iterations = min(candidates, key=lambda item: item[0])
    primary, secondary, alpha = decode_excitation(theta, magnitude_weighted)
    parameters = {
        "primary_productivity": float(primary),
        "secondary_productivity": float(secondary),
        "magnitude_alpha": float(alpha),
        "fixed_c_days": offset,
        "fixed_p": exponent,
    }
    return ExcitationFit(
        name=name,
        theta=theta,
        parameters=parameters,
        expected_counts=expected(theta).detach(),
        objective=objective,
        iterations=iterations,
    )


def _metrics(expected: torch.Tensor, observed: torch.Tensor, mask: torch.Tensor) -> dict[str, float]:
    return {
        "poisson_deviance": poisson_deviance(expected[mask], observed[mask]),
        "count_rmse": float(torch.sqrt(torch.mean((expected[mask] - observed[mask]).square()))),
        "observed_total": float(observed[mask].sum()),
        "predicted_total": float(expected[mask].sum()),
    }


def _deviance_terms(expected: torch.Tensor, observed: torch.Tensor) -> torch.Tensor:
    log_term = torch.where(
        observed > 0,
        observed * torch.log(observed / expected.clamp_min(1e-12)),
        torch.zeros_like(observed),
    )
    return 2.0 * (log_term - (observed - expected))


def _sensitivity_case(
    catalog,
    background: float,
    train_bins: int,
    holdout_bins: int,
) -> dict[str, float]:
    edges = make_conditional_bins(train_bins, holdout_bins)
    counts = bin_events(catalog, edges)
    train_mask = edges[1:] <= TRAIN_END_DAYS
    holdout_mask = edges[:-1] >= TRAIN_END_DAYS
    post = catalog.time_days > 0
    static = fit_relaxation_model(
        "omori", edges, counts, train_mask, background
    )
    weighted = fit_excitation_model(
        "magnitude_weighted",
        edges,
        counts,
        train_mask,
        catalog.time_days[post],
        catalog.magnitude[post],
        offset=static.parameters["c_days"],
        exponent=static.parameters["p"],
        background=background,
        initial_primary=static.parameters["productivity"],
    )
    static_score = poisson_deviance(
        static.expected_counts[holdout_mask], counts[holdout_mask]
    )
    weighted_score = poisson_deviance(
        weighted.expected_counts[holdout_mask], counts[holdout_mask]
    )
    return {
        "training_bin_hours": float(
            torch.diff(edges)[train_mask].mean() * 24
        ),
        "holdout_bin_hours": float(
            torch.diff(edges)[holdout_mask].mean() * 24
        ),
        "static_holdout_deviance": static_score,
        "conditional_holdout_deviance": weighted_score,
        "relative_deviance_reduction": (static_score - weighted_score)
        / static_score,
        "static_holdout_total": float(
            static.expected_counts[holdout_mask].sum()
        ),
        "conditional_holdout_total": float(
            weighted.expected_counts[holdout_mask].sum()
        ),
        "magnitude_alpha": weighted.parameters["magnitude_alpha"],
    }


def main(
    data_path: Path = Path("data/ridgecrest_aftershocks.csv"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(data_path)
    edges = make_conditional_bins()
    counts = bin_events(catalog, edges)
    train_mask = edges[1:] <= TRAIN_END_DAYS
    holdout_mask = edges[:-1] >= TRAIN_END_DAYS
    control = (
        (catalog.time_days >= CONTROL_START_DAYS)
        & (catalog.time_days < CONTROL_END_DAYS)
    )
    background = float(control.sum()) / (CONTROL_END_DAYS - CONTROL_START_DAYS)
    post = catalog.time_days > 0
    history_times = catalog.time_days[post]
    history_magnitudes = catalog.magnitude[post]

    static = fit_relaxation_model(
        "omori", edges, counts, train_mask, background
    )
    blind = fit_excitation_model(
        "magnitude_blind",
        edges,
        counts,
        train_mask,
        history_times,
        history_magnitudes,
        offset=static.parameters["c_days"],
        exponent=static.parameters["p"],
        background=background,
        initial_primary=static.parameters["productivity"],
    )
    weighted = fit_excitation_model(
        "magnitude_weighted",
        edges,
        counts,
        train_mask,
        history_times,
        history_magnitudes,
        offset=static.parameters["c_days"],
        exponent=static.parameters["p"],
        background=background,
        initial_primary=static.parameters["productivity"],
    )

    models = {
        "static_omori": {
            "parameters": static.parameters,
            "training": model_metrics(static, counts, train_mask),
            "holdout": model_metrics(static, counts, holdout_mask),
        },
        "magnitude_blind_excitation": {
            "parameters": blind.parameters,
            "training": _metrics(blind.expected_counts, counts, train_mask),
            "holdout": _metrics(blind.expected_counts, counts, holdout_mask),
        },
        "magnitude_weighted_excitation": {
            "parameters": weighted.parameters,
            "training": _metrics(weighted.expected_counts, counts, train_mask),
            "holdout": _metrics(weighted.expected_counts, counts, holdout_mask),
        },
    }
    static_holdout_terms = _deviance_terms(
        static.expected_counts[holdout_mask], counts[holdout_mask]
    )
    weighted_holdout_terms = _deviance_terms(
        weighted.expected_counts[holdout_mask], counts[holdout_mask]
    )
    daily_improvement = (
        static_holdout_terms - weighted_holdout_terms
    ).reshape(23, 4).sum(dim=1)
    static_holdout_score = models["static_omori"]["holdout"][
        "poisson_deviance"
    ]
    weighted_holdout_score = models["magnitude_weighted_excitation"][
        "holdout"
    ]["poisson_deviance"]
    comparison = {
        "absolute_holdout_deviance_reduction": static_holdout_score
        - weighted_holdout_score,
        "relative_holdout_deviance_reduction": (
            static_holdout_score - weighted_holdout_score
        )
        / static_holdout_score,
        "holdout_bins_improved": int(
            (static_holdout_terms > weighted_holdout_terms).sum()
        ),
        "holdout_bins_total": int(holdout_mask.sum()),
        "daily_blocks_improved": int((daily_improvement > 0).sum()),
        "daily_blocks_total": len(daily_improvement),
        "interpretation": "small aggregate gain; not a majority-bin improvement",
    }
    sensitivity = [
        _sensitivity_case(catalog, background, 42, 46),
        {
            "training_bin_hours": float(
                (TRAIN_END_DAYS - MIN_TIME_DAYS) / train_mask.sum() * 24
            ),
            "holdout_bin_hours": float(
                (MAX_TIME_DAYS - TRAIN_END_DAYS) / holdout_mask.sum() * 24
            ),
            "static_holdout_deviance": static_holdout_score,
            "conditional_holdout_deviance": weighted_holdout_score,
            "relative_deviance_reduction": (
                static_holdout_score - weighted_holdout_score
            )
            / static_holdout_score,
            "static_holdout_total": models["static_omori"]["holdout"][
                "predicted_total"
            ],
            "conditional_holdout_total": models[
                "magnitude_weighted_excitation"
            ]["holdout"]["predicted_total"],
            "magnitude_alpha": weighted.parameters["magnitude_alpha"],
        },
        _sensitivity_case(catalog, background, 70, 184),
    ]
    report = {
        "experiment": "online conditional aftershock excitation",
        "prediction_semantics": "each bin uses only catalog events before its start",
        "binning": {
            "training_bins": int(train_mask.sum()),
            "holdout_bins": int(holdout_mask.sum()),
            "training_bin_hours": float((TRAIN_END_DAYS - MIN_TIME_DAYS) / train_mask.sum() * 24),
            "holdout_bin_hours": float((MAX_TIME_DAYS - TRAIN_END_DAYS) / holdout_mask.sum() * 24),
        },
        "models": models,
        "comparison": comparison,
        "binning_sensitivity": sensitivity,
    }
    (output_dir / "aftershock_excitation_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    midpoint = (edges[:-1] + edges[1:]) / 2
    width = torch.diff(edges)
    residual_static = (counts - static.expected_counts) / torch.sqrt(static.expected_counts.clamp_min(1e-12))
    residual_weighted = (counts - weighted.expected_counts) / torch.sqrt(weighted.expected_counts.clamp_min(1e-12))

    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)
    rate_axis, cumulative_axis, residual_axis, score_axis = axes.ravel()
    rate_axis.semilogy(midpoint, (counts / width).clamp_min(0.1), "o", color="#2d3436", markersize=3, label="observed")
    rate_axis.semilogy(midpoint, static.expected_counts / width, color="#6c5ce7", label="static Omori")
    rate_axis.semilogy(midpoint, weighted.expected_counts / width, color="#00b894", label="conditional excitation")
    rate_axis.axvline(TRAIN_END_DAYS, color="#636e72", linestyle=":")
    rate_axis.set(title="Conditional rate", xlabel="days after M7.1", ylabel="M2.5+ events/day")
    rate_axis.legend(frameon=False)
    rate_axis.grid(alpha=0.2)

    observed_cumulative = torch.cat((torch.zeros(1, dtype=DTYPE), torch.cumsum(counts, dim=0)))
    static_cumulative = torch.cat((torch.zeros(1, dtype=DTYPE), torch.cumsum(static.expected_counts, dim=0)))
    weighted_cumulative = torch.cat((torch.zeros(1, dtype=DTYPE), torch.cumsum(weighted.expected_counts, dim=0)))
    cumulative_axis.plot(edges, observed_cumulative, drawstyle="steps-post", color="#2d3436", label="observed")
    cumulative_axis.plot(edges, static_cumulative, color="#6c5ce7", label="static Omori")
    cumulative_axis.plot(edges, weighted_cumulative, color="#00b894", label="conditional excitation")
    cumulative_axis.axvline(TRAIN_END_DAYS, color="#636e72", linestyle=":")
    cumulative_axis.set(title="Cumulative conditional predictions", xlabel="days after M7.1", ylabel="events after first hour")
    cumulative_axis.legend(frameon=False)
    cumulative_axis.grid(alpha=0.2)

    residual_axis.plot(midpoint, residual_static, color="#6c5ce7", alpha=0.7, label="static")
    residual_axis.plot(midpoint, residual_weighted, color="#00b894", alpha=0.9, label="excitation")
    residual_axis.axhline(0, color="#2d3436", linewidth=0.8)
    residual_axis.axhline(2, color="#d63031", linestyle="--", alpha=0.6)
    residual_axis.axhline(-2, color="#d63031", linestyle="--", alpha=0.6)
    residual_axis.axvline(TRAIN_END_DAYS, color="#636e72", linestyle=":")
    residual_axis.set(title="Standardized residuals", xlabel="days after M7.1", ylabel="count surprise")
    residual_axis.legend(frameon=False)
    residual_axis.grid(alpha=0.2)

    labels = ["static\nOmori", "blind\nexcitation", "magnitude\nweighted"]
    train_scores = [
        models["static_omori"]["training"]["poisson_deviance"],
        models["magnitude_blind_excitation"]["training"]["poisson_deviance"],
        models["magnitude_weighted_excitation"]["training"]["poisson_deviance"],
    ]
    holdout_scores = [
        models["static_omori"]["holdout"]["poisson_deviance"],
        models["magnitude_blind_excitation"]["holdout"]["poisson_deviance"],
        models["magnitude_weighted_excitation"]["holdout"]["poisson_deviance"],
    ]
    positions = torch.arange(3, dtype=DTYPE)
    score_axis.bar(positions - 0.18, train_scores, width=0.36, color="#74b9ff", label="training")
    score_axis.bar(positions + 0.18, holdout_scores, width=0.36, color="#fdcb6e", label="holdout")
    score_axis.set_xticks(positions, labels)
    score_axis.set_yscale("log")
    score_axis.set(title="Poisson deviance", ylabel="lower is better")
    score_axis.legend(frameon=False)
    score_axis.grid(alpha=0.2, axis="y")

    fig.suptitle(
        "KinoPulse aftershock exploration - can observed events explain the next interval?"
    )
    fig.savefig(output_dir / "aftershock_excitation_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
