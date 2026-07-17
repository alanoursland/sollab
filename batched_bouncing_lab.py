"""Physical and failure-isolation oracles for batched hybrid simulation."""

from __future__ import annotations

import json
import math
from importlib.metadata import version
from pathlib import Path

import matplotlib
import numpy as np
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.core import EuclideanSpace, State
from kinopulse.hybrid import Guard, HybridSystem
from kinopulse.hybrid.simulation import (
    BatchExecutionError,
    BatchSynchronizationError,
    batched_hybrid_solve,
)

from hybrid_lab import DTYPE, GRAVITY, RESTITUTION, make_system


HEIGHTS = (0.5, 1.0, 2.0)
HORIZON = 2.0
DT = 0.002
ARTIFACT_PATH = Path("artifacts/batched_bouncing_analysis.json")
FIGURE_PATH = Path("artifacts/batched_bouncing_lab.png")


class ZeroDynamics:
    def dynamics(self, time, state, control=None, parameters=None):
        return torch.zeros_like(state.tensor)


def sample_specific_guard(time, state, control):
    if state.tensor[0] > 0.5:
        raise RuntimeError("intentional middle-sample guard failure")
    return torch.tensor(1.0, dtype=state.dtype, device=state.device)


def initial_balls(heights=HEIGHTS) -> State:
    values = torch.tensor([[height, 0.0] for height in heights], dtype=DTYPE)
    return State(values, EuclideanSpace(2))


def solve_balls(max_workers: int, heights=HEIGHTS, horizon: float = HORIZON, execution_mode="asynchronous"):
    return batched_hybrid_solve(
        make_system(),
        initial_balls(heights),
        (0.0, horizon),
        execution_mode=execution_mode,
        max_workers=max_workers,
        dt=DT,
        max_transitions=100,
        min_dwell_time=1e-7,
        detect_zeno=False,
    )


def physical_diagnostics(result) -> list[dict]:
    diagnostics = []
    for index, (height, trajectory) in enumerate(zip(HEIGHTS, result.trajectories)):
        first_expected = math.sqrt(2.0 * height / GRAVITY)
        transitions = trajectory.transitions
        first_actual = float(transitions[0]["time"])
        post_velocity = np.asarray([float(item["x_plus"][1]) for item in transitions])
        ratios = post_velocity[1:] / post_velocity[:-1]
        diagnostics.append(
            {
                "sample": index,
                "initial_height": height,
                "transition_count": len(transitions),
                "first_impact_expected": first_expected,
                "first_impact_actual": first_actual,
                "first_impact_absolute_error": abs(first_actual - first_expected),
                "mean_post_impact_velocity_ratio": None if len(ratios) == 0 else float(np.mean(ratios)),
                "expected_velocity_ratio": RESTITUTION,
            }
        )
    return diagnostics


def compare_batches(serial, concurrent) -> dict:
    per_sample = []
    for first, second in zip(serial.trajectories, concurrent.trajectories):
        per_sample.append(
            {
                "time_bit_exact": bool(torch.equal(first.t, second.t)),
                "state_bit_exact": bool(torch.equal(first.x, second.x)),
                "modes_equal": first.modes == second.modes,
                "transition_times_equal": [item["time"] for item in first.transitions]
                == [item["time"] for item in second.transitions],
            }
        )
    return {
        "all_equal": all(all(item.values()) for item in per_sample),
        "per_sample": per_sample,
    }


def synchronization_oracles() -> dict:
    matching = solve_balls(2, heights=(1.0, 1.0), horizon=1.0, execution_mode="synchronized")
    divergence = None
    try:
        solve_balls(2, heights=(0.5, 1.0), horizon=1.0, execution_mode="synchronized")
    except BatchSynchronizationError as exc:
        divergence = {
            "exception": type(exc).__name__,
            "sample_index": exc.sample_index,
            "transition_index": exc.transition_index,
            "transition_counts": exc.result.transition_counts.tolist(),
            "partial_batch_size": exc.result.batch_size,
        }
    if divergence is None:
        raise RuntimeError("divergent bouncing histories unexpectedly synchronized")
    return {
        "matching_verified": matching.synchronization_verified,
        "matching_transition_counts": matching.transition_counts.tolist(),
        "divergence": divergence,
    }


def partial_failure_oracle() -> dict:
    system = HybridSystem(
        modes={"flow": ZeroDynamics()},
        guards={
            ("flow", "flow"): Guard(
                sample_specific_guard,
                direction="both",
                enable_cache=False,
            )
        },
        resets={},
        initial_mode="flow",
    )
    try:
        batched_hybrid_solve(
            system,
            State(torch.tensor([[0.0], [1.0], [0.0]], dtype=DTYPE), EuclideanSpace(1)),
            (0.0, 0.1),
            max_workers=3,
            dt=0.1,
            detect_zeno=False,
        )
    except BatchExecutionError as exc:
        return {
            "failed_indices": list(exc.failed_indices),
            "result_statuses": [None if result is None else result.status.value for result in exc.results],
            "exception_types": [None if error is None else type(error).__name__ for error in exc.exceptions],
            "exception_messages": [None if error is None else str(error) for error in exc.exceptions],
        }
    raise RuntimeError("intentional sample-specific guard failure was not surfaced")


def plot_results(result, report: dict, path: Path = FIGURE_PATH) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), constrained_layout=True)
    colors = ["#0072B2", "#009E73", "#D55E00"]
    for index, (trajectory, color) in enumerate(zip(result.trajectories, colors)):
        axes[0].plot(trajectory.t, trajectory.x[:, 0], color=color, label=f"h₀={HEIGHTS[index]:g}")
        times = torch.tensor([item["time"] for item in trajectory.transitions], dtype=DTYPE)
        axes[0].scatter(times, torch.zeros_like(times), color=color, s=18)
    axes[0].set_xlabel("time")
    axes[0].set_ylabel("height")
    axes[0].set_title("Independent event histories in one batch")
    axes[0].legend()

    mask = result.valid_mask.cpu().numpy().astype(float)
    tail_start = max(0, int(result.lengths.min()) - 2)
    tail = mask[:, tail_start:]
    axes[1].imshow(tail, aspect="auto", interpolation="nearest", cmap="Greys", vmin=0, vmax=1)
    axes[1].set_yticks(range(len(HEIGHTS)), [f"h₀={height:g}" for height in HEIGHTS])
    tick_positions = np.arange(0, tail.shape[1], 2)
    axes[1].set_xticks(tick_positions, [str(tail_start + int(value)) for value in tick_positions])
    axes[1].set_xlabel("padded trajectory index (tail zoom)")
    axes[1].set_title(f"Black = valid; white = padding · lengths {report['ragged_batch']['lengths']}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run() -> dict:
    caller_system = make_system()
    serial = batched_hybrid_solve(
        caller_system,
        initial_balls(),
        (0.0, HORIZON),
        max_workers=1,
        dt=DT,
        max_transitions=100,
        min_dwell_time=1e-7,
        detect_zeno=False,
    )
    concurrent = solve_balls(3)
    report = {
        "experiment": "batched bouncing-ball hybrid simulation and failure isolation",
        "kinopulse_version": version("kinopulse"),
        "protocol": {"heights": list(HEIGHTS), "horizon": HORIZON, "dt": DT, "restitution": RESTITUTION},
        "physical_diagnostics": physical_diagnostics(concurrent),
        "serial_vs_concurrent": compare_batches(serial, concurrent),
        "ragged_batch": {
            "lengths": concurrent.lengths.tolist(),
            "transition_counts": concurrent.transition_counts.tolist(),
            "valid_counts": concurrent.valid_mask.sum(dim=1).tolist(),
            "padding_is_nan": bool(torch.isnan(concurrent.t[~concurrent.valid_mask]).all()),
        },
        "caller_isolation": {
            "current_mode": caller_system.current_mode,
            "mode_sequence": list(caller_system.mode_sequence),
            "transition_times": list(caller_system.transition_times),
        },
        "synchronization": synchronization_oracles(),
        "partial_failure": partial_failure_oracle(),
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    plot_results(concurrent, report)
    return report


if __name__ == "__main__":
    outcome = run()
    print(f"Transition counts: {outcome['ragged_batch']['transition_counts']}")
    print(f"Serial/concurrent exact: {outcome['serial_vs_concurrent']['all_equal']}")
    print(f"Isolated failed indices: {outcome['partial_failure']['failed_indices']}")
    print(f"Wrote {ARTIFACT_PATH}")
    print(f"Wrote {FIGURE_PATH}")
