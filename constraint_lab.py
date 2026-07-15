"""Keep a Cartesian pendulum on its constraint manifold with KinoPulse."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.core.state import EuclideanSpace, State
from kinopulse.numeric.wrapper import NumericSystem
from kinopulse.solvers.config import SolverConfig, StepSizeConfig
from kinopulse.solvers.dae import ConstraintProjector, analyze_consistent_initialization


DTYPE = torch.float64
GRAVITY = 9.81


def pendulum_dynamics(t, state):
    position, velocity = state[:2], state[2:]
    gravity = torch.tensor([0.0, -GRAVITY], dtype=state.dtype)
    multiplier = -(velocity @ velocity + position @ gravity) / (position @ position)
    return torch.cat((velocity, gravity + multiplier * position))


def pendulum_constraint(t, state, u=None, params=None):
    position, velocity = state.tensor[:2], state.tensor[2:]
    return torch.stack((position @ position - 1.0, position @ velocity))


def make_system():
    system = NumericSystem(pendulum_dynamics, state_dim=4, dtype=DTYPE)
    system.constraint = pendulum_constraint
    return system


def simulate(project: bool, steps: int = 500, dt: float = 0.01):
    system = make_system()
    guess = State(torch.tensor([0.7, -0.7, 0.2, 0.1], dtype=DTYPE), EuclideanSpace(4))
    state, initialization = analyze_consistent_initialization(system, guess)
    config = SolverConfig(step_size=StepSizeConfig(dt=dt), dtype=DTYPE)
    projector = ConstraintProjector(system, config)
    states = [state.tensor.clone()]

    for index in range(steps):
        next_tensor = state.tensor + dt * pendulum_dynamics(index * dt, state.tensor)
        state = State(next_tensor, state.space)
        if project:
            state = projector.project((index + 1) * dt, state)
        states.append(state.tensor.clone())

    trajectory = torch.stack(states)
    position = trajectory[:, :2]
    velocity = trajectory[:, 2:]
    circle_error = (position.square().sum(dim=1) - 1.0).abs()
    tangency_error = (position * velocity).sum(dim=1).abs()
    energy = 0.5 * velocity.square().sum(dim=1) + GRAVITY * position[:, 1]
    return trajectory, circle_error, tangency_error, energy, initialization


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = simulate(project=False)
    projected = simulate(project=True)
    trajectory, circle_error, tangency_error, energy, initialization = projected

    report = {
        "system": "Cartesian unit pendulum",
        "initial_projection_iterations": initialization.iterations,
        "initial_correction_norm": initialization.correction_norm,
        "projected_max_circle_error": circle_error.max().item(),
        "projected_max_tangency_error": tangency_error.max().item(),
        "unprojected_max_circle_error": raw[1].max().item(),
        "unprojected_max_tangency_error": raw[2].max().item(),
        "projected_energy_range": (energy.max() - energy.min()).item(),
    }
    (output_dir / "constraint_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    fig, (orbit, drift) = plt.subplots(1, 2, figsize=(10.5, 4.5), constrained_layout=True)
    angle = torch.linspace(0, 2 * torch.pi, 400)
    orbit.plot(torch.cos(angle), torch.sin(angle), color="#b2bec3", linestyle="--", label="constraint manifold")
    orbit.plot(trajectory[:, 0], trajectory[:, 1], color="#6c5ce7", label="projected trajectory")
    orbit.set_aspect("equal")
    orbit.set(title="Pendulum in Cartesian coordinates", xlabel="x", ylabel="y")
    orbit.legend(frameon=False)
    orbit.grid(alpha=0.2)

    times = torch.arange(len(circle_error), dtype=DTYPE) * 0.01
    drift.semilogy(times, raw[1].clamp_min(1e-16), color="#d63031", label="without projection")
    drift.semilogy(times, circle_error.clamp_min(1e-16), color="#00b894", label="KinoPulse projection")
    drift.set(title="Holonomic constraint drift", xlabel="time", ylabel=r"$|x^2+y^2-1|$")
    drift.legend(frameon=False)
    drift.grid(alpha=0.2)
    fig.suptitle("KinoPulse constrained-dynamics exploration · staying on the manifold")
    fig.savefig(output_dir / "constraint_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
