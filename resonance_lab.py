"""Map Mathieu parametric resonance with KinoPulse Floquet analysis."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.analysis.nonautonomous.parametric_resonance import MathieuAnalyzer
from kinopulse.solvers.solve_functions import solve_ivp

from lorenz_lab import interpolate_trajectory


DTYPE = torch.float64


def mathieu_dynamics(delta: float, epsilon: float):
    def dynamics(t, state):
        time = torch.as_tensor(t, dtype=state.dtype, device=state.device)
        return torch.stack((state[1], -(delta + epsilon * torch.cos(time)) * state[0]))

    return dynamics


def simulate(delta: float, epsilon: float, horizon: float = 80.0, samples: int = 4001):
    trajectory = solve_ivp(
        mathieu_dynamics(delta, epsilon),
        (0.0, horizon),
        torch.tensor([0.1, 0.0], dtype=DTYPE),
        rtol=1e-8,
        atol=1e-10,
    )
    times = torch.linspace(0.0, horizon, samples, dtype=DTYPE)
    return times, interpolate_trajectory(trajectory, times)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    resolution = 17
    chart = MathieuAnalyzer(0.25, 0.2).compute_stability_chart(
        delta_range=(0.0, 2.0),
        epsilon_range=(0.0, 0.8),
        resolution=resolution,
        step_size=0.05,
    )
    resonant = MathieuAnalyzer(0.25, 0.2)
    quiet = MathieuAnalyzer(0.5, 0.2)
    resonant_t, resonant_x = simulate(0.25, 0.2)
    quiet_t, quiet_x = simulate(0.5, 0.2)

    report = {
        "system": "Mathieu oscillator",
        "equation": "x'' + (delta + epsilon*cos(t))*x = 0",
        "chart_resolution": resolution,
        "principal_point": {
            "delta": 0.25,
            "epsilon": 0.2,
            "stable": resonant.is_stable(),
            "resonance_order": resonant.identify_resonance_tongue(),
            "final_amplitude": resonant_x[-1, 0].abs().item(),
        },
        "comparison_point": {
            "delta": 0.5,
            "epsilon": 0.2,
            "stable": quiet.is_stable(),
            "final_amplitude": quiet_x[-1, 0].abs().item(),
        },
        "unstable_grid_fraction": (~chart["stability_map"]).double().mean().item(),
    }
    (output_dir / "resonance_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    fig, (stability, response) = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    stability.imshow(
        (~chart["stability_map"]).T,
        origin="lower",
        aspect="auto",
        interpolation="nearest",
        extent=(0.0, 2.0, 0.0, 0.8),
        cmap="magma",
    )
    stability.scatter([0.25, 0.5], [0.2, 0.2], c=["cyan", "white"], edgecolors="black", s=45)
    stability.set(title="Floquet instability tongues", xlabel=r"$\delta$", ylabel=r"$\epsilon$")

    response.semilogy(resonant_t, resonant_x[:, 0].abs().clamp_min(1e-8), color="#d63031", label=r"resonant: $\delta=0.25$")
    response.semilogy(quiet_t, quiet_x[:, 0].abs().clamp_min(1e-8), color="#0984e3", label=r"stable: $\delta=0.5$")
    response.set(title="Direct response under periodic forcing", xlabel="time", ylabel="absolute displacement")
    response.legend(frameon=False)
    response.grid(alpha=0.2)
    fig.suptitle("KinoPulse nonautonomous exploration · parametric resonance")
    fig.savefig(output_dir / "resonance_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
