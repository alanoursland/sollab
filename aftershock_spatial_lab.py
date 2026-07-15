"""Test whether along-strike event history improves Ridgecrest nowcasts."""

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

from aftershock_excitation_lab import (
    ALPHA_MAX,
    MAGNITUDE_THRESHOLD,
    _deviance_terms,
    _encode_alpha,
    _power_integral,
    fit_excitation_model,
    make_conditional_bins,
)
from aftershock_lab import (
    CONTROL_END_DAYS,
    CONTROL_START_DAYS,
    DTYPE,
    TRAIN_END_DAYS,
    anscombe_residual,
    bin_events,
    fit_relaxation_model,
    load_catalog,
    poisson_deviance,
)


MAINSHOCK_LATITUDE = 35.7695
MAINSHOCK_LONGITUDE = -117.5993333
EARTH_KM_PER_DEGREE = 111.32
SPATIAL_REGIONS = 5
SIGMA_MIN_KM = 0.5
SIGMA_MAX_KM = 60.0
TAU_MIN_DAYS = 0.02
TAU_MAX_DAYS = 10.0


@dataclass
class SpatialFrame:
    x_km: torch.Tensor
    y_km: torch.Tensor
    along_km: torch.Tensor
    across_km: torch.Tensor
    center_km: torch.Tensor
    along_axis: torch.Tensor
    boundaries_km: torch.Tensor
    region_centers_km: torch.Tensor
    regions: torch.Tensor
    base_probabilities: torch.Tensor


@dataclass
class SpatialFit:
    theta: torch.Tensor
    parameters: dict[str, float]
    expected_counts: torch.Tensor
    objective: float
    iterations: int


@dataclass
class AllocationFit:
    theta: torch.Tensor
    parameters: dict[str, float]
    probabilities: torch.Tensor
    objective: float
    iterations: int


@dataclass
class StateAllocationFit:
    theta: torch.Tensor
    parameters: dict[str, float]
    probabilities: torch.Tensor
    objective: float
    iterations: int


def build_spatial_frame(catalog) -> SpatialFrame:
    longitude_scale = EARTH_KM_PER_DEGREE * math.cos(
        math.radians(MAINSHOCK_LATITUDE)
    )
    x_km = (catalog.longitude - MAINSHOCK_LONGITUDE) * longitude_scale
    y_km = (catalog.latitude - MAINSHOCK_LATITUDE) * EARTH_KM_PER_DEGREE
    coordinates = torch.stack((x_km, y_km), dim=1)
    training = (
        (catalog.time_days >= float(make_conditional_bins()[0]))
        & (catalog.time_days < TRAIN_END_DAYS)
    )
    center = coordinates[training].mean(dim=0)
    _, _, right_vectors = torch.linalg.svd(
        coordinates[training] - center, full_matrices=False
    )
    along_axis = right_vectors[0]
    if float(along_axis[1]) > 0:
        along_axis = -along_axis
    across_axis = torch.stack((-along_axis[1], along_axis[0]))
    centered = coordinates - center
    along = centered @ along_axis
    across = centered @ across_axis
    quantiles = torch.linspace(0.0, 1.0, SPATIAL_REGIONS + 1, dtype=DTYPE)
    boundaries = torch.quantile(along[training], quantiles)[1:-1]
    regions = torch.bucketize(along, boundaries)
    region_centers = torch.stack(
        [along[training & (regions == index)].mean() for index in range(SPATIAL_REGIONS)]
    )
    training_counts = torch.bincount(
        regions[training], minlength=SPATIAL_REGIONS
    ).to(dtype=DTYPE)
    base_probabilities = training_counts / training_counts.sum()
    return SpatialFrame(
        x_km=x_km,
        y_km=y_km,
        along_km=along,
        across_km=across,
        center_km=center,
        along_axis=along_axis,
        boundaries_km=boundaries,
        region_centers_km=region_centers,
        regions=regions,
        base_probabilities=base_probabilities,
    )


def binned_region_counts(
    times: torch.Tensor,
    regions: torch.Tensor,
    edges: torch.Tensor,
) -> torch.Tensor:
    result = torch.zeros(
        (len(edges) - 1, SPATIAL_REGIONS), dtype=DTYPE
    )
    valid = (times >= edges[0]) & (times < edges[-1])
    time_bins = torch.bucketize(times[valid], edges, right=True) - 1
    flat_indices = time_bins * SPATIAL_REGIONS + regions[valid]
    result.view(-1).index_add_(
        0, flat_indices, torch.ones_like(flat_indices, dtype=DTYPE)
    )
    return result


def decode_spatial_parameters(
    theta: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    primary = torch.exp(theta[0])
    secondary = torch.exp(theta[1])
    alpha = ALPHA_MAX * torch.sigmoid(theta[2])
    sigma = SIGMA_MIN_KM + (SIGMA_MAX_KM - SIGMA_MIN_KM) * torch.sigmoid(
        theta[3]
    )
    return primary, secondary, alpha, sigma


def _encode_sigma(sigma_km: float) -> float:
    scaled = (sigma_km - SIGMA_MIN_KM) / (SIGMA_MAX_KM - SIGMA_MIN_KM)
    return math.log(scaled / (1.0 - scaled))


def spatial_expected_counts(
    theta: torch.Tensor,
    edges: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    event_along_km: torch.Tensor,
    region_centers_km: torch.Tensor,
    base_probabilities: torch.Tensor,
    *,
    offset: float,
    exponent: float,
    background: float,
) -> torch.Tensor:
    primary, secondary, alpha, sigma = decode_spatial_parameters(theta)
    start, end = edges[:-1], edges[1:]
    offset_tensor = theta.new_tensor(offset)
    exponent_tensor = theta.new_tensor(exponent)
    primary_integral = _power_integral(
        start, end, offset_tensor, exponent_tensor
    )

    lag_start = start[:, None] - event_times[None, :]
    lag_end = end[:, None] - event_times[None, :]
    available = lag_start > 0
    temporal_integral = _power_integral(
        lag_start.clamp_min(0),
        lag_end.clamp_min(0),
        offset_tensor,
        exponent_tensor,
    )
    magnitude_weight = torch.exp(
        alpha * (event_magnitudes - MAGNITUDE_THRESHOLD)
    )
    event_mass = temporal_integral * available * magnitude_weight[None, :]
    spatial_logits = -(
        event_along_km[:, None] - region_centers_km[None, :]
    ).square() / (2.0 * sigma.square())
    event_region_probability = torch.softmax(spatial_logits, dim=1)
    triggered = event_mass @ event_region_probability
    baseline = (
        primary * primary_integral + background * (end - start)
    )[:, None] * base_probabilities[None, :]
    return baseline + secondary * triggered


def fit_spatial_model(
    edges: torch.Tensor,
    observed: torch.Tensor,
    train_mask: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    event_along_km: torch.Tensor,
    frame: SpatialFrame,
    *,
    offset: float,
    exponent: float,
    background: float,
    initial_primary: float,
) -> SpatialFit:
    starts = [
        (initial_primary * 0.8, 0.001, 2.0, 8.0),
        (initial_primary * 0.4, 0.02, 2.5, 16.0),
    ]

    def expected(theta: torch.Tensor) -> torch.Tensor:
        return spatial_expected_counts(
            theta,
            edges,
            event_times,
            event_magnitudes,
            event_along_km,
            frame.region_centers_km,
            frame.base_probabilities,
            offset=offset,
            exponent=exponent,
            background=background,
        )

    def residual(theta: torch.Tensor) -> torch.Tensor:
        return anscombe_residual(
            expected(theta)[train_mask].reshape(-1),
            observed[train_mask].reshape(-1),
        )

    candidates = []
    for primary, secondary, alpha, sigma in starts:
        initial = torch.tensor(
            [
                math.log(primary),
                math.log(secondary),
                _encode_alpha(alpha),
                _encode_sigma(sigma),
            ],
            dtype=DTYPE,
        )
        optimizer = LevenbergMarquardt(residual, initial)
        try:
            theta = optimizer.optimize(max_iter=60, tolerance=1e-8)
            objective = float(residual(theta).square().sum())
        except (RuntimeError, ValueError):
            continue
        if math.isfinite(objective):
            candidates.append((objective, theta, len(optimizer.history)))
    if not candidates:
        raise RuntimeError("All KinoPulse spatial excitation fits failed")

    objective, theta, iterations = min(candidates, key=lambda item: item[0])
    primary, secondary, alpha, sigma = decode_spatial_parameters(theta)
    return SpatialFit(
        theta=theta,
        parameters={
            "primary_productivity": float(primary),
            "secondary_productivity": float(secondary),
            "magnitude_alpha": float(alpha),
            "along_strike_sigma_km": float(sigma),
            "fixed_c_days": offset,
            "fixed_p": exponent,
        },
        expected_counts=expected(theta).detach(),
        objective=objective,
        iterations=iterations,
    )


def decode_allocation_parameters(
    theta: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    history_fraction = torch.sigmoid(theta[0])
    alpha = ALPHA_MAX * torch.sigmoid(theta[1])
    sigma = SIGMA_MIN_KM + (SIGMA_MAX_KM - SIGMA_MIN_KM) * torch.sigmoid(
        theta[2]
    )
    return history_fraction, alpha, sigma


def _logit(value: float) -> float:
    return math.log(value / (1.0 - value))


def allocation_probabilities(
    theta: torch.Tensor,
    edges: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    event_along_km: torch.Tensor,
    region_centers_km: torch.Tensor,
    base_probabilities: torch.Tensor,
    *,
    offset: float,
    exponent: float,
) -> torch.Tensor:
    history_fraction, alpha, sigma = decode_allocation_parameters(theta)
    start, end = edges[:-1], edges[1:]
    offset_tensor = theta.new_tensor(offset)
    exponent_tensor = theta.new_tensor(exponent)
    lag_start = start[:, None] - event_times[None, :]
    lag_end = end[:, None] - event_times[None, :]
    available = lag_start > 0
    temporal_integral = _power_integral(
        lag_start.clamp_min(0),
        lag_end.clamp_min(0),
        offset_tensor,
        exponent_tensor,
    )
    event_mass = (
        temporal_integral
        * available
        * torch.exp(
            alpha * (event_magnitudes - MAGNITUDE_THRESHOLD)
        )[None, :]
    )
    spatial_logits = -(
        event_along_km[:, None] - region_centers_km[None, :]
    ).square() / (2.0 * sigma.square())
    excited_mass = event_mass @ torch.softmax(spatial_logits, dim=1)
    excited_total = excited_mass.sum(dim=1, keepdim=True)
    excited_probability = torch.where(
        excited_total > 0,
        excited_mass / excited_total.clamp_min(1e-12),
        base_probabilities[None, :],
    )
    return (
        (1.0 - history_fraction) * base_probabilities[None, :]
        + history_fraction * excited_probability
    )


def fit_allocation_model(
    edges: torch.Tensor,
    observed: torch.Tensor,
    train_mask: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    event_along_km: torch.Tensor,
    frame: SpatialFrame,
    *,
    offset: float,
    exponent: float,
) -> AllocationFit:
    starts = [
        (0.4, 0.2, 8.0),
        (0.7, 2.0, 16.0),
    ]

    def probabilities(theta: torch.Tensor) -> torch.Tensor:
        return allocation_probabilities(
            theta,
            edges,
            event_times,
            event_magnitudes,
            event_along_km,
            frame.region_centers_km,
            frame.base_probabilities,
            offset=offset,
            exponent=exponent,
        )

    observed_total = observed.sum(dim=1, keepdim=True)

    def residual(theta: torch.Tensor) -> torch.Tensor:
        conditional_expected = observed_total * probabilities(theta)
        return anscombe_residual(
            conditional_expected[train_mask].reshape(-1),
            observed[train_mask].reshape(-1),
        )

    candidates = []
    for history_fraction, alpha, sigma in starts:
        initial = torch.tensor(
            [
                _logit(history_fraction),
                _encode_alpha(alpha),
                _encode_sigma(sigma),
            ],
            dtype=DTYPE,
        )
        optimizer = LevenbergMarquardt(residual, initial)
        try:
            theta = optimizer.optimize(max_iter=60, tolerance=1e-8)
            objective = float(residual(theta).square().sum())
        except (RuntimeError, ValueError):
            continue
        if math.isfinite(objective):
            candidates.append((objective, theta, len(optimizer.history)))
    if not candidates:
        raise RuntimeError("All KinoPulse spatial-allocation fits failed")

    objective, theta, iterations = min(candidates, key=lambda item: item[0])
    history_fraction, alpha, sigma = decode_allocation_parameters(theta)
    return AllocationFit(
        theta=theta,
        parameters={
            "history_fraction": float(history_fraction),
            "magnitude_alpha": float(alpha),
            "along_strike_sigma_km": float(sigma),
            "fixed_c_days": offset,
            "fixed_p": exponent,
        },
        probabilities=probabilities(theta).detach(),
        objective=objective,
        iterations=iterations,
    )


def decode_state_parameters(
    theta: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    history_fraction = torch.sigmoid(theta[0])
    alpha = ALPHA_MAX * torch.sigmoid(theta[1])
    sigma = SIGMA_MIN_KM + (SIGMA_MAX_KM - SIGMA_MIN_KM) * torch.sigmoid(
        theta[2]
    )
    tau = TAU_MIN_DAYS + (TAU_MAX_DAYS - TAU_MIN_DAYS) * torch.sigmoid(
        theta[3]
    )
    return history_fraction, alpha, sigma, tau


def _encode_tau(tau_days: float) -> float:
    scaled = (tau_days - TAU_MIN_DAYS) / (TAU_MAX_DAYS - TAU_MIN_DAYS)
    return math.log(scaled / (1.0 - scaled))


def state_allocation_probabilities(
    theta: torch.Tensor,
    edges: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    event_along_km: torch.Tensor,
    region_centers_km: torch.Tensor,
    base_probabilities: torch.Tensor,
) -> torch.Tensor:
    history_fraction, alpha, sigma, tau = decode_state_parameters(theta)
    start = edges[:-1]
    lag = start[:, None] - event_times[None, :]
    available = lag > 0
    event_mass = (
        torch.exp(-lag.clamp_min(0) / tau)
        * available
        * torch.exp(
            alpha * (event_magnitudes - MAGNITUDE_THRESHOLD)
        )[None, :]
    )
    spatial_logits = -(
        event_along_km[:, None] - region_centers_km[None, :]
    ).square() / (2.0 * sigma.square())
    state_mass = event_mass @ torch.softmax(spatial_logits, dim=1)
    state_total = state_mass.sum(dim=1, keepdim=True)
    state_probability = torch.where(
        state_total > 0,
        state_mass / state_total.clamp_min(1e-12),
        base_probabilities[None, :],
    )
    return (
        (1.0 - history_fraction) * base_probabilities[None, :]
        + history_fraction * state_probability
    )


def fit_state_allocation_model(
    edges: torch.Tensor,
    observed: torch.Tensor,
    train_mask: torch.Tensor,
    event_times: torch.Tensor,
    event_magnitudes: torch.Tensor,
    event_along_km: torch.Tensor,
    frame: SpatialFrame,
) -> StateAllocationFit:
    starts = [
        (0.4, 1.5, 8.0, 0.12),
        (0.7, 2.0, 16.0, 1.0),
    ]

    def probabilities(theta: torch.Tensor) -> torch.Tensor:
        return state_allocation_probabilities(
            theta,
            edges,
            event_times,
            event_magnitudes,
            event_along_km,
            frame.region_centers_km,
            frame.base_probabilities,
        )

    observed_total = observed.sum(dim=1, keepdim=True)

    def residual(theta: torch.Tensor) -> torch.Tensor:
        conditional_expected = observed_total * probabilities(theta)
        return anscombe_residual(
            conditional_expected[train_mask].reshape(-1),
            observed[train_mask].reshape(-1),
        )

    candidates = []
    for history_fraction, alpha, sigma, tau in starts:
        initial = torch.tensor(
            [
                _logit(history_fraction),
                _encode_alpha(alpha),
                _encode_sigma(sigma),
                _encode_tau(tau),
            ],
            dtype=DTYPE,
        )
        optimizer = LevenbergMarquardt(residual, initial)
        try:
            theta = optimizer.optimize(max_iter=60, tolerance=1e-8)
            objective = float(residual(theta).square().sum())
        except (RuntimeError, ValueError):
            continue
        if math.isfinite(objective):
            candidates.append((objective, theta, len(optimizer.history)))
    if not candidates:
        raise RuntimeError("All KinoPulse spatial-state fits failed")

    objective, theta, iterations = min(candidates, key=lambda item: item[0])
    history_fraction, alpha, sigma, tau = decode_state_parameters(theta)
    return StateAllocationFit(
        theta=theta,
        parameters={
            "history_fraction": float(history_fraction),
            "magnitude_alpha": float(alpha),
            "along_strike_sigma_km": float(sigma),
            "memory_tau_days": float(tau),
        },
        probabilities=probabilities(theta).detach(),
        objective=objective,
        iterations=iterations,
    )


def score_space_time(
    expected: torch.Tensor,
    observed: torch.Tensor,
    mask: torch.Tensor,
) -> dict[str, float | list[float]]:
    expected_selected = expected[mask]
    observed_selected = observed[mask]
    expected_total = expected_selected.sum(dim=1)
    observed_total = observed_selected.sum(dim=1)
    conditional_expected = (
        expected_selected
        / expected_total.clamp_min(1e-12)[:, None]
        * observed_total[:, None]
    )
    return {
        "joint_poisson_deviance": poisson_deviance(
            expected_selected.reshape(-1), observed_selected.reshape(-1)
        ),
        "temporal_poisson_deviance": poisson_deviance(
            expected_total, observed_total
        ),
        "conditional_spatial_deviance": poisson_deviance(
            conditional_expected.reshape(-1), observed_selected.reshape(-1)
        ),
        "count_rmse": float(
            torch.sqrt(
                torch.mean((expected_selected - observed_selected).square())
            )
        ),
        "predicted_by_region": expected_selected.sum(dim=0).tolist(),
        "observed_by_region": observed_selected.sum(dim=0).tolist(),
    }


def main(
    data_path: Path = Path("data/ridgecrest_aftershocks.csv"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(data_path)
    edges = make_conditional_bins()
    train_mask = edges[1:] <= TRAIN_END_DAYS
    holdout_mask = edges[:-1] >= TRAIN_END_DAYS
    temporal_counts = bin_events(catalog, edges)
    frame = build_spatial_frame(catalog)
    observed = binned_region_counts(catalog.time_days, frame.regions, edges)
    control = (
        (catalog.time_days >= CONTROL_START_DAYS)
        & (catalog.time_days < CONTROL_END_DAYS)
    )
    background = float(control.sum()) / (CONTROL_END_DAYS - CONTROL_START_DAYS)
    post = catalog.time_days > 0

    static = fit_relaxation_model(
        "omori", edges, temporal_counts, train_mask, background
    )
    temporal = fit_excitation_model(
        "magnitude_weighted",
        edges,
        temporal_counts,
        train_mask,
        catalog.time_days[post],
        catalog.magnitude[post],
        offset=static.parameters["c_days"],
        exponent=static.parameters["p"],
        background=background,
        initial_primary=static.parameters["productivity"],
    )
    spatial = fit_spatial_model(
        edges,
        observed,
        train_mask,
        catalog.time_days[post],
        catalog.magnitude[post],
        frame.along_km[post],
        frame,
        offset=static.parameters["c_days"],
        exponent=static.parameters["p"],
        background=background,
        initial_primary=static.parameters["productivity"],
    )
    allocation = fit_allocation_model(
        edges,
        observed,
        train_mask,
        catalog.time_days[post],
        catalog.magnitude[post],
        frame.along_km[post],
        frame,
        offset=static.parameters["c_days"],
        exponent=static.parameters["p"],
    )
    state_allocation = fit_state_allocation_model(
        edges,
        observed,
        train_mask,
        catalog.time_days[post],
        catalog.magnitude[post],
        frame.along_km[post],
        frame,
    )

    static_space = static.expected_counts[:, None] * frame.base_probabilities
    temporal_space = temporal.expected_counts[:, None] * frame.base_probabilities
    allocation_space = temporal.expected_counts[:, None] * allocation.probabilities
    state_space = (
        temporal.expected_counts[:, None] * state_allocation.probabilities
    )
    models = {
        "static_omori": {
            "parameters": static.parameters,
            "training": score_space_time(static_space, observed, train_mask),
            "holdout": score_space_time(static_space, observed, holdout_mask),
        },
        "temporal_excitation": {
            "parameters": temporal.parameters,
            "training": score_space_time(temporal_space, observed, train_mask),
            "holdout": score_space_time(temporal_space, observed, holdout_mask),
        },
        "spatial_excitation": {
            "parameters": spatial.parameters,
            "training": score_space_time(
                spatial.expected_counts, observed, train_mask
            ),
            "holdout": score_space_time(
                spatial.expected_counts, observed, holdout_mask
            ),
        },
        "adaptive_spatial_allocation": {
            "parameters": allocation.parameters,
            "training": score_space_time(
                allocation_space, observed, train_mask
            ),
            "holdout": score_space_time(
                allocation_space, observed, holdout_mask
            ),
        },
        "latent_spatial_state": {
            "parameters": state_allocation.parameters,
            "training": score_space_time(state_space, observed, train_mask),
            "holdout": score_space_time(state_space, observed, holdout_mask),
        },
    }
    report = {
        "experiment": "causal along-strike aftershock excitation",
        "prediction_semantics": "each cell-bin uses only events before its start",
        "spatial_frame": {
            "training_only_pca": True,
            "regions": SPATIAL_REGIONS,
            "along_axis_xy": frame.along_axis.tolist(),
            "boundaries_km": frame.boundaries_km.tolist(),
            "region_centers_km": frame.region_centers_km.tolist(),
            "training_probabilities": frame.base_probabilities.tolist(),
            "training_along_std_km": float(
                frame.along_km[
                    (catalog.time_days >= edges[0])
                    & (catalog.time_days < TRAIN_END_DAYS)
                ].std()
            ),
        },
        "models": models,
    }
    (output_dir / "aftershock_spatial_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    colors = ["#6c5ce7", "#0984e3", "#00b894", "#fdcb6e", "#e17055"]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)
    geometry_axis, region_axis, residual_axis, score_axis = axes.ravel()
    training_events = (
        (catalog.time_days >= edges[0]) & (catalog.time_days < TRAIN_END_DAYS)
    )
    holdout_events = (
        (catalog.time_days >= TRAIN_END_DAYS) & (catalog.time_days < edges[-1])
    )
    for region, color in enumerate(colors):
        train_region = training_events & (frame.regions == region)
        hold_region = holdout_events & (frame.regions == region)
        geometry_axis.scatter(
            frame.along_km[train_region],
            frame.across_km[train_region],
            s=5,
            color=color,
            alpha=0.2,
        )
        geometry_axis.scatter(
            frame.along_km[hold_region],
            frame.across_km[hold_region],
            s=10,
            facecolors="none",
            edgecolors=color,
            linewidths=0.6,
        )
    for boundary in frame.boundaries_km:
        geometry_axis.axvline(float(boundary), color="#636e72", alpha=0.4)
    geometry_axis.set(
        title="Training PCA rupture coordinates",
        xlabel="along strike (km)",
        ylabel="across strike (km)",
    )
    geometry_axis.grid(alpha=0.15)

    positions = torch.arange(SPATIAL_REGIONS, dtype=DTYPE)
    observed_by_region = observed[holdout_mask].sum(dim=0)
    region_axis.bar(
        positions - 0.25,
        observed_by_region,
        width=0.25,
        color="#2d3436",
        label="observed",
    )
    region_axis.bar(
        positions,
        temporal_space[holdout_mask].sum(dim=0),
        width=0.25,
        color="#74b9ff",
        label="time only",
    )
    region_axis.bar(
        positions + 0.25,
        state_space[holdout_mask].sum(dim=0),
        width=0.25,
        color="#00b894",
        label="latent state",
    )
    region_axis.set(
        title="Held-out events by along-strike region",
        xlabel="region from one rupture end to the other",
        ylabel="M2.5+ events",
    )
    region_axis.set_xticks(positions, [str(i + 1) for i in range(SPATIAL_REGIONS)])
    region_axis.legend(frameon=False)
    region_axis.grid(alpha=0.2, axis="y")

    temporal_terms = _deviance_terms(
        temporal_space[holdout_mask], observed[holdout_mask]
    )
    spatial_terms = _deviance_terms(
        state_space[holdout_mask], observed[holdout_mask]
    )
    improvement = (temporal_terms - spatial_terms).T
    image = residual_axis.imshow(
        improvement,
        aspect="auto",
        cmap="RdBu_r",
        vmin=-float(improvement.abs().quantile(0.95)),
        vmax=float(improvement.abs().quantile(0.95)),
        extent=(TRAIN_END_DAYS, float(edges[-1]), 5.5, 0.5),
    )
    residual_axis.set(
        title="Local deviance improvement (red = spatial wins)",
        xlabel="days after M7.1",
        ylabel="along-strike region",
        yticks=positions + 1,
    )
    fig.colorbar(image, ax=residual_axis, label="time-only minus spatial")

    labels = ["static", "time only", "coupled", "adaptive", "state"]
    model_names = (
        "static_omori",
        "temporal_excitation",
        "spatial_excitation",
        "adaptive_spatial_allocation",
        "latent_spatial_state",
    )
    joint_scores = [
        models[name]["holdout"]["joint_poisson_deviance"]
        for name in model_names
    ]
    spatial_scores = [
        models[name]["holdout"]["conditional_spatial_deviance"]
        for name in model_names
    ]
    score_axis.bar(
        positions - 0.18,
        joint_scores,
        width=0.36,
        color="#6c5ce7",
        label="joint space-time",
    )
    score_axis.bar(
        positions + 0.18,
        spatial_scores,
        width=0.36,
        color="#fdcb6e",
        label="location given time",
    )
    score_axis.set_xticks(positions, labels)
    score_axis.set(
        title="Held-out Poisson deviance",
        ylabel="lower is better",
    )
    score_axis.legend(frameon=False)
    score_axis.grid(alpha=0.2, axis="y")

    fig.suptitle(
        "KinoPulse Ridgecrest exploration - does spatial memory predict the next region?"
    )
    fig.savefig(output_dir / "aftershock_spatial_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
