"""Audit causal abstention signals for external aftershock count intervals."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from external_uncertainty_lab import conservative_quantile
from online_uncertainty_lab import available_history_indices, prequential_forecasts


SUPPORT_LIMIT = 2.5
CONSENSUS_COVERAGE = 0.8
SHARPNESS_MAX_WIDTH = 5.0
COUNT_CORRECTION = 0.5
FEATURE_NAMES = (
    "mainshock_magnitude",
    "log1p_depth_km",
    "log_background_rate",
    "log1p_day1_events",
)
MODEL_NAMES = ("frozen_hierarchy", "robust_pool", "target_day1")
WIDTH_SWEEP = (3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 15.0)


def forecast_inputs(fold: dict) -> tuple[dict[str, float], float]:
    """Return observable target-time inputs and model disagreement."""
    predictions = [
        float(fold["models"][name]["predicted_total"]) for name in MODEL_NAMES
    ]
    features = {
        "mainshock_magnitude": float(fold["magnitude"]),
        "log1p_depth_km": math.log1p(float(fold["depth_km"])),
        "log_background_rate": math.log(
            float(fold["background_rate_per_day"]) + 0.05
        ),
        "log1p_day1_events": math.log1p(float(fold["calibration_events"])),
    }
    disagreement = math.log(
        (max(predictions) + COUNT_CORRECTION)
        / (min(predictions) + COUNT_CORRECTION)
    )
    return features, disagreement


def robust_location_scale(values: list[float]) -> tuple[float, float]:
    if not values:
        raise ValueError("values must not be empty")
    location = statistics.median(values)
    mad = statistics.median(abs(value - location) for value in values)
    return location, max(1.4826 * mad, 1e-12)


def target_decision(target: dict, history: list[dict], forecast: dict) -> dict:
    """Compute abstention decisions without reading the target outcome."""
    if not history:
        raise ValueError("history must not be empty")
    target_features, disagreement = forecast_inputs(target)
    historical_inputs = [forecast_inputs(item) for item in history]
    feature_scores = {}
    for name in FEATURE_NAMES:
        location, scale = robust_location_scale(
            [features[name] for features, _ in historical_inputs]
        )
        feature_scores[name] = abs(target_features[name] - location) / scale
    support_score = max(feature_scores.values())
    consensus_threshold, consensus_rank = conservative_quantile(
        [item_disagreement for _, item_disagreement in historical_inputs],
        CONSENSUS_COVERAGE,
    )
    width = float(forecast["multiplicative_width"])
    policies = {
        "issue_all": True,
        "feature_support": support_score <= SUPPORT_LIMIT,
        "model_consensus": disagreement <= consensus_threshold,
        "sharpness_cap": width <= SHARPNESS_MAX_WIDTH,
    }
    policies["combined"] = all(
        policies[name]
        for name in ("feature_support", "model_consensus", "sharpness_cap")
    )
    return {
        "target_features": target_features,
        "feature_scores": feature_scores,
        "support_score": support_score,
        "support_limit": SUPPORT_LIMIT,
        "forecast_disagreement": disagreement,
        "consensus_threshold": consensus_threshold,
        "consensus_rank": consensus_rank,
        "sharpness_width": width,
        "sharpness_max_width": SHARPNESS_MAX_WIDTH,
        "policy_issue": policies,
    }


def audited_forecasts(folds: list[dict]) -> list[dict]:
    ordered = sorted(folds, key=lambda fold: fold["time"])
    forecasts = {
        row["event_id"]: row
        for row in prequential_forecasts(ordered, mode="rolling")["rows"]
    }
    rows = []
    for target_index, target in enumerate(ordered):
        if target["event_id"] not in forecasts:
            continue
        history_indices = available_history_indices(ordered, target_index)
        history = [ordered[index] for index in history_indices]
        forecast = forecasts[target["event_id"]]
        decision = target_decision(target, history, forecast)
        rows.append(
            {
                "event_id": target["event_id"],
                "name": target["name"],
                "time": target["time"],
                "observed": float(target["evaluation_events"]),
                "lower": float(forecast["lower"]),
                "upper": float(forecast["upper"]),
                "covered": bool(forecast["covered"]),
                "below": bool(forecast["below"]),
                "above": bool(forecast["above"]),
                "multiplicative_width": float(forecast["multiplicative_width"]),
                "history_count": len(history),
                "history_event_ids": [item["event_id"] for item in history],
                "latest_history_time": history[-1]["time"],
                **decision,
            }
        )
    return rows


def summarize_policy(rows: list[dict], policy: str) -> dict:
    retained = [row for row in rows if row["policy_issue"][policy]]
    abstained = [row for row in rows if not row["policy_issue"][policy]]
    widths = sorted(row["multiplicative_width"] for row in retained)
    median_width = statistics.median(widths) if widths else None
    return {
        "policy": policy,
        "eligible": len(rows),
        "issued": len(retained),
        "abstained": len(abstained),
        "retention": len(retained) / len(rows) if rows else None,
        "covered": sum(row["covered"] for row in retained),
        "coverage": (
            sum(row["covered"] for row in retained) / len(retained)
            if retained
            else None
        ),
        "median_multiplicative_width": median_width,
        "retained_miss_event_ids": [
            row["event_id"] for row in retained if not row["covered"]
        ],
        "abstained_covered": sum(row["covered"] for row in abstained),
        "abstained_missed": sum(not row["covered"] for row in abstained),
    }


def summarize_policies(rows: list[dict]) -> dict:
    names = (
        "issue_all",
        "feature_support",
        "model_consensus",
        "sharpness_cap",
        "combined",
    )
    return {name: summarize_policy(rows, name) for name in names}


def width_sweep(rows: list[dict]) -> list[dict]:
    result = []
    for limit in WIDTH_SWEEP:
        retained = [row for row in rows if row["multiplicative_width"] <= limit]
        result.append(
            {
                "max_width": limit,
                "issued": len(retained),
                "retention": len(retained) / len(rows),
                "covered": sum(row["covered"] for row in retained),
                "coverage": (
                    sum(row["covered"] for row in retained) / len(retained)
                    if retained
                    else None
                ),
            }
        )
    return result


def run_abstention_audit(
    evidence_path: Path = Path("artifacts/external_aftershock_validation.json"),
) -> dict:
    source = json.loads(evidence_path.read_text(encoding="utf-8"))
    rows = audited_forecasts(source["folds"])
    later = [row for row in rows if row["time"] >= "2020-01-01"]
    return {
        "experiment": "causal abstention audit for external aftershock intervals",
        "claim_boundary": (
            "post-hoc negative-result study; gates use target-time inputs and "
            "fully matured earlier outcomes, but were motivated by reports 24-25"
        ),
        "source_experiment": source["experiment"],
        "policy_constants": {
            "support_limit": SUPPORT_LIMIT,
            "consensus_coverage": CONSENSUS_COVERAGE,
            "sharpness_max_width": SHARPNESS_MAX_WIDTH,
        },
        "overall": summarize_policies(rows),
        "from_2020": summarize_policies(later),
        "width_sweep": width_sweep(rows),
        "rows": rows,
    }


def plot_abstention_audit(report: dict, output_path: Path) -> None:
    rows = report["rows"]
    summaries = report["overall"]
    labels = {
        "issue_all": "issue all",
        "feature_support": "feature support",
        "model_consensus": "model consensus",
        "sharpness_cap": "width <= 5x",
        "combined": "combined",
    }
    colors = {
        "issue_all": "#636e72",
        "feature_support": "#0984e3",
        "model_consensus": "#6c5ce7",
        "sharpness_cap": "#e17055",
        "combined": "#d63031",
    }
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    policy_axis, width_axis, time_axis, signal_axis = axes.ravel()

    for policy, summary in summaries.items():
        policy_axis.scatter(
            summary["retention"],
            summary["coverage"],
            s=70,
            color=colors[policy],
            label=labels[policy],
        )
    policy_axis.axhline(0.8, color="#2d3436", linestyle="--", label="80% target")
    policy_axis.set(
        title="Selective coverage does not improve reliably",
        xlabel="fraction of eligible forecasts issued",
        ylabel="coverage among issued forecasts",
        xlim=(0.35, 1.03),
        ylim=(0.55, 0.86),
    )
    policy_axis.legend(frameon=False, fontsize=8)
    policy_axis.grid(alpha=0.2)

    sweep = report["width_sweep"]
    width_axis.plot(
        [item["retention"] for item in sweep],
        [item["coverage"] for item in sweep],
        marker="o",
        color="#e17055",
    )
    for item in sweep:
        if item["max_width"] in (3.0, 5.0, 10.0, 15.0):
            width_axis.annotate(
                f"{item['max_width']:g}x",
                (item["retention"], item["coverage"]),
                xytext=(4, 4),
                textcoords="offset points",
                fontsize=8,
            )
    width_axis.axhline(0.8, color="#2d3436", linestyle="--")
    width_axis.set(
        title="Narrow-interval selection is anti-informative",
        xlabel="retention under maximum-width rule",
        ylabel="coverage among issued forecasts",
        ylim=(0.25, 0.85),
    )
    width_axis.grid(alpha=0.2)

    positions = list(range(len(rows)))
    time_axis.plot(
        positions,
        [row["support_score"] for row in rows],
        marker="o",
        color="#0984e3",
        label="feature novelty",
    )
    misses = [index for index, row in enumerate(rows) if not row["covered"]]
    time_axis.scatter(
        misses,
        [rows[index]["support_score"] for index in misses],
        marker="x",
        s=70,
        color="#d63031",
        label="interval miss",
        zorder=3,
    )
    time_axis.axhline(SUPPORT_LIMIT, color="#2d3436", linestyle="--")
    time_axis.set_xticks(
        positions,
        [row["time"][:4] for row in rows],
        rotation=70,
        fontsize=7,
    )
    time_axis.set(title="Most misses look feature-typical", ylabel="maximum robust score")
    time_axis.legend(frameon=False)
    time_axis.grid(alpha=0.2)

    ratios = [
        row["forecast_disagreement"] / row["consensus_threshold"]
        for row in rows
    ]
    for index, row in enumerate(rows):
        signal_axis.scatter(
            row["support_score"],
            ratios[index],
            marker="x" if not row["covered"] else "o",
            color="#d63031" if not row["covered"] else "#00b894",
            alpha=0.9,
        )
    signal_axis.axvline(SUPPORT_LIMIT, color="#2d3436", linestyle="--")
    signal_axis.axhline(1.0, color="#2d3436", linestyle="--")
    signal_axis.set(
        title="Failure occupies the apparently safe quadrant",
        xlabel="feature novelty score",
        ylabel="disagreement / causal threshold",
    )
    signal_axis.grid(alpha=0.2)

    fig.suptitle("Causal abstention audit - no reliable target-time failure signal")
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_abstention_audit()
    (output_dir / "abstention_audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_abstention_audit(report, output_dir / "abstention_audit.png")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
