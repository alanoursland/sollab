"""Explore deterministic chaos with KinoPulse and the Lorenz system."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.analysis.stability.chaos import ChaosDetector
from kinopulse.solvers.solve_functions import solve_ivp


PARAMETERS = {"sigma": 10.0, "rho": 28.0, "beta": 8.0 / 3.0}


def lorenz(t: float, state: torch.Tensor, params=None) -> torch.Tensor:
    """Lorenz vector field with the signature expected by KinoPulse analysis."""
    values = PARAMETERS if params is None else params
    x, y, z = state
    return torch.stack(
        (
            values["sigma"] * (y - x),
            x * (values["rho"] - z) - y,
            x * y - values["beta"] * z,
        )
    )


def interpolate_trajectory(trajectory, sample_times: torch.Tensor) -> torch.Tensor:
    """Linearly resample a KinoPulse trajectory onto a uniform time grid."""
    times = trajectory.times
    states = trajectory.states
    indices = torch.searchsorted(times, sample_times, right=True).clamp(1, len(times) - 1)
    left_t, right_t = times[indices - 1], times[indices]
    weight = ((sample_times - left_t) / (right_t - left_t)).unsqueeze(-1)
    return states[indices - 1] + weight * (states[indices] - states[indices - 1])


def simulate(initial_state: torch.Tensor, horizon: float, samples: int):
    requested_times = torch.linspace(0.0, horizon, samples)
    trajectory = solve_ivp(
        lorenz,
        (0.0, horizon),
        initial_state,
        method="RK45",
        rtol=1e-7,
        atol=1e-9,
    )
    return requested_times, interpolate_trajectory(trajectory, requested_times)


def main(output_dir: Path = Path("artifacts")) -> None:
    torch.manual_seed(7)
    output_dir.mkdir(parents=True, exist_ok=True)

    horizon, samples = 30.0, 6001
    initial = torch.tensor([1.0, 1.0, 1.0], dtype=torch.float64)
    perturbed = initial + torch.tensor([1e-6, 0.0, 0.0], dtype=torch.float64)
    times, states = simulate(initial, horizon, samples)
    _, nearby_states = simulate(perturbed, horizon, samples)
    separation = torch.linalg.vector_norm(states - nearby_states, dim=1)

    result = ChaosDetector(lorenz, dt=0.01).detect_chaos(
        initial, time_horizon=15.0, params=PARAMETERS, compute_spectrum=True
    )
    report = {
        "system": "Lorenz",
        "parameters": PARAMETERS,
        "initial_state": initial.tolist(),
        "perturbation": 1e-6,
        "is_chaotic": result.is_chaotic,
        "largest_lyapunov_exponent": result.largest_lyapunov_exponent,
        "lyapunov_spectrum": result.lyapunov_exponents.tolist(),
        "sensitive_dependence": result.sensitive_dependence,
        "converged": result.converged,
        "max_observed_separation": separation.max().item(),
    }
    (output_dir / "lorenz_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    with (output_dir / "lorenz_trajectory.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(("time", "x", "y", "z", "nearby_separation"))
        writer.writerows(zip(times.tolist(), *states.T.tolist(), separation.tolist()))

    fig = plt.figure(figsize=(12, 5), constrained_layout=True)
    ax = fig.add_subplot(1, 2, 1, projection="3d")
    ax.plot(*states.T, color="#6c5ce7", linewidth=0.55)
    ax.set(title="Lorenz attractor", xlabel="x", ylabel="y", zlabel="z")
    ax.grid(False)

    divergence = fig.add_subplot(1, 2, 2)
    divergence.semilogy(times, separation.clamp_min(1e-12), color="#d63031")
    divergence.set(
        title="Sensitive dependence on initial conditions",
        xlabel="time",
        ylabel="distance between trajectories",
    )
    divergence.grid(alpha=0.25)
    fig.suptitle(
        f"KinoPulse chaos analysis · largest Lyapunov exponent "
        f"{result.largest_lyapunov_exponent:.3f}"
    )
    fig.savefig(output_dir / "lorenz_lab.png", dpi=180)
    plt.close(fig)

    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
