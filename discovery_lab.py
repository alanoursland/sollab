"""Use KinoPulse sparse identification to rediscover the Lorenz equations."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.identification.sparse import SparseIdentifier
from kinopulse.solvers.solve_functions import solve_ivp
from kinopulse.solvers.trajectory import SolverTrajectory

from lorenz_lab import simulate


DTYPE = torch.float64
INITIAL_CONDITIONS = ([1.0, 1.0, 1.0], [-8.0, 7.0, 27.0], [5.0, -3.0, 15.0])


def training_trajectories():
    trajectories = []
    for initial in INITIAL_CONDITIONS:
        times, states = simulate(torch.tensor(initial, dtype=DTYPE), horizon=8.0, samples=4001)
        trajectories.append(SolverTrajectory(times=times, states=states))
    return trajectories


def discover():
    identifier = SparseIdentifier(
        library_type="polynomial",
        max_degree=2,
        threshold=0.1,
        normalize=True,
    )
    system = identifier.fit(training_trajectories(), derivative_method="smooth")
    return identifier, system


def simulate_discovered(system, initial: torch.Tensor, horizon: float = 3.0, samples: int = 601):
    def learned_dynamics(t, state):
        features = system.library.build_library(state.unsqueeze(0))[0]
        return features @ system.coefficients

    times = torch.linspace(0.0, horizon, samples, dtype=DTYPE)
    trajectory = solve_ivp(
        learned_dynamics,
        (0.0, horizon),
        initial,
        t_eval=times,
        rtol=1e-8,
        atol=1e-10,
    )
    return trajectory.times, trajectory.states


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _, system = discover()
    equations = system.get_equations(
        state_names=["x", "y", "z"], coefficient_format=".5g"
    ).splitlines()
    active_terms = int((system.coefficients.abs() > 1e-6).sum().item())

    initial = torch.tensor([2.0, 3.0, 15.0], dtype=DTYPE)
    times, truth = simulate(initial, horizon=3.0, samples=601)
    _, learned = simulate_discovered(system, initial)
    rmse = torch.sqrt(torch.mean((truth - learned) ** 2)).item()

    report = {
        "experiment": "rediscover Lorenz dynamics from trajectory data",
        "library": "polynomial degree 2",
        "derivative_method": "smooth",
        "candidate_terms_per_equation": len(system.feature_names),
        "active_terms_total": active_terms,
        "discovered_equations": equations,
        "three_second_rollout_rmse": rmse,
    }
    (output_dir / "discovery_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    fig, axes = plt.subplots(3, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
    for index, (axis, variable) in enumerate(zip(axes, ("x", "y", "z"))):
        axis.plot(times, truth[:, index], color="#2d3436", linewidth=1.4, label="hidden truth")
        axis.plot(times, learned[:, index], color="#e17055", linestyle="--", label="discovered model")
        axis.set_ylabel(variable)
        axis.grid(alpha=0.2)
    axes[0].legend(frameon=False, ncol=2)
    axes[-1].set_xlabel("time")
    fig.suptitle(f"KinoPulse equation discovery · unseen rollout RMSE {rmse:.3f}")
    fig.savefig(output_dir / "discovery_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
