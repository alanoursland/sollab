"""Audit KinoPulse online change detection on controlled and aftershock residual streams."""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.identification.online.adaptation import ChangeDetector

from aftershock_hierarchy_lab import fit_hierarchical_target, robust_population
from aftershock_lab import DTYPE, fit_relaxation_model
from aftershock_meta_lab import load_population_manifest
from aftershock_transfer_lab import CALIBRATION_END_DAYS, load_sequence, make_transfer_bins


SYNTHETIC_CONFIGS = (
    ("window_w12", "window", 12, 3.0),
    ("cusum_w12", "cusum", 12, 3.0),
    ("glr_w12", "glr", 12, 3.0),
    ("glr_w20", "glr", 20, 3.0),
)
AFTERSHOCK_CONFIGS = (
    ("window_w8", "window", 8, 6.0),
    ("cusum_w8", "cusum", 8, 2.0),
    ("glr_w20", "glr", 20, 3.0),
)


def detector_alarms(
    values: list[float], method: str, window_size: int, threshold: float
) -> list[int]:
    detector = ChangeDetector(
        window_size=window_size, threshold=threshold, method=method
    )
    return [index for index, value in enumerate(values) if detector.update(value)]


def poisson_deviance_contributions(
    observed: torch.Tensor, expected: torch.Tensor
) -> torch.Tensor:
    expected = expected.clamp_min(1e-12)
    log_term = torch.where(
        observed > 0,
        observed * torch.log(observed / expected),
        torch.zeros_like(expected),
    )
    return 2.0 * (log_term - (observed - expected))


def synthetic_audit() -> dict:
    streams = {
        "stable": [0.0] * 60,
        "persistent_step": [0.0] * 30 + [5.0] * 30,
        "single_spike": [0.0] * 30 + [8.0] + [0.0] * 29,
    }
    results = {}
    for stream_name, values in streams.items():
        results[stream_name] = {}
        for name, method, window_size, threshold in SYNTHETIC_CONFIGS:
            results[stream_name][name] = detector_alarms(
                values, method, window_size, threshold
            )

    detector = ChangeDetector(window_size=20, threshold=1.0, method="window")
    for value in streams["persistent_step"][:35]:
        detector.update(value)
    before = {
        "n_updates": detector.n_updates,
        "n_changes_detected": detector.n_changes_detected,
        "last_change_index": detector.last_change_index,
        "buffer_length": len(detector.errors),
    }
    detector.reset()
    after = {
        "n_updates": detector.n_updates,
        "n_changes_detected": detector.n_changes_detected,
        "last_change_index": detector.last_change_index,
        "buffer_length": len(detector.errors),
    }
    return {
        "streams": streams,
        "configurations": [
            {
                "name": name,
                "method": method,
                "window_size": window_size,
                "threshold": threshold,
            }
            for name, method, window_size, threshold in SYNTHETIC_CONFIGS
        ],
        "alarms": results,
        "reset_probe": {"before": before, "after": after},
    }


def aftershock_audit(
    data_dir: Path = Path("data/aftershock_population"),
    artifact_dir: Path = Path("artifacts"),
) -> dict:
    hierarchy = json.loads(
        (artifact_dir / "aftershock_population_hierarchy.json").read_text(
            encoding="utf-8"
        )
    )
    specs, _ = load_population_manifest(data_dir / "manifest.json")
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    evaluation_indices = torch.nonzero(evaluation_mask).flatten()
    evaluation_end_days = edges[1:][evaluation_mask]
    sequences = [load_sequence(spec, edges, data_dir) for spec in specs]
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)
    full_fits = [
        fit_relaxation_model(
            "omori", edges, sequence.counts, all_mask, sequence.background
        )
        for sequence in sequences
    ]

    records = []
    for index, sequence in enumerate(sequences):
        fold = hierarchy["folds"][index]
        population = robust_population(
            full_fits, [other for other in range(len(sequences)) if other != index]
        )
        fit = fit_hierarchical_target(
            sequence,
            edges,
            calibration_mask,
            population,
            fold["selected_pooling_strength"],
        )
        contributions = poisson_deviance_contributions(
            sequence.counts[evaluation_mask], fit.expected_counts[evaluation_mask]
        )
        alarms = {}
        for name, method, window_size, threshold in AFTERSHOCK_CONFIGS:
            indices = detector_alarms(
                contributions.tolist(), method, window_size, threshold
            )
            alarms[name] = {
                "indices": indices,
                "first_end_day": (
                    float(evaluation_end_days[indices[0]]) if indices else None
                ),
            }
        records.append(
            {
                "event_id": sequence.spec.event_id,
                "name": sequence.spec.name,
                "evaluation_bin_indices": evaluation_indices.tolist(),
                "evaluation_end_days": evaluation_end_days.tolist(),
                "deviance_contributions": contributions.tolist(),
                "total_deviance": float(contributions.sum()),
                "population_predictive_total_miss": not fold[
                    "predictive_distribution"
                ]["total_covered"],
                "alarms": alarms,
            }
        )
    return {
        "input": "held-out per-bin Poisson deviance from the expanded hierarchy",
        "configurations": [
            {
                "name": name,
                "method": method,
                "window_size": window_size,
                "threshold": threshold,
            }
            for name, method, window_size, threshold in AFTERSHOCK_CONFIGS
        ],
        "records": records,
    }


def make_figure(report: dict, target: Path) -> None:
    synthetic = report["synthetic"]
    aftershocks = report["aftershocks"]["records"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    step_axis, spike_axis, heat_axis, outcome_axis = axes.ravel()
    colors = {
        "window_w12": "#d63031",
        "cusum_w12": "#0984e3",
        "glr_w12": "#6c5ce7",
        "glr_w20": "#00b894",
    }
    for axis, stream_name, title in (
        (step_axis, "persistent_step", "Persistent synthetic step"),
        (spike_axis, "single_spike", "Single synthetic spike"),
    ):
        values = synthetic["streams"][stream_name]
        axis.plot(values, color="#2d3436", linewidth=1.5, label="input error")
        for name, alarm_indices in synthetic["alarms"][stream_name].items():
            if alarm_indices:
                axis.scatter(
                    alarm_indices,
                    [values[index] for index in alarm_indices],
                    s=24,
                    color=colors[name],
                    label=f"{name}: {len(alarm_indices)} alarms",
                )
        axis.set(title=title, xlabel="update", ylabel="error")
        axis.legend(frameon=False, fontsize=8)
        axis.grid(alpha=0.2)

    matrix = torch.tensor(
        [record["deviance_contributions"] for record in aftershocks], dtype=DTYPE
    )
    image = heat_axis.imshow(torch.log1p(matrix).numpy(), aspect="auto", cmap="magma")
    for row, record in enumerate(aftershocks):
        indices = record["alarms"]["window_w8"]["indices"]
        if indices:
            heat_axis.scatter(indices[0], row, marker="x", color="white", s=48)
    heat_axis.set_yticks(range(len(aftershocks)), [r["event_id"] for r in aftershocks])
    heat_axis.set(
        title="Aftershock forecast surprise (white × = first window alarm)",
        xlabel="evaluation bin after day 1",
        ylabel="held-out sequence",
    )
    fig.colorbar(image, ax=heat_axis, label="log(1 + bin Poisson deviance)")

    misses = [r for r in aftershocks if r["population_predictive_total_miss"]]
    covered = [r for r in aftershocks if not r["population_predictive_total_miss"]]
    groups = (misses, covered)
    alarmed = [sum(bool(r["alarms"]["window_w8"]["indices"]) for r in group) for group in groups]
    quiet = [len(group) - count for group, count in zip(groups, alarmed)]
    outcome_axis.bar((0, 1), alarmed, label="at least one alarm", color="#d63031")
    outcome_axis.bar((0, 1), quiet, bottom=alarmed, label="no alarm", color="#b2bec3")
    outcome_axis.set_xticks((0, 1), ("predictive total\nmiss", "predictive total\ncovered"))
    outcome_axis.set(
        title="Window detector is sensitive but nonspecific",
        ylabel="sequence count",
    )
    outcome_axis.legend(frameon=False)
    outcome_axis.grid(axis="y", alpha=0.2)
    fig.suptitle("KinoPulse ChangeDetector contract and residual-stream audit")
    fig.savefig(target, dpi=180)
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = {
        "experiment": "KinoPulse ChangeDetector contract and aftershock residual audit",
        "synthetic": synthetic_audit(),
        "aftershocks": aftershock_audit(artifact_dir=output_dir),
    }
    result_path = output_dir / "change_detector_analysis.json"
    figure_path = output_dir / "change_detector_lab.png"
    result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    make_figure(report, figure_path)
    summary = {
        "synthetic_step_alarm_counts": {
            key: len(value)
            for key, value in report["synthetic"]["alarms"][
                "persistent_step"
            ].items()
        },
        "synthetic_spike_alarm_counts": {
            key: len(value)
            for key, value in report["synthetic"]["alarms"]["single_spike"].items()
        },
        "reset_probe": report["synthetic"]["reset_probe"],
        "aftershock_first_alarm_counts": {
            config[0]: sum(
                bool(record["alarms"][config[0]]["indices"])
                for record in report["aftershocks"]["records"]
            )
            for config in AFTERSHOCK_CONFIGS
        },
    }
    print(json.dumps(summary, indent=2))
    print(f"Wrote {result_path} and {figure_path}")


if __name__ == "__main__":
    main()
