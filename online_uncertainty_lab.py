"""Prequential grouped interval calibration with a 30-day outcome embargo."""

from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from external_uncertainty_lab import (
    ALPHA,
    apply_interval_calibration,
    fit_interval_calibration,
)


MINIMUM_HISTORY = 12
ROLLING_WINDOW = 12
OUTCOME_MATURITY_DAYS = 30


def _origin(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def available_history_indices(
    folds: list[dict], target_index: int, maturity_days: int = OUTCOME_MATURITY_DAYS
) -> list[int]:
    """Return earlier sequences whose outcome windows have fully matured."""
    target_time = _origin(folds[target_index]["time"])
    return [
        index
        for index in range(target_index)
        if _origin(folds[index]["time"]) + timedelta(days=maturity_days)
        <= target_time
    ]


def _raw_interval(fold: dict) -> tuple[float, float]:
    predictive = fold["predictive_distribution"]
    return float(predictive["total_p10"]), float(predictive["total_p90"])


def prequential_forecasts(
    folds: list[dict],
    *,
    mode: str,
    minimum_history: int = MINIMUM_HISTORY,
    rolling_window: int = ROLLING_WINDOW,
) -> dict:
    if mode not in {"raw", "expanding", "rolling"}:
        raise ValueError("mode must be 'raw', 'expanding', or 'rolling'")
    if minimum_history < 1 or rolling_window < 1:
        raise ValueError("history sizes must be positive")
    ordered = sorted(folds, key=lambda fold: fold["time"])
    rows = []
    skipped = []
    for target_index, target in enumerate(ordered):
        available = available_history_indices(ordered, target_index)
        if len(available) < minimum_history:
            skipped.append(target["event_id"])
            continue
        if mode == "rolling":
            used = available[-rolling_window:]
        else:
            used = available
        raw_lower, raw_upper = _raw_interval(target)
        calibration = None
        if mode == "raw":
            lower, upper = raw_lower, raw_upper
        else:
            calibration = fit_interval_calibration(
                [ordered[index] for index in used],
                alpha=ALPHA,
                asymmetric=True,
            )
            lower, upper = apply_interval_calibration(target, calibration)
        observed = float(target["evaluation_events"])
        rows.append(
            {
                "event_id": target["event_id"],
                "name": target["name"],
                "time": target["time"],
                "observed": observed,
                "median": float(
                    target["predictive_distribution"]["total_median"]
                ),
                "raw_lower": raw_lower,
                "raw_upper": raw_upper,
                "lower": lower,
                "upper": upper,
                "covered": lower <= observed <= upper,
                "below": observed < lower,
                "above": observed > upper,
                "multiplicative_width": (upper + 0.5) / (lower + 0.5),
                "available_history_count": len(available),
                "used_history_count": len(used),
                "used_event_ids": [ordered[index]["event_id"] for index in used],
                "latest_used_time": ordered[used[-1]]["time"],
                "lower_log_expansion": (
                    0.0 if calibration is None else calibration.lower_log_expansion
                ),
                "upper_log_expansion": (
                    0.0 if calibration is None else calibration.upper_log_expansion
                ),
            }
        )
    return {
        "mode": mode,
        "minimum_history": minimum_history,
        "rolling_window": rolling_window if mode == "rolling" else None,
        "maturity_days": OUTCOME_MATURITY_DAYS,
        "skipped_event_ids": skipped,
        "rows": rows,
    }


def summarize_rows(rows: list[dict]) -> dict:
    widths = sorted(row["multiplicative_width"] for row in rows)
    middle = len(widths) // 2
    median_width = (
        widths[middle]
        if len(widths) % 2
        else 0.5 * (widths[middle - 1] + widths[middle])
    )
    return {
        "sequence_count": len(rows),
        "covered": sum(row["covered"] for row in rows),
        "coverage": sum(row["covered"] for row in rows) / len(rows),
        "below": sum(row["below"] for row in rows),
        "above": sum(row["above"] for row in rows),
        "median_multiplicative_width": median_width,
    }


def run_online_calibration(
    evidence_path: Path = Path("artifacts/external_aftershock_validation.json"),
) -> dict:
    source = json.loads(evidence_path.read_text(encoding="utf-8"))
    methods = {
        mode: prequential_forecasts(source["folds"], mode=mode)
        for mode in ("raw", "expanding", "rolling")
    }
    evaluation_ids = [row["event_id"] for row in methods["raw"]["rows"]]
    if any(
        [row["event_id"] for row in methods[mode]["rows"]] != evaluation_ids
        for mode in methods
    ):
        raise RuntimeError("online methods evaluated different targets")
    for method in methods.values():
        method["overall"] = summarize_rows(method["rows"])
        later = [row for row in method["rows"] if row["time"] >= "2020-01-01"]
        method["from_2020"] = summarize_rows(later)
    return {
        "experiment": "prequential external-domain uncertainty calibration",
        "claim_boundary": (
            "post-hoc method study; every interval uses only fully matured "
            "outcomes from earlier Alaska-sector sequences"
        ),
        "source_experiment": source["experiment"],
        "target_coverage": 1.0 - ALPHA,
        "minimum_history": MINIMUM_HISTORY,
        "rolling_window": ROLLING_WINDOW,
        "outcome_maturity_days": OUTCOME_MATURITY_DAYS,
        "evaluation_event_ids": evaluation_ids,
        "methods": methods,
    }


def plot_online_calibration(report: dict, output_path: Path) -> None:
    colors = {"raw": "#636e72", "expanding": "#0984e3", "rolling": "#00b894"}
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    cumulative_axis, width_axis, expansion_axis, later_axis = axes.ravel()

    for mode, method in report["methods"].items():
        cumulative = []
        covered = 0
        for index, row in enumerate(method["rows"], start=1):
            covered += row["covered"]
            cumulative.append(covered / index)
        cumulative_axis.plot(
            range(1, len(cumulative) + 1),
            cumulative,
            marker="o",
            markersize=3,
            label=mode,
            color=colors[mode],
        )
    cumulative_axis.axhline(
        report["target_coverage"], color="#d63031", linestyle="--", label="target"
    )
    cumulative_axis.set(
        title="Prequential cumulative coverage",
        xlabel="issued external intervals",
        ylabel="coverage through forecast",
        ylim=(0, 1),
    )
    cumulative_axis.legend(frameon=False)
    cumulative_axis.grid(alpha=0.2)

    modes = list(report["methods"])
    width_axis.bar(
        modes,
        [report["methods"][mode]["overall"]["median_multiplicative_width"] for mode in modes],
        color=[colors[mode] for mode in modes],
    )
    width_axis.set(
        title="Sharpness cost over common targets",
        ylabel="median multiplicative interval width",
    )

    for mode in ("expanding", "rolling"):
        rows = report["methods"][mode]["rows"]
        expansion_axis.plot(
            [row["time"][:10] for row in rows],
            [math.exp(row["lower_log_expansion"]) for row in rows],
            marker="o",
            markersize=3,
            label=f"{mode} lower factor",
            color=colors[mode],
        )
    expansion_axis.set(
        title="Online lower-tail adaptation",
        ylabel="multiplicative lower expansion",
    )
    expansion_axis.tick_params(axis="x", rotation=70, labelsize=7)
    expansion_axis.legend(frameon=False)
    expansion_axis.grid(alpha=0.2)

    late_modes = ["raw", "expanding", "rolling"]
    below = [report["methods"][mode]["from_2020"]["below"] for mode in late_modes]
    above = [report["methods"][mode]["from_2020"]["above"] for mode in late_modes]
    later_axis.bar(late_modes, below, label="below", color="#6c5ce7")
    later_axis.bar(late_modes, above, bottom=below, label="above", color="#e17055")
    for index, mode in enumerate(late_modes):
        summary = report["methods"][mode]["from_2020"]
        later_axis.text(
            index,
            below[index] + above[index] + 0.2,
            f"{summary['covered']}/{summary['sequence_count']}",
            ha="center",
        )
    later_axis.set(title="2020–2025 misses and coverage", ylabel="misses")
    later_axis.legend(frameon=False)

    fig.suptitle(
        "Prequential uncertainty calibration · only matured prior earthquake outcomes"
    )
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_online_calibration()
    (output_dir / "online_uncertainty_calibration.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_online_calibration(report, output_dir / "online_uncertainty_calibration.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
