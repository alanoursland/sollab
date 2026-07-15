"""Benchmark KinoPulse PDE diffusion against an analytical solution."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.pde import (
    BoundaryCondition,
    Field,
    Grid,
    HeatEquation,
    heat_1d_analytical,
    solve_pde,
)


ALPHA = 0.1
HORIZON = 0.1
DTYPE = torch.float64


def solve_resolution(points: int):
    grid = Grid(1, (points,), [(0.0, 1.0)], [False], dtype=DTYPE)
    x = grid.meshgrid()[0]
    initial = Field(torch.sin(torch.pi * x).reshape(1, 1, -1), grid, channels=1)
    boundaries = [
        BoundaryCondition("dirichlet", "left", 0, value=0.0),
        BoundaryCondition("dirichlet", "right", 0, value=0.0),
    ]
    dt = 0.2 * grid.dx[0] ** 2 / ALPHA
    trajectory = solve_pde(
        HeatEquation(grid, alpha=ALPHA),
        (0.0, HORIZON),
        initial,
        boundaries,
        dt=dt,
        save_every=max(1, round(0.01 / dt)),
    )
    numerical = trajectory.fields[-1].data[0, 0]
    exact = heat_1d_analytical(x, HORIZON, ALPHA)
    error = torch.sqrt(torch.mean((numerical - exact) ** 2)).item()
    return x, numerical, exact, error, trajectory


def probe_stability_warning(points: int = 51, dt: float = 0.01):
    """Return warnings emitted for an intentionally unsafe explicit step."""
    grid = Grid(1, (points,), [(0.0, 1.0)], [False], dtype=DTYPE)
    x = grid.meshgrid()[0]
    initial = Field(torch.sin(torch.pi * x).reshape(1, 1, -1), grid, channels=1)
    boundaries = [
        BoundaryCondition("dirichlet", "left", 0, value=0.0),
        BoundaryCondition("dirichlet", "right", 0, value=0.0),
    ]
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        solve_pde(
            HeatEquation(grid, alpha=ALPHA),
            (0.0, 0.001),
            initial,
            boundaries,
            dt=dt,
        )
    return [str(item.message) for item in captured]


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    resolutions = [26, 51, 101]
    solutions = [solve_resolution(points) for points in resolutions]
    errors = [solution[3] for solution in solutions]
    observed_orders = [
        torch.log2(torch.tensor(errors[i] / errors[i + 1])).item()
        for i in range(len(errors) - 1)
    ]

    finest_x, finest_numerical, finest_exact, _, finest_trajectory = solutions[-1]
    variances = [field.data.var().item() for field in finest_trajectory.fields]
    stability_warnings = probe_stability_warning()
    report = {
        "system": "one-dimensional heat equation",
        "diffusivity": ALPHA,
        "final_time": HORIZON,
        "resolutions": resolutions,
        "rmse": errors,
        "observed_convergence_orders": observed_orders,
        "variance_monotonically_decreases": all(
            later <= earlier + 1e-12 for earlier, later in zip(variances, variances[1:])
        ),
        "unsafe_timestep_warnings": stability_warnings,
    }
    (output_dir / "diffusion_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    fig, (profile, convergence) = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    profile.plot(finest_x, finest_exact, color="#2d3436", linewidth=2, label="analytical")
    profile.plot(finest_x, finest_numerical, color="#e17055", linestyle="--", label="KinoPulse")
    profile.set(title="Diffused sine mode at t = 0.1", xlabel="position", ylabel="temperature")
    profile.legend(frameon=False)
    profile.grid(alpha=0.2)

    spacing = torch.tensor([1.0 / (points - 1) for points in resolutions])
    convergence.loglog(spacing, errors, marker="o", color="#6c5ce7", label="measured error")
    reference = errors[-1] * (spacing / spacing[-1]) ** 2
    convergence.loglog(spacing, reference, linestyle="--", color="#00b894", label="second-order reference")
    convergence.invert_xaxis()
    convergence.set(title="Grid-convergence study", xlabel="grid spacing", ylabel="final RMSE")
    convergence.legend(frameon=False)
    convergence.grid(alpha=0.2, which="both")
    fig.suptitle("KinoPulse field exploration · heat diffusion and numerical convergence")
    fig.savefig(output_dir / "diffusion_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
