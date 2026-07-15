"""Model the relaxation of the 2019 Ridgecrest aftershock sequence."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.identification.counts import (
    anscombe_residual as kinopulse_anscombe_residual,
    poisson_deviance as kinopulse_poisson_deviance,
)
from kinopulse.identification.parametric import multistart_least_squares
from kinopulse.solvers import solve_ivp

from fetch_ridgecrest import source_url


DTYPE = torch.float64
MAINSHOCK_ID = "ci38457511"
MAINSHOCK_TIME = datetime.fromisoformat("2019-07-06T03:19:53.040+00:00")
MIN_TIME_DAYS = 1.0 / 24.0
TRAIN_END_DAYS = 7.0
MAX_TIME_DAYS = 30.0
CONTROL_START_DAYS = -30.0
CONTROL_END_DAYS = -2.0


@dataclass
class Catalog:
    time_days: torch.Tensor
    magnitude: torch.Tensor
    latitude: torch.Tensor
    longitude: torch.Tensor
    event_ids: list[str]


@dataclass
class FitResult:
    name: str
    theta: torch.Tensor
    parameters: dict[str, float]
    expected_counts: torch.Tensor
    objective: float
    iterations: int


def load_catalog(path: Path = Path("data/ridgecrest_aftershocks.csv")) -> Catalog:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; run `.venv\\Scripts\\python.exe fetch_ridgecrest.py`"
        )

    rows = list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))
    required = {"time", "latitude", "longitude", "mag", "id"}
    if not rows or not required.issubset(rows[0]):
        raise ValueError(f"Expected USGS CSV columns {sorted(required)}")

    selected = []
    for row in rows:
        event_time = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        elapsed = (event_time - MAINSHOCK_TIME).total_seconds() / 86400.0
        if (
            row["id"] != MAINSHOCK_ID
            and CONTROL_START_DAYS <= elapsed <= MAX_TIME_DAYS
        ):
            selected.append(
                (
                    elapsed,
                    float(row["mag"]),
                    float(row["latitude"]),
                    float(row["longitude"]),
                    row["id"],
                )
            )

    if not selected:
        raise ValueError("USGS catalog contains no post-mainshock events")
    values = torch.tensor([item[:4] for item in selected], dtype=DTYPE)
    return Catalog(
        time_days=values[:, 0],
        magnitude=values[:, 1],
        latitude=values[:, 2],
        longitude=values[:, 3],
        event_ids=[item[4] for item in selected],
    )


def make_bins(num_bins: int = 42) -> torch.Tensor:
    log_fraction = math.log(TRAIN_END_DAYS / MIN_TIME_DAYS) / math.log(
        MAX_TIME_DAYS / MIN_TIME_DAYS
    )
    train_bins = max(2, min(num_bins - 2, round(num_bins * log_fraction)))
    holdout_bins = num_bins - train_bins
    training_edges = torch.logspace(
        math.log10(MIN_TIME_DAYS),
        math.log10(TRAIN_END_DAYS),
        train_bins + 1,
        dtype=DTYPE,
    )
    holdout_edges = torch.logspace(
        math.log10(TRAIN_END_DAYS),
        math.log10(MAX_TIME_DAYS),
        holdout_bins + 1,
        dtype=DTYPE,
    )
    return torch.cat((training_edges, holdout_edges[1:]))


def bin_events(catalog: Catalog, edges: torch.Tensor) -> torch.Tensor:
    usable = catalog.time_days[catalog.time_days >= float(edges[0])]
    return torch.histogram(usable, bins=edges).hist.to(dtype=DTYPE)


def _exprel(value: torch.Tensor) -> torch.Tensor:
    safe = torch.where(value.abs() < 1e-7, torch.ones_like(value), value)
    direct = torch.expm1(value) / safe
    series = 1.0 + value / 2.0 + value.square() / 6.0 + value**3 / 24.0
    return torch.where(value.abs() < 1e-4, series, direct)


def decode_omori(theta: torch.Tensor) -> tuple[torch.Tensor, ...]:
    productivity = torch.exp(theta[0])
    offset = torch.exp(theta[1])
    exponent = 0.3 + 1.7 * torch.sigmoid(theta[2])
    return productivity, offset, exponent


def omori_expected_counts(
    theta: torch.Tensor,
    edges: torch.Tensor,
    background: float = 0.0,
) -> torch.Tensor:
    productivity, offset, exponent = decode_omori(theta)
    start, end = edges[:-1], edges[1:]
    log_start = torch.log(start + offset)
    log_ratio = torch.log((end + offset) / (start + offset))
    one_minus_p = 1.0 - exponent
    integral = (
        torch.exp(one_minus_p * log_start)
        * log_ratio
        * _exprel(one_minus_p * log_ratio)
    )
    return productivity * integral + background * (end - start)


def decode_exponential(theta: torch.Tensor) -> tuple[torch.Tensor, ...]:
    return tuple(torch.exp(theta[index]) for index in range(2))


def exponential_expected_counts(
    theta: torch.Tensor,
    edges: torch.Tensor,
    background: float = 0.0,
) -> torch.Tensor:
    initial_rate, timescale = decode_exponential(theta)
    start, end = edges[:-1], edges[1:]
    transient = initial_rate * timescale * (
        torch.exp(-start / timescale) - torch.exp(-end / timescale)
    )
    return transient + background * (end - start)


def anscombe_residual(expected: torch.Tensor, observed: torch.Tensor) -> torch.Tensor:
    """Compatibility orientation for the playground's pre-release residual."""
    return -kinopulse_anscombe_residual(
        expected,
        observed,
        eps=1e-12,
        reduction="none",
    )


def _encode_p(value: float) -> float:
    scaled = (value - 0.3) / 1.7
    return math.log(scaled / (1.0 - scaled))


def fit_relaxation_model(
    name: str,
    edges: torch.Tensor,
    observed: torch.Tensor,
    train_mask: torch.Tensor,
    background: float,
) -> FitResult:
    if name == "omori":
        expected_fn = omori_expected_counts
        starts = [
            (200.0, 0.05, 1.05),
            (100.0, 0.01, 0.80),
            (400.0, 0.20, 1.30),
            (50.0, 0.50, 0.60),
        ]
        initial_thetas = [
            torch.tensor(
                [math.log(k), math.log(c), _encode_p(p)],
                dtype=DTYPE,
            )
            for k, c, p in starts
        ]
    elif name == "exponential":
        expected_fn = exponential_expected_counts
        starts = [
            (2000.0, 0.20),
            (500.0, 1.00),
            (5000.0, 0.05),
        ]
        initial_thetas = [torch.log(torch.tensor(values, dtype=DTYPE)) for values in starts]
    else:
        raise ValueError(f"Unknown relaxation model: {name}")

    def residual(theta: torch.Tensor) -> torch.Tensor:
        return anscombe_residual(
            expected_fn(theta, edges, background)[train_mask], observed[train_mask]
        )

    multistart = multistart_least_squares(
        residual,
        initial_thetas,
        max_iter=100,
        tolerance=1e-9,
        failure_policy="record",
    )
    best = multistart.best.result
    if best is None:  # The result contract makes this unreachable for best.
        raise RuntimeError(f"All KinoPulse fits failed for {name}")
    objective, theta, iterations = best.objective, best.parameters, best.iterations
    if name == "omori":
        values = decode_omori(theta)
        parameters = dict(zip(("productivity", "c_days", "p"), map(float, values)))
    else:
        values = decode_exponential(theta)
        parameters = dict(zip(("initial_rate_per_day", "timescale_days"), map(float, values)))
    return FitResult(
        name=name,
        theta=theta,
        parameters=parameters,
        expected_counts=expected_fn(theta, edges, background).detach(),
        objective=objective,
        iterations=iterations,
    )


def poisson_deviance(expected: torch.Tensor, observed: torch.Tensor) -> float:
    return float(
        kinopulse_poisson_deviance(
            expected,
            observed,
            eps=1e-12,
            reduction="sum",
        )
    )


def integrate_omori(
    fit: FitResult,
    times: torch.Tensor,
    background: float,
) -> torch.Tensor:
    productivity, offset, exponent = decode_omori(fit.theta)

    def dynamics(t, state):
        time = torch.as_tensor(t, dtype=state.dtype, device=state.device)
        rate = productivity / (time + offset) ** exponent + background
        return rate.reshape_as(state)

    requested = times.to(dtype=torch.float32)
    trajectory = solve_ivp(
        dynamics,
        (float(requested[0]), float(requested[-1])),
        torch.zeros(1, dtype=DTYPE),
        t_eval=requested,
        rtol=1e-9,
        atol=1e-11,
    )
    return trajectory.states[:, 0]


def model_metrics(fit: FitResult, observed: torch.Tensor, mask: torch.Tensor) -> dict[str, float]:
    predicted = fit.expected_counts[mask]
    actual = observed[mask]
    return {
        "poisson_deviance": poisson_deviance(predicted, actual),
        "count_rmse": float(torch.sqrt(torch.mean((predicted - actual).square()))),
        "observed_total": float(actual.sum()),
        "predicted_total": float(predicted.sum()),
    }


def main(
    data_path: Path = Path("data/ridgecrest_aftershocks.csv"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog = load_catalog(data_path)
    edges = make_bins()
    counts = bin_events(catalog, edges)
    train_mask = edges[1:] <= TRAIN_END_DAYS
    holdout_mask = ~train_mask
    control_mask = (
        (catalog.time_days >= CONTROL_START_DAYS)
        & (catalog.time_days < CONTROL_END_DAYS)
    )
    background_count = int(control_mask.sum())
    background_duration = CONTROL_END_DAYS - CONTROL_START_DAYS
    background_rate = background_count / background_duration

    omori = fit_relaxation_model(
        "omori", edges, counts, train_mask, background_rate
    )
    exponential = fit_relaxation_model(
        "exponential", edges, counts, train_mask, background_rate
    )

    integrated = integrate_omori(omori, edges, background_rate)
    closed_form_cumulative = torch.cat(
        (torch.zeros(1, dtype=DTYPE), torch.cumsum(omori.expected_counts, dim=0))
    )
    solver_error = float((integrated - closed_form_cumulative).abs().max())

    omori_z = (counts - omori.expected_counts) / torch.sqrt(omori.expected_counts.clamp_min(1e-12))
    top_indices = torch.argsort(omori_z.abs(), descending=True)[:5]
    deviations = [
        {
            "start_day": float(edges[index]),
            "end_day": float(edges[index + 1]),
            "observed": int(counts[index]),
            "expected": float(omori.expected_counts[index]),
            "standardized_residual": float(omori_z[index]),
        }
        for index in top_indices
    ]
    large = torch.where((catalog.time_days > 0) & (catalog.magnitude >= 4.5))[0]
    large_events = [
        {
            "day": float(catalog.time_days[index]),
            "magnitude": float(catalog.magnitude[index]),
            "event_id": catalog.event_ids[index],
        }
        for index in large
    ]

    binning_sensitivity = []
    for num_bins in (32, 42, 52):
        if num_bins == 42:
            sensitivity_edges, sensitivity_counts = edges, counts
            sensitivity_omori, sensitivity_exponential = omori, exponential
        else:
            sensitivity_edges = make_bins(num_bins)
            sensitivity_counts = bin_events(catalog, sensitivity_edges)
            sensitivity_train = sensitivity_edges[1:] <= TRAIN_END_DAYS
            sensitivity_omori = fit_relaxation_model(
                "omori",
                sensitivity_edges,
                sensitivity_counts,
                sensitivity_train,
                background_rate,
            )
            sensitivity_exponential = fit_relaxation_model(
                "exponential",
                sensitivity_edges,
                sensitivity_counts,
                sensitivity_train,
                background_rate,
            )
        sensitivity_holdout = sensitivity_edges[:-1] >= TRAIN_END_DAYS
        binning_sensitivity.append(
            {
                "bins": num_bins,
                "omori_p": sensitivity_omori.parameters["p"],
                "omori_c_days": sensitivity_omori.parameters["c_days"],
                "holdout_observed": int(sensitivity_counts[sensitivity_holdout].sum()),
                "holdout_omori_predicted": float(
                    sensitivity_omori.expected_counts[sensitivity_holdout].sum()
                ),
                "holdout_omori_deviance": poisson_deviance(
                    sensitivity_omori.expected_counts[sensitivity_holdout],
                    sensitivity_counts[sensitivity_holdout],
                ),
                "holdout_exponential_deviance": poisson_deviance(
                    sensitivity_exponential.expected_counts[sensitivity_holdout],
                    sensitivity_counts[sensitivity_holdout],
                ),
            }
        )

    report = {
        "experiment": "Ridgecrest aftershock relaxation",
        "source": source_url(),
        "source_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "mainshock_event_id": MAINSHOCK_ID,
        "catalog_events_excluding_mainshock": len(catalog.event_ids),
        "post_mainshock_catalog_events": int((catalog.time_days > 0).sum()),
        "events_used_after_first_hour": int(counts.sum()),
        "magnitude_threshold": 2.5,
        "radius_km": 100,
        "training_days": [MIN_TIME_DAYS, TRAIN_END_DAYS],
        "holdout_days": [TRAIN_END_DAYS, MAX_TIME_DAYS],
        "background_control_days": [CONTROL_START_DAYS, CONTROL_END_DAYS],
        "background_control_events": background_count,
        "fixed_background_rate_per_day": background_rate,
        "omori": {
            "parameters": omori.parameters,
            "fit_objective": omori.objective,
            "optimizer_history_points": omori.iterations,
            "training": model_metrics(omori, counts, train_mask),
            "holdout": model_metrics(omori, counts, holdout_mask),
        },
        "exponential": {
            "parameters": exponential.parameters,
            "fit_objective": exponential.objective,
            "optimizer_history_points": exponential.iterations,
            "training": model_metrics(exponential, counts, train_mask),
            "holdout": model_metrics(exponential, counts, holdout_mask),
        },
        "kinopulse_solver_max_cumulative_error": solver_error,
        "binning_sensitivity": binning_sensitivity,
        "largest_omori_bin_deviations": deviations,
        "magnitude_4_5_or_larger_aftershocks": large_events,
    }
    (output_dir / "aftershock_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    midpoint = torch.sqrt(edges[:-1] * edges[1:])
    width = torch.diff(edges)
    observed_rate = counts / width
    omori_rate = omori.expected_counts / width
    exponential_rate = exponential.expected_counts / width
    observed_cumulative = torch.cat((torch.zeros(1, dtype=DTYPE), torch.cumsum(counts, dim=0)))

    fig, axes = plt.subplots(2, 2, figsize=(12, 9), constrained_layout=True)
    map_axis, rate_axis, cumulative_axis, residual_axis = axes.ravel()
    post = catalog.time_days > 0
    scatter = map_axis.scatter(
        catalog.longitude[post],
        catalog.latitude[post],
        c=torch.log10(catalog.time_days[post].clamp_min(1e-4)),
        s=(catalog.magnitude[post].clamp_min(2.5) - 2.2).square() * 7,
        cmap="viridis",
        alpha=0.65,
        linewidths=0,
    )
    map_axis.scatter([-117.5993333], [35.7695], marker="*", s=150, color="#d63031", label="M7.1 mainshock")
    map_axis.set(title="Catalog geometry", xlabel="longitude", ylabel="latitude")
    map_axis.legend(frameon=False)
    colorbar = fig.colorbar(scatter, ax=map_axis, pad=0.02)
    colorbar.set_label("log10 days after mainshock")

    rate_axis.loglog(midpoint, observed_rate.clamp_min(0.1), "o", color="#2d3436", markersize=4, label="USGS binned rate")
    rate_axis.loglog(midpoint, omori_rate, color="#6c5ce7", linewidth=2, label="Omori fit")
    rate_axis.loglog(midpoint, exponential_rate, color="#e17055", linestyle="--", linewidth=2, label="exponential fit")
    rate_axis.axvline(TRAIN_END_DAYS, color="#636e72", linestyle=":", label="holdout begins")
    rate_axis.set(title="Relaxation law", xlabel="days after mainshock", ylabel="M2.5+ events/day")
    rate_axis.legend(frameon=False)
    rate_axis.grid(alpha=0.2, which="both")

    cumulative_axis.semilogx(edges, observed_cumulative, drawstyle="steps-post", color="#2d3436", label="observed")
    cumulative_axis.semilogx(edges, closed_form_cumulative, color="#6c5ce7", linewidth=2, label="Omori")
    exponential_cumulative = torch.cat((torch.zeros(1, dtype=DTYPE), torch.cumsum(exponential.expected_counts, dim=0)))
    cumulative_axis.semilogx(edges, exponential_cumulative, color="#e17055", linestyle="--", linewidth=2, label="exponential")
    cumulative_axis.axvline(TRAIN_END_DAYS, color="#636e72", linestyle=":")
    cumulative_axis.set(title="Cumulative aftershocks", xlabel="days after mainshock", ylabel="events after first hour")
    cumulative_axis.legend(frameon=False)
    cumulative_axis.grid(alpha=0.2, which="both")

    residual_axis.semilogx(midpoint, omori_z, marker="o", color="#0984e3", linewidth=1)
    residual_axis.axhline(0, color="#2d3436", linewidth=0.8)
    residual_axis.axhline(2, color="#d63031", linestyle="--", alpha=0.7)
    residual_axis.axhline(-2, color="#d63031", linestyle="--", alpha=0.7)
    residual_axis.axvline(TRAIN_END_DAYS, color="#636e72", linestyle=":")
    for index in large:
        event_day = float(catalog.time_days[index])
        if event_day >= MIN_TIME_DAYS:
            residual_axis.axvline(event_day, color="#fdcb6e", alpha=0.35, linewidth=1)
    residual_axis.set_xlim(float(edges[0]), float(edges[-1]))
    residual_axis.set(title="Where Omori is surprised", xlabel="days after mainshock", ylabel="(observed - expected) / sqrt(expected)")
    residual_axis.grid(alpha=0.2, which="both")

    fig.suptitle("KinoPulse real-data exploration · memory after the 2019 Ridgecrest M7.1 earthquake")
    fig.savefig(output_dir / "aftershock_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
