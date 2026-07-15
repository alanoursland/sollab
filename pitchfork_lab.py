"""Map a pitchfork bifurcation with KinoPulse equilibrium continuation."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.analysis.bifurcations.detection import BifurcationDetector
from kinopulse.analysis.bifurcations.parameter_sweep import ParameterSweeper
from kinopulse.numeric.wrapper import NumericSystem


def pitchfork(t: float, state: torch.Tensor, params) -> torch.Tensor:
    """Supercritical pitchfork normal form: x' = mu*x - x^3."""
    return params["mu"] * state - state**3


def analyze(samples: int = 81):
    parameter_values = torch.linspace(-1.0, 1.0, samples, dtype=torch.float64)
    system = NumericSystem(pitchfork, state_dim=1, dtype=torch.float64)
    sweep = ParameterSweeper(system).sweep_parameter(
        "mu",
        parameter_values,
        torch.tensor([0.1], dtype=torch.float64),
        base_params={"mu": torch.tensor(0.0, dtype=torch.float64)},
        use_continuation=False,
    )
    detected = BifurcationDetector().detect_from_sweep(sweep)
    return parameter_values, sweep, detected


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    mu, sweep, detected = analyze()
    eigenvalues = sweep.eigenvalue_tracking[:, 0].real

    detector_report = [
        {
            "parameter_value": point.parameter_value,
            "reported_type": point.bifurcation_type,
            "confidence": point.confidence,
        }
        for point in detected
    ]
    report = {
        "system": "supercritical pitchfork normal form",
        "equation": "dx/dt = mu*x - x^3",
        "continuation_successful": sweep.continuation_successful,
        "kinopulse_detector": detector_report,
        "analytical_bifurcation": {"parameter_value": 0.0, "type": "pitchfork"},
        "note": "Detector output is retained verbatim; see kinopulse_gaps.",
    }
    (output_dir / "pitchfork_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    positive = mu.clamp_min(0).sqrt()
    fig, (branches, spectrum) = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    branches.plot(mu, torch.zeros_like(mu), color="#6c5ce7", label="central equilibrium")
    mask = mu >= 0
    branches.plot(mu[mask], positive[mask], color="#00b894", label=r"$x=+\sqrt{\mu}$")
    branches.plot(mu[mask], -positive[mask], color="#00b894", label=r"$x=-\sqrt{\mu}$")
    branches.scatter([0], [0], color="#d63031", zorder=3, label="analytical pitchfork")
    branches.set(title="Equilibrium branches", xlabel=r"parameter $\mu$", ylabel="equilibrium x")
    branches.legend(frameon=False)

    spectrum.axhline(0, color="black", linewidth=0.8)
    spectrum.plot(mu, eigenvalues, color="#0984e3", label="KinoPulse eigenvalue")
    for i, point in enumerate(detected):
        spectrum.axvline(
            point.parameter_value,
            color="#d63031",
            linestyle="--",
            alpha=0.75,
            label="detector output" if i == 0 else None,
        )
    spectrum.set(title="Central-branch stability", xlabel=r"parameter $\mu$", ylabel="eigenvalue")
    spectrum.legend(frameon=False)
    fig.suptitle("KinoPulse bifurcation exploration · pitchfork normal form")
    fig.savefig(output_dir / "pitchfork_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
