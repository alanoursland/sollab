"""Exercise KinoPulse 0.1.0.dev2026071512 against small analytical oracles."""

from __future__ import annotations

import json
import math
from importlib.metadata import version
from pathlib import Path

import torch

from kinopulse.identification.counts import (
    anscombe_residual,
    expected_counts_from_compensator,
    integrate_rate,
    poisson_deviance,
    poisson_deviance_residual,
    poisson_log_likelihood,
)
from kinopulse.identification.parametric import (
    LevenbergMarquardt,
    ResidualStack,
    estimate_nonlinear_covariance,
    multistart_least_squares,
)
from kinopulse.stochastic import TemporalPointProcess


DTYPE = torch.float64


def _manual_poisson_log_likelihood(expected: torch.Tensor, observed: torch.Tensor) -> torch.Tensor:
    return (
        observed * torch.log(expected)
        - expected
        - torch.lgamma(observed + 1.0)
    ).sum()


def _homogeneous_process(rate: float) -> TemporalPointProcess:
    def intensity(times: torch.Tensor, history: torch.Tensor, params) -> torch.Tensor:
        del history, params
        return torch.full_like(times, rate)

    def compensator(times: torch.Tensor, history: torch.Tensor, params) -> torch.Tensor:
        del history, params
        return rate * times

    return TemporalPointProcess(intensity, compensator, homogeneous=True)


def _exponential_hawkes_process(mu: float, alpha: float, beta: float) -> TemporalPointProcess:
    def intensity(times: torch.Tensor, history: torch.Tensor, params) -> torch.Tensor:
        del params
        if history.numel() == 0:
            return torch.full_like(times, mu)
        lags = times[:, None] - history[None, :]
        excitation = torch.where(
            lags > 0,
            alpha * torch.exp(-beta * lags),
            torch.zeros_like(lags),
        )
        return mu + excitation.sum(dim=1)

    def compensator(times: torch.Tensor, history: torch.Tensor, params) -> torch.Tensor:
        del params
        if history.numel() == 0:
            return mu * times
        lags = (times[:, None] - history[None, :]).clamp_min(0.0)
        return mu * times + (alpha / beta) * (1.0 - torch.exp(-beta * lags)).sum(dim=1)

    return TemporalPointProcess(intensity, compensator)


def run_release_validation() -> dict[str, object]:
    expected = torch.tensor([0.2, 1.0, 3.5, 9.0], dtype=DTYPE, requires_grad=True)
    observed = torch.tensor([0.0, 1.0, 5.0, 7.0], dtype=DTYPE)
    log_likelihood = poisson_log_likelihood(expected, observed)
    deviance = poisson_deviance(expected, observed)
    deviance_residual = poisson_deviance_residual(expected, observed)
    anscombe = anscombe_residual(expected, observed)
    (deviance + anscombe.square().sum()).backward()

    edges = torch.tensor([0.0, 0.25, 1.0, 2.0], dtype=DTYPE)
    scale = torch.tensor(2.5, dtype=DTYPE, requires_grad=True)
    analytical, analytical_info = expected_counts_from_compensator(
        lambda times, parameter: parameter * times.square() / 2.0,
        edges,
        scale,
        return_diagnostics=True,
    )
    numerical, numerical_info = integrate_rate(
        lambda times, parameter: parameter * times,
        edges,
        scale,
        steps_per_bin=16,
        return_diagnostics=True,
    )
    analytical.sum().backward()

    rate = 1.7
    horizon = 2.5
    events = torch.tensor([0.2, 0.9, 1.8], dtype=DTYPE)
    homogeneous = _homogeneous_process(rate)
    homogeneous_result = homogeneous.log_likelihood(events, horizon)
    homogeneous_oracle = events.numel() * math.log(rate) - rate * horizon
    homogeneous_bins = torch.tensor([0.0, 0.5, 1.25, horizon], dtype=DTYPE)
    homogeneous_counts = homogeneous.expected_counts(homogeneous_bins)
    batch = homogeneous.log_likelihood_batch(
        [events, events[:1]], [horizon, 1.0]
    )
    generator = torch.Generator().manual_seed(1512)
    simulation = homogeneous.simulate(horizon, generator=generator)

    mu, alpha, beta = 0.7, 1.2, 0.8
    hawkes_events = torch.tensor([0.4, 1.1, 1.7], dtype=DTYPE)
    hawkes_horizon = 2.4
    hawkes = _exponential_hawkes_process(mu, alpha, beta)
    hawkes_result = hawkes.log_likelihood(hawkes_events, hawkes_horizon)
    event_intensities = []
    for index, event in enumerate(hawkes_events):
        history = hawkes_events[:index]
        lags = event - history
        event_intensities.append(mu + float((alpha * torch.exp(-beta * lags)).sum()))
    hawkes_oracle = sum(math.log(value) for value in event_intensities) - (
        mu * hawkes_horizon
        + sum(
            alpha / beta * (1.0 - math.exp(-beta * (hawkes_horizon - float(event))))
            for event in hawkes_events
        )
    )

    x = torch.tensor([-2.0, -1.0, 0.0, 1.0, 2.0], dtype=DTYPE)
    y = 1.5 * x - 0.25
    stack = ResidualStack(
        observations=(lambda parameters: parameters[0] * x + parameters[1] - y, 2.0),
        weak_prior=(lambda parameters: parameters - torch.tensor([1.5, -0.25], dtype=DTYPE), 0.1),
    )
    fit = LevenbergMarquardt(
        stack, torch.tensor([0.0, 0.0], dtype=DTYPE)
    ).fit(max_iter=50, tolerance=1e-12, covariance_policy="error")

    def guarded_residual(parameters: torch.Tensor) -> torch.Tensor:
        if float(parameters[0]) < -50.0:
            raise ValueError("deliberate invalid basin")
        return parameters - torch.tensor([2.0, -1.0], dtype=DTYPE)

    starts = [
        torch.tensor([-100.0, 0.0], dtype=DTYPE),
        torch.tensor([8.0, 4.0], dtype=DTYPE),
        torch.tensor([0.0, 0.0], dtype=DTYPE),
    ]
    multistart = multistart_least_squares(
        guarded_residual, starts, max_iter=30, tolerance=1e-12
    )

    singular = estimate_nonlinear_covariance(
        torch.tensor([1.0, -1.0, 0.5], dtype=DTYPE),
        torch.tensor([[1.0, 1.0], [2.0, 2.0], [3.0, 3.0]], dtype=DTYPE),
        singular_policy="pinv",
    )

    return {
        "kinopulse_version": version("kinopulse"),
        "count_objectives": {
            "log_likelihood_absolute_error": float(
                abs(log_likelihood - _manual_poisson_log_likelihood(expected.detach(), observed))
            ),
            "deviance_residual_identity_error": float(
                abs(deviance - deviance_residual.square().sum())
            ),
            "zero_count_deviance_contribution": float(
                poisson_deviance(expected.detach(), observed, reduction="none")[0]
            ),
            "expected_zero_count_limit": float(2.0 * expected.detach()[0]),
            "gradient_is_finite": bool(torch.isfinite(expected.grad).all()),
        },
        "expected_count_integration": {
            "analytical_method": analytical_info.method,
            "numerical_method": numerical_info.method,
            "maximum_absolute_error": float((analytical - numerical).abs().max()),
            "scale_gradient": float(scale.grad),
            "expected_scale_gradient": float(edges[-1].square() / 2.0),
        },
        "homogeneous_point_process": {
            "log_likelihood": float(homogeneous_result.log_likelihood),
            "analytical_log_likelihood": homogeneous_oracle,
            "absolute_error": abs(float(homogeneous_result.log_likelihood) - homogeneous_oracle),
            "maximum_expected_count_error": float(
                (homogeneous_counts - rate * torch.diff(homogeneous_bins)).abs().max()
            ),
            "batch_matches_scalar": bool(
                batch[0].log_likelihood == homogeneous_result.log_likelihood
                and batch[1].log_likelihood
                == homogeneous.log_likelihood(events[:1], 1.0).log_likelihood
            ),
            "simulated_event_count_seed_1512": int(simulation.event_times.numel()),
            "simulation_reproducible": bool(
                torch.equal(
                    simulation.event_times,
                    homogeneous.simulate(
                        horizon, generator=torch.Generator().manual_seed(1512)
                    ).event_times,
                )
            ),
        },
        "history_dependent_point_process": {
            "kinopulse_log_likelihood": float(hawkes_result.log_likelihood),
            "analytical_log_likelihood": hawkes_oracle,
            "absolute_error": abs(float(hawkes_result.log_likelihood) - hawkes_oracle),
            "event_contribution_error": abs(
                float(hawkes_result.event_contribution)
                - sum(math.log(value) for value in event_intensities)
            ),
            "compensator_error": abs(
                float(hawkes_result.compensator_contribution)
                - (sum(math.log(value) for value in event_intensities) - hawkes_oracle)
            ),
        },
        "least_squares": {
            "parameters": fit.parameters.tolist(),
            "objective": fit.objective,
            "converged": fit.converged,
            "jacobian_rank": fit.jacobian_rank,
            "condition_number": fit.condition_number,
            "has_covariance": fit.parameter_covariance is not None,
            "objective_contributions": fit.metadata["objective_contributions"],
        },
        "multistart": {
            "best_index": multistart.best.index,
            "best_parameters": multistart.best.result.parameters.tolist(),
            "candidate_count": len(multistart.candidates),
            "failed_candidate_indices": [
                candidate.index for candidate in multistart.failed_candidates
            ],
        },
        "singular_covariance": {
            "rank": singular.rank,
            "condition_number": singular.condition_number,
            "used_pseudoinverse": singular.used_pseudoinverse,
            "covariance_is_finite": bool(torch.isfinite(singular.covariance).all()),
        },
    }


def main(output_path: Path = Path("artifacts/kinopulse_2026071512_validation.json")) -> None:
    evidence = run_release_validation()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
