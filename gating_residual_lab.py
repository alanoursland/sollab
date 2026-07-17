"""Analytical oracles for KinoPulse structured residuals and neural gating."""

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

from kinopulse.core import EuclideanSpace, State
from kinopulse.neural.gating import GatingPolicy, apply_gating
from kinopulse.neural.residuals import GatedResidual, MultiplicativeResidual


DTYPE = torch.float64
ARTIFACT_PATH = Path("artifacts/gating_residual_analysis.json")
FIGURE_PATH = Path("artifacts/gating_residual_lab.png")
WHEEL_SHA256 = "F39CDF1B09CC7068FBA587C565176D7E50D6F9C25EE52A1730CF527D420ED619"


class IdentityLogits(nn.Module):
    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return value


class ConstantNetwork(nn.Module):
    def __init__(self, values: list[float]):
        super().__init__()
        self.register_buffer("values", torch.tensor(values, dtype=DTYPE))

    def forward(self, value: torch.Tensor) -> torch.Tensor:
        return self.values.expand(*value.shape[:-1], self.values.numel())


class LinearBase:
    state_dim = 1
    input_dim = 0

    def __init__(self):
        self.space = EuclideanSpace(1)
        self.state_space = self.space

    def dynamics(self, time, state, control=None, parameters=None):
        return -2.0 * state.tensor


def chatter_scenario() -> tuple[list[float], list[int]]:
    margins = (
        [0.5] * 4
        + [-0.05, 0.08, -0.06, 0.07, -0.04, 0.06]
        + [-0.7] * 6
        + [0.04, -0.06, 0.05, -0.07, 0.03, -0.08]
        + [0.7] * 6
    )
    truth = [0] * 10 + [1] * 12 + [0] * 6
    return margins, truth


def replay_gate(policy: GatingPolicy, margins: list[float], truth: list[int]) -> dict:
    state = None
    selected, switched, dwell, output = [], [], [], []
    candidates = torch.tensor([[[-1.0], [1.0]]], dtype=DTYPE)
    for margin in margins:
        logits = torch.tensor([[margin / 2.0, -margin / 2.0]], dtype=DTYPE)
        decision = policy(logits, state)
        state = decision.state
        selected.append(int(decision.selected.item()))
        switched.append(bool(decision.switched.item()))
        dwell.append(int(state.dwell_steps.item()))
        output.append(float(apply_gating(candidates, decision).item()))
    target_output = np.asarray([-1.0 if expert == 0 else 1.0 for expert in truth])
    return {
        "selected": selected,
        "switched": switched,
        "dwell_steps": dwell,
        "expert_output": output,
        "switch_count": int(sum(switched)),
        "selection_accuracy": float(np.mean(np.asarray(selected) == np.asarray(truth))),
        "expert_output_mse": float(np.mean((np.asarray(output) - target_output) ** 2)),
    }


def straight_through_oracle() -> dict:
    logits = torch.tensor([[0.2, -0.2]], dtype=DTYPE, requires_grad=True)
    policy = GatingPolicy(IdentityLogits(), 2, mode="hard", temperature=1.0)
    decision = policy(logits)
    candidates = torch.tensor([[[2.0], [5.0]]], dtype=DTYPE)
    result = apply_gating(candidates, decision)
    result.sum().backward()
    assert logits.grad is not None
    return {
        "weights": decision.weights.detach().tolist(),
        "selected": int(decision.selected.item()),
        "forward_value": float(result.item()),
        "logit_gradient": logits.grad.detach().tolist(),
        "gradient_sum": float(logits.grad.sum()),
        "gradient_norm": float(torch.linalg.vector_norm(logits.grad)),
    }


def residual_oracles() -> dict:
    base = LinearBase()
    state = State(torch.tensor([3.0], dtype=DTYPE), base.space)

    multiplicative = MultiplicativeResidual(base, hidden_dims=[], dtype=DTYPE)
    multiplicative.residual_net = ConstantNetwork([0.5])
    multiplicative_value = float(multiplicative.dynamics(0.0, state).item())

    gated = GatedResidual(
        base,
        hidden_dims=[],
        dtype=DTYPE,
        gate_network=ConstantNetwork([0.0]),
    )
    gated.residual_net = ConstantNetwork([4.0])
    gated_value = float(gated.dynamics(0.0, state).item())
    gate_value = float(gated.gate_values(state.tensor.unsqueeze(0)).item())
    return {
        "base_dynamics_at_x3": -6.0,
        "multiplicative_residual": 0.5,
        "multiplicative_expected": -9.0,
        "multiplicative_actual": multiplicative_value,
        "gated_additive_residual": 4.0,
        "gate_logit": 0.0,
        "gate_value": gate_value,
        "gated_expected": -4.0,
        "gated_actual": gated_value,
    }


def plot_results(results: dict, path: Path = FIGURE_PATH) -> None:
    margins = np.asarray(results["scenario"]["score_margin"])
    truth = np.asarray(results["scenario"]["true_expert"])
    naive = results["naive_hard_gate"]
    stable = results["hysteretic_dwell_gate"]
    steps = np.arange(len(margins))

    fig, axes = plt.subplots(2, 1, figsize=(10, 7.5), sharex=True, constrained_layout=True)
    axes[0].plot(steps, margins, color="#0072B2", marker="o", ms=3, label="expert-0 score margin")
    axes[0].axhline(0, color="0.5", lw=1)
    axes[0].axhspan(-0.25, 0.25, color="#F0E442", alpha=0.2, label="hysteresis region")
    axes[0].set_ylabel("score margin")
    axes[0].set_title("Boundary jitter followed by two sustained regime changes")
    axes[0].legend()

    axes[1].step(steps, truth, where="mid", color="black", lw=2.5, label="true expert")
    axes[1].step(steps, naive["selected"], where="mid", color="#D55E00", alpha=0.8, label=f"naive ({naive['switch_count']} switches)")
    axes[1].step(steps, stable["selected"], where="mid", color="#009E73", lw=2, label=f"hysteresis+dwell ({stable['switch_count']} switches)")
    axes[1].set_yticks([0, 1], ["expert 0", "expert 1"])
    axes[1].set_xlabel("decision step")
    axes[1].set_title("Explicit gate state suppresses chatter without missing either transition")
    axes[1].legend(ncol=3)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run() -> dict:
    margins, truth = chatter_scenario()
    naive = replay_gate(GatingPolicy(IdentityLogits(), 2, mode="hard"), margins, truth)
    stable = replay_gate(
        GatingPolicy(
            IdentityLogits(),
            2,
            mode="hard",
            hysteresis=0.25,
            min_dwell_steps=2,
        ),
        margins,
        truth,
    )
    results = {
        "experiment": "structured neural residual and explicit-state gating analytical oracles",
        "kinopulse_version": version("kinopulse"),
        "wheel_sha256": WHEEL_SHA256,
        "scenario": {
            "score_margin": margins,
            "true_expert": truth,
            "candidate_dynamics": [-1.0, 1.0],
            "hysteresis": 0.25,
            "minimum_dwell_steps": 2,
        },
        "naive_hard_gate": naive,
        "hysteretic_dwell_gate": stable,
        "straight_through_oracle": straight_through_oracle(),
        "structured_residual_oracles": residual_oracles(),
        "scope": "synthetic release validation only; no ENSO data or frozen forecast was used",
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    plot_results(results)
    return results


if __name__ == "__main__":
    outcome = run()
    print(f"Naive switches: {outcome['naive_hard_gate']['switch_count']}")
    print(f"Stabilized switches: {outcome['hysteretic_dwell_gate']['switch_count']}")
    print(f"Straight-through gradient norm: {outcome['straight_through_oracle']['gradient_norm']:.6f}")
    print(f"Wrote {ARTIFACT_PATH}")
    print(f"Wrote {FIGURE_PATH}")
