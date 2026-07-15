"""Explore impacts, resets, and finite-time event accumulation with KinoPulse."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.core.state import EuclideanSpace, State
from kinopulse.hybrid import hybrid_solve, hybrid_system
from kinopulse.numeric.wrapper import NumericSystem


GRAVITY = 9.81
RESTITUTION = 0.8
DTYPE = torch.float64


def flight(t, state):
    return torch.stack((state[1], torch.as_tensor(-GRAVITY, dtype=state.dtype)))


def ground_guard(t, state, params=None):
    return state.tensor[0]


def impact_reset(state):
    after = state.tensor.clone()
    after[0] = 0.0
    after[1] = -RESTITUTION * after[1]
    return State(after, state.space)


def make_system():
    flow = NumericSystem(flight, state_dim=2, dtype=DTYPE)
    return hybrid_system(
        {"flight": flow},
        [("flight", "flight", ground_guard, impact_reset)],
        initial_mode="flight",
    )


def simulate(horizon=4.0, **kwargs):
    initial = State(torch.tensor([1.0, 0.0], dtype=DTYPE), EuclideanSpace(2))
    return hybrid_solve(
        make_system(),
        initial,
        (0.0, horizon),
        dt=0.002,
        max_transitions=100,
        min_dwell_time=1e-7,
        **kwargs,
    )


def theoretical_accumulation_time():
    first_impact = (2.0 / GRAVITY) ** 0.5
    first_upward_velocity = RESTITUTION * (2.0 * GRAVITY) ** 0.5
    return first_impact + 2.0 * first_upward_velocity / (GRAVITY * (1.0 - RESTITUTION))


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = simulate()
    impact_times = torch.tensor([item["time"] for item in result.transitions], dtype=DTYPE)
    pre_velocities = torch.tensor([item["x_minus"][1] for item in result.transitions], dtype=DTYPE)
    post_velocities = torch.tensor([item["x_plus"][1] for item in result.transitions], dtype=DTYPE)
    observed_ratios = post_velocities[1:] / post_velocities[:-1]
    energy_ratios = (post_velocities[1:] / post_velocities[:-1]) ** 2

    report = {
        "system": "inelastic bouncing ball",
        "restitution": RESTITUTION,
        "impacts_before_four_seconds": len(result.transitions),
        "first_impact_time": impact_times[0].item(),
        "theoretical_first_impact_time": (2.0 / GRAVITY) ** 0.5,
        "mean_velocity_ratio": observed_ratios.mean().item(),
        "expected_velocity_ratio": RESTITUTION,
        "mean_energy_ratio": energy_ratios.mean().item(),
        "expected_energy_ratio": RESTITUTION**2,
        "theoretical_event_accumulation_time": theoretical_accumulation_time(),
        "zeno_detected_before_four_seconds": result.zeno_detected,
    }
    (output_dir / "hybrid_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    fig, (motion, intervals) = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    motion.plot(result.t, result.x[:, 0], color="#0984e3")
    motion.scatter(impact_times, torch.zeros_like(impact_times), color="#d63031", s=16, zorder=3)
    motion.set(title="Hybrid trajectory and impact events", xlabel="time", ylabel="height")
    motion.grid(alpha=0.2)

    dwell = torch.diff(impact_times)
    intervals.semilogy(impact_times[1:], dwell, marker="o", color="#6c5ce7", markersize=3)
    intervals.axvline(theoretical_accumulation_time(), color="#d63031", linestyle="--", label="theoretical limit")
    intervals.set(title="Geometrically shrinking flight times", xlabel="impact time", ylabel="time since prior impact")
    intervals.legend(frameon=False)
    intervals.grid(alpha=0.2)
    fig.suptitle("KinoPulse hybrid exploration · a bouncing ball approaching Zeno behavior")
    fig.savefig(output_dir / "hybrid_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
