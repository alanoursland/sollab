"""Stabilize an inverted pendulum linearization with KinoPulse LQR."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.control.linear.lqr import (
    synthesize_lqr_from_matrices,
    verify_closed_loop_stability,
    verify_riccati_solution,
)
from kinopulse.control.linear.utils.controllability import is_controllable
from kinopulse.solvers.solve_functions import solve_ivp


DTYPE = torch.float64
A = torch.tensor([[0.0, 1.0], [9.81, 0.0]], dtype=DTYPE)
B = torch.tensor([[0.0], [1.0]], dtype=DTYPE)
Q = torch.diag(torch.tensor([20.0, 2.0], dtype=DTYPE))
R = torch.tensor([[0.5]], dtype=DTYPE)


def design_controller():
    return synthesize_lqr_from_matrices(A, B, Q, R, name="upright-pendulum LQR")


def simulate(matrix: torch.Tensor, horizon: float = 6.0):
    def dynamics(t, state):
        return matrix @ state

    return solve_ivp(
        dynamics,
        (0.0, horizon),
        torch.tensor([0.15, 0.0], dtype=DTYPE),
        rtol=1e-8,
        atol=1e-10,
    )


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    controller = design_controller()
    controllable, rank = is_controllable(A, B)
    stable, poles = verify_closed_loop_stability(A, B, controller.K)
    riccati_valid, riccati_residual = verify_riccati_solution(A, B, Q, R, controller.P, tol=1e-7)
    closed_matrix = A - B @ controller.K
    open_loop = simulate(A, horizon=2.0)
    closed_loop = simulate(closed_matrix)

    report = {
        "system": "linearized upright pendulum",
        "controllable": bool(controllable),
        "controllability_rank": int(rank),
        "gain": controller.K.tolist(),
        "closed_loop_stable": bool(stable),
        "closed_loop_poles": [
            {"real": value.real.item(), "imag": value.imag.item()} for value in poles
        ],
        "riccati_solution_valid": bool(riccati_valid),
        "riccati_residual": float(riccati_residual),
    }
    (output_dir / "control_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    fig, (response, phase) = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    response.plot(open_loop.times, open_loop.states[:, 0], color="#d63031", label="open loop")
    response.plot(closed_loop.times, closed_loop.states[:, 0], color="#00b894", label="LQR closed loop")
    response.axhline(0, color="black", linewidth=0.7)
    response.set_yscale("symlog", linthresh=0.01)
    response.set(title="Upright-angle response", xlabel="time", ylabel="angle error (rad)")
    response.legend(frameon=False)
    response.grid(alpha=0.2)

    phase.plot(open_loop.states[:, 0], open_loop.states[:, 1], color="#d63031", label="open loop")
    phase.plot(closed_loop.states[:, 0], closed_loop.states[:, 1], color="#00b894", label="LQR closed loop")
    phase.scatter([0], [0], color="black", s=20, zorder=3)
    phase.set_xscale("symlog", linthresh=0.01)
    phase.set_yscale("symlog", linthresh=0.01)
    phase.set(title="Phase portrait", xlabel="angle error", ylabel="angular velocity")
    phase.legend(frameon=False)
    phase.grid(alpha=0.2)
    fig.suptitle("KinoPulse control exploration · stabilizing an unstable equilibrium")
    fig.savefig(output_dir / "control_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
