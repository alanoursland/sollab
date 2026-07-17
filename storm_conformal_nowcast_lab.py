"""Chronological group-conformal bands for causal one-hour Dst predictions."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path

import matplotlib
import numpy as np
from scipy.stats import spearmanr
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.opt.least_squares import RidgeSolver
from kinopulse.validation import (
    PrequentialIntervalCalibrator,
    SelectivePredictionAudit,
    SplitConformalIntervalCalibrator,
)
from multi_storm_transfer_lab import (
    POST_HOURS,
    PRE_HOURS,
    PopulationData,
    Storm,
    load_population,
    select_storms,
)
from open_source_commit_ecology_lab import DTYPE


MAXIMUM_FORWARD_FILL_HOURS = 24
NOMINAL_COVERAGE = 0.8


@dataclass(frozen=True)
class CausalDstModel:
    coefficients: torch.Tensor
    feature_mean: torch.Tensor
    feature_scale: torch.Tensor
    training_years: tuple[int, int]


@dataclass(frozen=True)
class StormErrorPath:
    storm: Storm
    relative_target_hours: np.ndarray
    errors_nt: np.ndarray

    @property
    def pre_errors(self) -> np.ndarray:
        return self.errors_nt[self.relative_target_hours <= 0]

    @property
    def post_errors(self) -> np.ndarray:
        return self.errors_nt[self.relative_target_hours > 0]

    @property
    def pre_max_absolute_error_nt(self) -> float:
        return float(np.max(np.abs(self.pre_errors)))

    @property
    def post_max_absolute_error_nt(self) -> float:
        return float(np.max(np.abs(self.post_errors)))


def finite_required(values: torch.Tensor, sentinel: float) -> torch.Tensor:
    return torch.isfinite(values) & (values < sentinel)


def causal_forward_fill(
    values: torch.Tensor,
    valid: torch.Tensor,
    maximum_age_hours: int,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    """Carry the latest valid observation forward without looking ahead."""
    if maximum_age_hours < 0:
        raise ValueError("maximum_age_hours must be nonnegative")
    result = values.clone()
    result_valid = valid.clone()
    ages = torch.full(valid.shape, -1, dtype=torch.int64, device=valid.device)
    last_valid = -maximum_age_hours - 1
    for index in range(len(values)):
        if bool(valid[index]):
            last_valid = index
            ages[index] = 0
        elif index - last_valid <= maximum_age_hours:
            result[index] = result[last_valid]
            result_valid[index] = True
            ages[index] = index - last_valid
    return result, result_valid, ages


def causal_fill_forcing(
    data: PopulationData,
    maximum_age_hours: int = MAXIMUM_FORWARD_FILL_HOURS,
) -> tuple[PopulationData, dict]:
    electric, electric_valid, electric_age = causal_forward_fill(
        data.electric_field,
        finite_required(data.electric_field, 900),
        maximum_age_hours,
    )
    pressure, pressure_valid, pressure_age = causal_forward_fill(
        data.pressure,
        finite_required(data.pressure, 90),
        maximum_age_hours,
    )
    filled = replace(data, electric_field=electric, pressure=pressure)
    return filled, {
        "maximum_forward_fill_age_hours": maximum_age_hours,
        "electric_hours_filled": int((electric_age > 0).sum()),
        "pressure_hours_filled": int((pressure_age > 0).sum()),
        "maximum_electric_fill_age_used": int(electric_age.max()),
        "maximum_pressure_fill_age_used": int(pressure_age.max()),
        "electric_valid_after_fill": int(electric_valid.sum()),
        "pressure_valid_after_fill": int(pressure_valid.sum()),
    }


def causal_design(data: PopulationData) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
    """Predict Dst[t+1]-Dst[t] using information available at t."""
    dst_valid = finite_required(data.dst, 90000)
    electric_valid = finite_required(data.electric_field, 900)
    pressure_valid = finite_required(data.pressure, 90)
    consecutive_previous = torch.tensor(
        [right - left == timedelta(hours=1) for left, right in zip(data.timestamps[:-1], data.timestamps[1:])],
        dtype=torch.bool,
    )
    consecutive_next = consecutive_previous.clone()
    indices = torch.arange(1, len(data.dst) - 1)
    valid = (
        dst_valid[indices]
        & dst_valid[indices + 1]
        & electric_valid[indices]
        & pressure_valid[indices]
        & pressure_valid[indices - 1]
        & consecutive_previous[indices - 1]
        & consecutive_next[indices]
    )
    features = torch.stack(
        (
            torch.ones_like(data.dst[indices]),
            data.dst[indices],
            data.electric_field[indices].clamp_min(0),
            data.pressure[indices] - data.pressure[indices - 1],
        ),
        dim=1,
    )
    target = data.dst[indices + 1] - data.dst[indices]
    return indices, features, target, valid


def fit_causal_model(
    data: PopulationData, training_years: tuple[int, int] = (2010, 2015)
) -> CausalDstModel:
    indices, features, target, valid = causal_design(data)
    years = data.year[indices]
    selected = valid & (years >= training_years[0]) & (years <= training_years[1])
    if not bool(selected.any()):
        raise ValueError("no valid causal training rows")
    mean = features[selected, 1:].mean(dim=0)
    scale = features[selected, 1:].std(dim=0).clamp_min(1e-12)
    standardized = torch.cat((features[:, :1], (features[:, 1:] - mean) / scale), dim=1)
    coefficients = RidgeSolver(lambda_=0.01).solve(standardized[selected], target[selected]).x
    return CausalDstModel(coefficients, mean, scale, training_years)


def causal_valid_mask(data: PopulationData) -> torch.Tensor:
    indices, _, _, valid = causal_design(data)
    mask = torch.zeros(len(data.dst), dtype=torch.bool)
    mask[indices] = valid
    return mask


def eligible_storms(data: PopulationData) -> list[Storm]:
    valid = causal_valid_mask(data)
    result = []
    for storm in select_storms(data):
        start, stop = storm.index - PRE_HOURS, storm.index + POST_HOURS
        complete = start >= 1 and stop < len(data.dst) and bool(valid[start:stop].all())
        result.append(replace(storm, complete_forcing_window=complete))
    return result


def storm_error_path(data: PopulationData, storm: Storm, model: CausalDstModel) -> StormErrorPath:
    if not storm.complete_forcing_window:
        raise ValueError("storm is not eligible for causal prediction")
    start, stop = storm.index - PRE_HOURS, storm.index + POST_HOURS
    errors = []
    relative_hours = []
    for index in range(start, stop):
        raw = torch.tensor(
            [
                1.0,
                float(data.dst[index]),
                float(data.electric_field[index].clamp_min(0)),
                float(data.pressure[index] - data.pressure[index - 1]),
            ],
            dtype=DTYPE,
        )
        design = torch.cat((raw[:1], (raw[1:] - model.feature_mean) / model.feature_scale))
        predicted_next = float(data.dst[index]) + float(design @ model.coefficients)
        errors.append(predicted_next - float(data.dst[index + 1]))
        relative_hours.append(index + 1 - storm.index)
    return StormErrorPath(storm, np.asarray(relative_hours), np.asarray(errors))


def calibration_thresholds(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "median": ordered[math.ceil(len(ordered) * 0.5) - 1],
        "eighty_percent": ordered[math.ceil(len(ordered) * 0.8) - 1],
        "maximum": ordered[-1],
    }


def run_experiment(
    manifest_path: Path = Path("data/omni_population/manifest.json"),
) -> tuple[dict, list[StormErrorPath], list[StormErrorPath]]:
    original = load_population(manifest_path)
    data, fill_summary = causal_fill_forcing(original)
    storms = eligible_storms(data)
    model = fit_causal_model(data)
    calibration = [
        storm_error_path(data, storm, model)
        for storm in storms
        if storm.complete_forcing_window and 2016 <= storm.timestamp.year <= 2018
    ]
    test = [
        storm_error_path(data, storm, model)
        for storm in storms
        if storm.complete_forcing_window and 2019 <= storm.timestamp.year <= 2025
    ]
    if not calibration or not test:
        raise RuntimeError("frozen chronology produced no calibration or test storms")

    calibration_ids = [path.storm.timestamp.isoformat() for path in calibration]
    calibration_scores = [path.post_max_absolute_error_nt for path in calibration]
    split = SplitConformalIntervalCalibrator(
        coverage=NOMINAL_COVERAGE,
        mode="joint",
        group_ids=calibration_ids,
        ordering=[path.storm.timestamp.isoformat() for path in calibration],
    ).fit(
        lower=[0.0] * len(calibration),
        upper=[0.0] * len(calibration),
        observed=calibration_scores,
    )
    fixed_radius = float(split.joint_correction)

    all_paths = calibration + test
    all_ids = [path.storm.timestamp.isoformat() for path in all_paths]
    all_available = [
        path.storm.timestamp + timedelta(hours=POST_HOURS) for path in all_paths
    ]
    all_post_scores = [path.post_max_absolute_error_nt for path in all_paths]
    prequential = PrequentialIntervalCalibrator(
        group_ids=all_ids,
        outcome_available_times=all_available,
        lower=[0.0] * len(all_paths),
        upper=[0.0] * len(all_paths),
        observed=all_post_scores,
        coverage=NOMINAL_COVERAGE,
        mode="joint",
    )
    issues = [
        prequential.issue(
            group_id=path.storm.timestamp.isoformat(),
            decision_time=path.storm.timestamp,
            lower=0.0,
            upper=0.0,
        )
        for path in test
    ]
    radii = [float(issue.adjusted_upper) for issue in issues]
    covered = [path.post_max_absolute_error_nt <= radius for path, radius in zip(test, radii)]

    histories = [()] * len(calibration) + [issue.calibration_group_ids for issue in issues]
    audit = SelectivePredictionAudit(
        group_ids=all_ids,
        decision_times=[path.storm.timestamp for path in all_paths],
        outcome_available_times=all_available,
        history_ids=histories,
    )
    thresholds = calibration_thresholds(
        [path.pre_max_absolute_error_nt for path in calibration]
    )
    eligible = [False] * len(calibration) + [True] * len(test)
    predictions = (
        [0.0] * len(calibration) + [-radius for radius in radii],
        [0.0] * len(calibration) + radii,
    )
    curve = audit.coverage_retention_curve(
        predictions=predictions,
        outcomes=all_post_scores,
        scores=[path.pre_max_absolute_error_nt for path in all_paths],
        thresholds=list(thresholds.values()),
        issue_when="score_leq",
        prospective=True,
        eligible=eligible,
        policy={"score": "maximum absolute pre-minimum one-hour error"},
    )
    policy_results = [
        {
            "label": label,
            "threshold_nt": threshold,
            "summary": evaluation.to_dict()["summary"],
        }
        for (label, threshold), evaluation in zip(thresholds.items(), curve.results)
    ]
    correlation = spearmanr(
        [path.pre_max_absolute_error_nt for path in test],
        [path.post_max_absolute_error_nt for path in test],
    )
    hourly_covered = sum(
        int(np.sum(np.abs(path.post_errors) <= radius)) for path, radius in zip(test, radii)
    )
    hourly_total = sum(len(path.post_errors) for path in test)

    event_rows = []
    for path, issue, radius, is_covered in zip(test, issues, radii, covered):
        event_rows.append(
            {
                "timestamp_utc": path.storm.timestamp.isoformat(),
                "minimum_dst_nt": path.storm.minimum_dst_nt,
                "pre_max_absolute_error_nt": path.pre_max_absolute_error_nt,
                "post_max_absolute_error_nt": path.post_max_absolute_error_nt,
                "prequential_radius_nt": radius,
                "simultaneously_covered": is_covered,
                "calibration_group_count": len(issue.calibration_group_ids),
                "latest_calibration_outcome_utc": issue.latest_outcome_available_time.isoformat(),
            }
        )

    result = {
        "experiment": "chronological group-conformal bands for causal one-hour Dst predictions",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "source_years": [2010, 2025],
        "information_contract": {
            "prediction": "Dst[t+1] from Dst[t], electric field[t], and pressure[t]-pressure[t-1]",
            "missing_forcing": "last observation carried forward for at most 24 hours; no future interpolation",
            "calibration_group": "one selected storm; score is maximum absolute post-minimum hourly error",
            "decision_time": "selected Dst minimum; pre-minimum errors and matured earlier storms only",
            "selection_boundary": "storm centers are retrospectively selected local Dst minima",
        },
        "forcing_fill": fill_summary,
        "chronology": {
            "fit_years": [2010, 2015],
            "calibration_years": [2016, 2018],
            "test_years": [2019, 2025],
            "calibration_storms": len(calibration),
            "test_storms": len(test),
        },
        "eligible_storm_counts": {
            "all_candidates": len(storms),
            "all_complete": sum(storm.complete_forcing_window for storm in storms),
            "calibration_candidates": sum(2016 <= storm.timestamp.year <= 2018 for storm in storms),
            "test_candidates": sum(storm.timestamp.year >= 2019 for storm in storms),
        },
        "model": {
            "coefficients": model.coefficients.tolist(),
            "feature_mean": model.feature_mean.tolist(),
            "feature_scale": model.feature_scale.tolist(),
        },
        "fixed_split_conformal": {
            **split.to_dict(),
            "radius_nt": fixed_radius,
            "test_simultaneous_coverage": sum(path.post_max_absolute_error_nt <= fixed_radius for path in test) / len(test),
        },
        "prequential_conformal": {
            "nominal_group_coverage": NOMINAL_COVERAGE,
            "simultaneous_storm_coverage": sum(covered) / len(covered),
            "covered_storms": sum(covered),
            "missed_storms": len(covered) - sum(covered),
            "hourly_marginal_coverage": hourly_covered / hourly_total,
            "mean_radius_nt": float(np.mean(radii)),
            "minimum_radius_nt": min(radii),
            "maximum_radius_nt": max(radii),
            "events": event_rows,
        },
        "selective_prediction": {
            "thresholds_from_calibration_only_nt": thresholds,
            "pre_post_error_spearman": float(correlation.statistic),
            "pre_post_error_spearman_pvalue": float(correlation.pvalue),
            "coverage_retention_curve": curve.to_dict(),
            "policy_results": policy_results,
        },
        "interpretation_boundary": (
            "one-hour predictions are causal within retrospectively selected storm windows; "
            "this is not prospective storm detection and exchangeability is not assumed"
        ),
    }
    return result, calibration, test


def render_figure(result: dict, test: list[StormErrorPath], output_path: Path) -> None:
    events = result["prequential_conformal"]["events"]
    positions = np.arange(len(events))
    errors = np.array([event["post_max_absolute_error_nt"] for event in events])
    radii = np.array([event["prequential_radius_nt"] for event in events])
    covered = np.array([event["simultaneously_covered"] for event in events])
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)

    ax = axes[0, 0]
    ax.plot(positions, radii, color="#1565c0", marker="o", label="prequential radius")
    ax.scatter(positions[covered], errors[covered], color="#2e7d32", label="covered max error", zorder=3)
    ax.scatter(positions[~covered], errors[~covered], color="#c62828", marker="x", s=55, label="missed max error", zorder=3)
    ax.set(xlabel="chronological test-storm index", ylabel="nT", title="Simultaneous recovery-path coverage")
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)

    deepest_index = int(np.argmin([path.storm.minimum_dst_nt for path in test]))
    deepest = test[deepest_index]
    ax = axes[0, 1]
    ax.plot(deepest.relative_target_hours[deepest.relative_target_hours > 0], np.abs(deepest.post_errors), color="black")
    ax.axhline(radii[deepest_index], color="#1565c0", linestyle="--", label="issued radius")
    ax.set(
        xlabel="hours after selected Dst minimum",
        ylabel="absolute one-hour error (nT)",
        title=f"Deepest test storm ({deepest.storm.timestamp:%Y-%m-%d}, {deepest.storm.minimum_dst_nt:.0f} nT)",
    )
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)

    ax = axes[1, 0]
    pre = np.array([path.pre_max_absolute_error_nt for path in test])
    post = np.array([path.post_max_absolute_error_nt for path in test])
    ax.scatter(pre, post, c=[path.storm.timestamp.year for path in test], cmap="viridis", edgecolor="black")
    ax.set(
        xlabel="known pre-minimum max error (nT)",
        ylabel="future recovery max error (nT)",
        title=f"Prospective abstention score: Spearman {result['selective_prediction']['pre_post_error_spearman']:.2f}",
    )
    ax.grid(alpha=0.2)

    ax = axes[1, 1]
    points = result["selective_prediction"]["coverage_retention_curve"]["points"]
    retention = [point["retention"] for point in points]
    coverage = [point["coverage"] for point in points]
    labels = list(result["selective_prediction"]["thresholds_from_calibration_only_nt"])
    ax.plot(retention, coverage, marker="o", color="#6a1b9a")
    grouped_labels: dict[tuple[float, float], list[str]] = {}
    for x, y, label in zip(retention, coverage, labels):
        grouped_labels.setdefault((x, y), []).append(label.replace("eighty_percent", "80th"))
    for (x, y), point_labels in grouped_labels.items():
        offset = (5, -18) if y > 0.95 else (5, 5)
        ax.annotate(" / ".join(point_labels), (x, y), xytext=offset, textcoords="offset points")
    ax.axhline(NOMINAL_COVERAGE, color="gray", linestyle="--", label="nominal 80%")
    ax.set(xlabel="test-storm retention", ylabel="issued simultaneous coverage", title="Calibration-only abstention thresholds")
    ax.set_xlim(0, 1.03)
    ax.set_ylim(0, 1.03)
    ax.legend(frameon=False)
    ax.grid(alpha=0.2)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(
    manifest_path: Path = Path("data/omni_population/manifest.json"),
    artifact_path: Path = Path("artifacts/storm_conformal_nowcast.json"),
    figure_path: Path = Path("artifacts/storm_conformal_nowcast.png"),
) -> dict:
    result, _, test = run_experiment(manifest_path)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render_figure(result, test, figure_path)
    print(f"Wrote {artifact_path} (sha256 {hashlib.sha256(artifact_path.read_bytes()).hexdigest()})")
    print(f"Wrote {figure_path}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=Path("data/omni_population/manifest.json"))
    parser.add_argument("--artifact", type=Path, default=Path("artifacts/storm_conformal_nowcast.json"))
    parser.add_argument("--figure", type=Path, default=Path("artifacts/storm_conformal_nowcast.png"))
    arguments = parser.parse_args()
    main(arguments.manifest, arguments.artifact, arguments.figure)
