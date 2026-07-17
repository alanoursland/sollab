"""Analytical uncertainty decomposition for stochastic neural vector fields."""

from __future__ import annotations

import json
from importlib.metadata import version
from pathlib import Path

import matplotlib
import numpy as np
import torch
from torch import nn

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.neural.base import NeuralSystem
from kinopulse.neural.vector_fields import EnsembleNeuralVectorField, NeuralStochasticVectorField


DTYPE = torch.float64
ARTIFACT_PATH = Path("artifacts/stochastic_uncertainty_analysis.json")
FIGURE_PATH = Path("artifacts/stochastic_uncertainty_lab.png")
SEED = 20260717
SAMPLES = 100_000
DT = 0.04


class ConstantNetwork(nn.Module):
    def __init__(self, values: list[float]):
        super().__init__()
        self.register_buffer("values", torch.tensor(values, dtype=DTYPE))

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.values.expand(*value.shape[:-1], self.values.numel())


class ConstantVectorField(NeuralSystem):
    def __init__(self, values: list[float]):
        super().__init__(state_dim=len(values), dtype=DTYPE)
        self.register_buffer("values", torch.tensor(values, dtype=DTYPE))

    def forward(self, time, state, control=None, parameters=None):
        return self.values.expand(*state.shape[:-1], self.values.numel())


def make_stochastic_field() -> NeuralStochasticVectorField:
    field = NeuralStochasticVectorField(state_dim=2, noise_dim=2, dtype=DTYPE)
    field.drift_net = ConstantNetwork([1.0, -2.0])
    field.diffusion_net = ConstantNetwork([0.5, 0.0, 0.1, 0.3])
    return field


def analytical_stochastic_oracle() -> dict:
    field = make_stochastic_field()
    state = torch.tensor([3.0, 4.0], dtype=DTYPE)
    distribution = field.predict_distribution(torch.tensor(0.0), state)
    diffusion = field.diffusion(torch.tensor(0.0), state)
    supplied_noise = torch.tensor([2.0, -1.0], dtype=DTYPE)
    applied = field.apply_noise(diffusion, supplied_noise)
    expected_covariance = diffusion @ diffusion.T
    return {
        "drift": distribution.mean.tolist(),
        "diffusion": diffusion.tolist(),
        "aleatoric_covariance": distribution.aleatoric_covariance.tolist(),
        "expected_covariance": expected_covariance.tolist(),
        "epistemic_variance": distribution.epistemic_variance.tolist(),
        "supplied_noise": supplied_noise.tolist(),
        "applied_noise": applied.tolist(),
        "expected_applied_noise": [1.0, -0.1],
    }


def ensemble_oracle() -> dict:
    ensemble = EnsembleNeuralVectorField(
        [
            ConstantVectorField([1.0, 2.0]),
            ConstantVectorField([3.0, 0.0]),
            ConstantVectorField([2.0, 4.0]),
        ]
    )
    distribution = ensemble.predict_distribution(
        torch.tensor(0.0), torch.tensor([3.0, 4.0], dtype=DTYPE)
    )
    return {
        "members": distribution.members.tolist(),
        "mean": distribution.mean.tolist(),
        "epistemic_variance": distribution.epistemic_variance.tolist(),
        "expected_mean": [2.0, 2.0],
        "expected_epistemic_variance": [2.0 / 3.0, 8.0 / 3.0],
        "aleatoric_covariance": distribution.aleatoric_covariance.tolist(),
    }


def monte_carlo_oracle() -> tuple[dict, np.ndarray]:
    field = make_stochastic_field()
    diffusion = field.diffusion(torch.tensor(0.0), torch.tensor([0.0, 0.0], dtype=DTYPE))
    drift = field.drift(torch.tensor(0.0), torch.tensor([0.0, 0.0], dtype=DTYPE))
    generator = torch.Generator().manual_seed(SEED)
    noise = torch.randn(SAMPLES, 2, generator=generator, dtype=DTYPE)
    batched_diffusion = diffusion.expand(SAMPLES, -1, -1)
    increments = DT * drift + (DT**0.5) * field.apply_noise(batched_diffusion, noise)
    empirical_mean = increments.mean(dim=0)
    centered = increments - empirical_mean
    empirical_covariance = centered.T @ centered / SAMPLES
    expected_mean = DT * drift
    expected_covariance = DT * (diffusion @ diffusion.T)
    mean_error = torch.linalg.vector_norm(empirical_mean - expected_mean)
    covariance_error = torch.linalg.matrix_norm(empirical_covariance - expected_covariance)
    return (
        {
            "seed": SEED,
            "samples": SAMPLES,
            "dt": DT,
            "expected_mean": expected_mean.tolist(),
            "empirical_mean": empirical_mean.tolist(),
            "mean_error_l2": float(mean_error),
            "expected_covariance": expected_covariance.tolist(),
            "empirical_covariance": empirical_covariance.tolist(),
            "covariance_error_frobenius": float(covariance_error),
        },
        increments.detach().numpy(),
    )


def plot_results(results: dict, increments: np.ndarray, path: Path = FIGURE_PATH) -> None:
    stochastic = results["stochastic_field_oracle"]
    ensemble = results["ensemble_oracle"]
    monte_carlo = results["monte_carlo_one_step"]
    expected_covariance = np.asarray(monte_carlo["expected_covariance"])
    empirical_covariance = np.asarray(monte_carlo["empirical_covariance"])

    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), constrained_layout=True)
    subset = increments[:4000]
    axes[0].scatter(subset[:, 0], subset[:, 1], s=5, alpha=0.18, color="#0072B2")
    axes[0].scatter(*monte_carlo["expected_mean"], color="#D55E00", marker="x", s=80, label="analytical mean")
    axes[0].set_xlabel("state-1 increment")
    axes[0].set_ylabel("state-2 increment")
    axes[0].set_title("Supplied-noise one-step cloud")
    axes[0].legend()

    width = 0.34
    positions = np.arange(4)
    axes[1].bar(positions - width / 2, expected_covariance.reshape(-1), width, color="#56B4E9", label="expected")
    axes[1].bar(positions + width / 2, empirical_covariance.reshape(-1), width, color="#009E73", label="empirical")
    axes[1].set_xticks(positions, ["Σ11", "Σ12", "Σ21", "Σ22"])
    axes[1].set_title("Aleatoric covariance oracle")
    axes[1].legend()

    members = np.asarray(ensemble["members"])
    axes[2].scatter(members[:, 0], members[:, 1], color="#CC79A7", s=80, label="members")
    axes[2].scatter(*ensemble["mean"], color="black", marker="*", s=150, label="ensemble mean")
    axes[2].set_xlabel("drift component 1")
    axes[2].set_ylabel("drift component 2")
    axes[2].set_title(
        "Epistemic variance "
        f"({ensemble['epistemic_variance'][0]:.3f}, {ensemble['epistemic_variance'][1]:.3f})"
    )
    axes[2].legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run() -> dict:
    monte_carlo, increments = monte_carlo_oracle()
    results = {
        "experiment": "stochastic neural vector-field uncertainty decomposition",
        "kinopulse_version": version("kinopulse"),
        "stochastic_field_oracle": analytical_stochastic_oracle(),
        "ensemble_oracle": ensemble_oracle(),
        "monte_carlo_one_step": monte_carlo,
        "scope": "synthetic analytical validation; application supplies all noise",
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    plot_results(results, increments)
    return results


if __name__ == "__main__":
    outcome = run()
    monte_carlo = outcome["monte_carlo_one_step"]
    print(f"Mean error: {monte_carlo['mean_error_l2']:.6g}")
    print(f"Covariance error: {monte_carlo['covariance_error_frobenius']:.6g}")
    print(f"Wrote {ARTIFACT_PATH}")
    print(f"Wrote {FIGURE_PATH}")
