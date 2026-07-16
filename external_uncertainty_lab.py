"""Chronologically recalibrate external aftershock predictive intervals."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


CUTOFF = "2020-01-01T00:00:00Z"
ALPHA = 0.2
COUNT_CORRECTION = 0.5


@dataclass(frozen=True)
class IntervalCalibration:
    method: str
    alpha: float
    calibration_count: int
    lower_log_expansion: float
    upper_log_expansion: float
    lower_rank: int
    upper_rank: int


def conservative_quantile(values: list[float], coverage: float) -> tuple[float, int]:
    """Return the split-conformal finite-sample order statistic and rank."""
    if not values:
        raise ValueError("values must not be empty")
    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must lie strictly between zero and one")
    rank = math.ceil((len(values) + 1) * coverage)
    if rank > len(values):
        return float("inf"), rank
    return sorted(values)[rank - 1], rank


def _fold_values(fold: dict) -> tuple[float, float, float, float]:
    predictive = fold["predictive_distribution"]
    return (
        float(fold["evaluation_events"]),
        float(predictive["total_p10"]),
        float(predictive["total_median"]),
        float(predictive["total_p90"]),
    )


def fit_interval_calibration(
    calibration_folds: list[dict],
    *,
    alpha: float = ALPHA,
    asymmetric: bool,
    count_correction: float = COUNT_CORRECTION,
) -> IntervalCalibration:
    if not calibration_folds:
        raise ValueError("calibration_folds must not be empty")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must lie strictly between zero and one")
    if count_correction <= 0 or not math.isfinite(count_correction):
        raise ValueError("count_correction must be finite and positive")

    lower_scores = []
    upper_scores = []
    joint_scores = []
    for fold in calibration_folds:
        observed, lower, _, upper = _fold_values(fold)
        lower_score = max(
            0.0,
            math.log((lower + count_correction) / (observed + count_correction)),
        )
        upper_score = max(
            0.0,
            math.log((observed + count_correction) / (upper + count_correction)),
        )
        lower_scores.append(lower_score)
        upper_scores.append(upper_score)
        joint_scores.append(max(lower_score, upper_score))

    if asymmetric:
        lower, lower_rank = conservative_quantile(
            lower_scores, 1.0 - alpha / 2.0
        )
        upper, upper_rank = conservative_quantile(
            upper_scores, 1.0 - alpha / 2.0
        )
        method = "asymmetric_tail_expansion"
    else:
        expansion, rank = conservative_quantile(joint_scores, 1.0 - alpha)
        lower = upper = expansion
        lower_rank = upper_rank = rank
        method = "symmetric_joint_expansion"
    return IntervalCalibration(
        method=method,
        alpha=alpha,
        calibration_count=len(calibration_folds),
        lower_log_expansion=lower,
        upper_log_expansion=upper,
        lower_rank=lower_rank,
        upper_rank=upper_rank,
    )


def apply_interval_calibration(
    fold: dict,
    calibration: IntervalCalibration,
    *,
    count_correction: float = COUNT_CORRECTION,
) -> tuple[float, float]:
    _, lower, _, upper = _fold_values(fold)
    calibrated_lower = max(
        0.0,
        (lower + count_correction)
        * math.exp(-calibration.lower_log_expansion)
        - count_correction,
    )
    calibrated_upper = (
        (upper + count_correction)
        * math.exp(calibration.upper_log_expansion)
        - count_correction
    )
    return calibrated_lower, calibrated_upper


def evaluate_intervals(
    folds: list[dict], calibration: IntervalCalibration | None = None
) -> dict:
    rows = []
    for fold in folds:
        observed, raw_lower, median, raw_upper = _fold_values(fold)
        if calibration is None:
            lower, upper = raw_lower, raw_upper
            method = "raw"
        else:
            lower, upper = apply_interval_calibration(fold, calibration)
            method = calibration.method
        rows.append(
            {
                "event_id": fold["event_id"],
                "name": fold["name"],
                "time": fold["time"],
                "observed": observed,
                "median": median,
                "lower": lower,
                "upper": upper,
                "covered": lower <= observed <= upper,
                "below": observed < lower,
                "above": observed > upper,
                "multiplicative_width": (upper + COUNT_CORRECTION)
                / (lower + COUNT_CORRECTION),
            }
        )
    widths = sorted(row["multiplicative_width"] for row in rows)
    middle = len(widths) // 2
    median_width = (
        widths[middle]
        if len(widths) % 2
        else 0.5 * (widths[middle - 1] + widths[middle])
    )
    return {
        "method": method,
        "sequence_count": len(rows),
        "covered": sum(row["covered"] for row in rows),
        "coverage": sum(row["covered"] for row in rows) / len(rows),
        "below": sum(row["below"] for row in rows),
        "above": sum(row["above"] for row in rows),
        "median_multiplicative_width": median_width,
        "rows": rows,
    }


def run_uncertainty_recalibration(
    evidence_path: Path = Path("artifacts/external_aftershock_validation.json"),
) -> dict:
    source = json.loads(evidence_path.read_text(encoding="utf-8"))
    calibration_folds = [fold for fold in source["folds"] if fold["time"] < CUTOFF]
    evaluation_folds = [fold for fold in source["folds"] if fold["time"] >= CUTOFF]
    symmetric = fit_interval_calibration(
        calibration_folds, alpha=ALPHA, asymmetric=False
    )
    asymmetric = fit_interval_calibration(
        calibration_folds, alpha=ALPHA, asymmetric=True
    )
    return {
        "experiment": "chronological external-domain interval recalibration",
        "claim_boundary": (
            "post-hoc follow-up to report 23; calibration uses pre-2020 Alaska-"
            "sector outcomes and evaluation uses 2020-2025 outcomes"
        ),
        "source_experiment": source["experiment"],
        "cutoff": CUTOFF,
        "target_coverage": 1.0 - ALPHA,
        "count_correction": COUNT_CORRECTION,
        "calibration_sequence_count": len(calibration_folds),
        "evaluation_sequence_count": len(evaluation_folds),
        "calibrations": {
            "symmetric": symmetric.__dict__,
            "asymmetric": asymmetric.__dict__,
        },
        "calibration_period": {
            "raw": evaluate_intervals(calibration_folds),
            "symmetric": evaluate_intervals(calibration_folds, symmetric),
            "asymmetric": evaluate_intervals(calibration_folds, asymmetric),
        },
        "evaluation_period": {
            "raw": evaluate_intervals(evaluation_folds),
            "symmetric": evaluate_intervals(evaluation_folds, symmetric),
            "asymmetric": evaluate_intervals(evaluation_folds, asymmetric),
        },
    }


def plot_uncertainty_recalibration(report: dict, output_path: Path) -> None:
    raw = report["evaluation_period"]["raw"]
    symmetric = report["evaluation_period"]["symmetric"]
    asymmetric = report["evaluation_period"]["asymmetric"]
    methods = [raw, symmetric, asymmetric]
    labels = ["raw", "symmetric", "asymmetric"]

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    coverage_axis, width_axis, interval_axis, tail_axis = axes.ravel()

    coverages = [method["coverage"] for method in methods]
    coverage_axis.bar(labels, coverages, color=["#636e72", "#0984e3", "#00b894"])
    coverage_axis.axhline(
        report["target_coverage"], color="#d63031", linestyle="--", label="target"
    )
    coverage_axis.set_ylim(0, 1.0)
    coverage_axis.set(title="2020–2025 total coverage", ylabel="fraction covered")
    coverage_axis.legend(frameon=False)

    widths = [method["median_multiplicative_width"] for method in methods]
    width_axis.bar(labels, widths, color=["#636e72", "#0984e3", "#00b894"])
    width_axis.set(
        title="Cost of calibration",
        ylabel="median multiplicative interval width",
    )

    rows = asymmetric["rows"]
    positions = list(range(len(rows)))
    observed = [row["observed"] for row in rows]
    median = [row["median"] for row in rows]
    lower = [row["lower"] for row in rows]
    upper = [row["upper"] for row in rows]
    interval_axis.errorbar(
        positions,
        median,
        yerr=[
            [center - low for center, low in zip(median, lower)],
            [high - center for center, high in zip(median, upper)],
        ],
        fmt="o",
        capsize=2,
        label="calibrated interval",
    )
    interval_axis.scatter(positions, observed, marker="x", color="#d63031", label="observed")
    interval_axis.set_yscale("log")
    interval_axis.set_xticks(
        positions,
        [f"{row['time'][:4]}\n{row['event_id']}" for row in rows],
        rotation=70,
        fontsize=7,
    )
    interval_axis.set(title="Asymmetric intervals on later sequences", ylabel="future total")
    interval_axis.legend(frameon=False)
    interval_axis.grid(alpha=0.2, which="both")

    x = list(range(len(methods)))
    below = [method["below"] for method in methods]
    above = [method["above"] for method in methods]
    tail_axis.bar(x, below, label="below interval", color="#6c5ce7")
    tail_axis.bar(x, above, bottom=below, label="above interval", color="#e17055")
    tail_axis.set_xticks(x, labels)
    tail_axis.set(title="Direction of evaluation misses", ylabel="sequences")
    tail_axis.legend(frameon=False)

    fig.suptitle(
        "Chronological uncertainty recalibration · pre-2020 calibration, 2020–2025 evaluation"
    )
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_uncertainty_recalibration()
    (output_dir / "external_uncertainty_recalibration.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_uncertainty_recalibration(
        report, output_dir / "external_uncertainty_recalibration.png"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
