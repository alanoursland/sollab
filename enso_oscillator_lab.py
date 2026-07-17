"""Chronological scalar ENSO forecasting: oscillator or threshold switching?"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Iterable

import matplotlib
import numpy as np
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.opt.least_squares import RidgeSolver
from kinopulse.validation import ExpandingWindowGroupSplit, cross_validate

from fetch_meiv2 import parse_meiv2


DTYPE = torch.float64
DATA_PATH = Path("data/enso/meiv2.data")
MANIFEST_PATH = Path("data/enso/manifest.json")
ARTIFACT_PATH = Path("artifacts/enso_oscillator_analysis.json")
FIGURE_PATH = Path("artifacts/enso_oscillator_lab.png")
TRAIN_END = 2009
VALIDATION_YEARS = tuple(range(2010, 2018))
TEST_YEARS = tuple(range(2018, 2026))
REGIME_THRESHOLD = 0.5


@dataclass(frozen=True)
class ScalarForecastModel:
    kind: str
    alpha: float = 0.0
    threshold: float | None = None
    feature_mean: torch.Tensor | None = None
    feature_scale: torch.Tensor | None = None
    coefficients: dict[str, torch.Tensor] | None = None
    climatology: dict[int, float] | None = None


def load_observations(path: Path = DATA_PATH) -> dict[tuple[int, int], float]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run fetch_meiv2.py first")
    records = parse_meiv2(path.read_text(encoding="utf-8"))
    return {
        (row["year"], row["month"]): float(row["value"])
        for row in records
        if row["value"] is not None
    }


def previous_month(year: int, month: int, steps: int = 1) -> tuple[int, int]:
    absolute = year * 12 + month - 1 - steps
    return absolute // 12, absolute % 12 + 1


def base_features(x_t: float, x_tm1: float, target_month: int) -> list[float]:
    phase = 2.0 * math.pi * (target_month - 1) / 12.0
    return [1.0, x_t, x_tm1, math.sin(phase), math.cos(phase)]


def model_features(kind: str, x_t: float, x_tm1: float, target_month: int) -> list[float]:
    features = base_features(x_t, x_tm1, target_month)
    if kind == "weakly_nonlinear":
        features.extend((x_t**2, x_t**3))
    return features


def regime_key(value: float, threshold: float) -> str:
    if value < -threshold:
        return "cold"
    if value > threshold:
        return "warm"
    return "neutral"


def _training_rows(
    observations: dict[tuple[int, int], float],
    years: Iterable[int],
    kind: str,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    selected_years = set(years)
    rows: list[list[float]] = []
    targets: list[float] = []
    states: list[float] = []
    for (year, month), target in sorted(observations.items()):
        if year not in selected_years:
            continue
        p1 = previous_month(year, month)
        p2 = previous_month(year, month, 2)
        if p1 not in observations or p2 not in observations:
            continue
        x_t, x_tm1 = observations[p1], observations[p2]
        rows.append(model_features(kind, x_t, x_tm1, month))
        targets.append(target)
        states.append(x_t)
    if not rows:
        raise ValueError("no complete training rows")
    return (
        torch.tensor(rows, dtype=DTYPE),
        torch.tensor(targets, dtype=DTYPE),
        torch.tensor(states, dtype=DTYPE),
    )


def fit_model(
    observations: dict[tuple[int, int], float],
    years: Iterable[int],
    parameters: dict,
) -> ScalarForecastModel:
    years = tuple(int(year) for year in years)
    kind = str(parameters["kind"])
    if kind == "persistence":
        return ScalarForecastModel(kind=kind)
    if kind == "monthly_climatology":
        climatology = {
            month: float(np.mean([value for (year, m), value in observations.items() if year in years and m == month]))
            for month in range(1, 13)
        }
        return ScalarForecastModel(kind=kind, climatology=climatology)

    alpha = float(parameters["alpha"])
    threshold = float(parameters["threshold"]) if kind == "threshold_switching" else None
    X, y, current_states = _training_rows(observations, years, kind)
    mean = X[:, 1:].mean(dim=0)
    scale = X[:, 1:].std(dim=0, unbiased=False).clamp_min(1e-12)
    standardized = torch.cat((X[:, :1], (X[:, 1:] - mean) / scale), dim=1)

    coefficients: dict[str, torch.Tensor] = {}
    if kind == "threshold_switching":
        assert threshold is not None
        keys = [regime_key(float(value), threshold) for value in current_states]
        for key in ("cold", "neutral", "warm"):
            mask = torch.tensor([item == key for item in keys], dtype=torch.bool)
            if int(mask.sum()) < standardized.shape[1] + 2:
                raise ValueError(f"only {int(mask.sum())} training rows in {key} regime")
            coefficients[key] = RidgeSolver(lambda_=alpha).solve(standardized[mask], y[mask]).x
    else:
        coefficients["all"] = RidgeSolver(lambda_=alpha).solve(standardized, y).x
    return ScalarForecastModel(kind, alpha, threshold, mean, scale, coefficients)


def predict_one(model: ScalarForecastModel, x_t: float, x_tm1: float, target_month: int) -> float:
    if model.kind == "persistence":
        return x_t
    if model.kind == "monthly_climatology":
        assert model.climatology is not None
        return model.climatology[target_month]
    assert model.feature_mean is not None and model.feature_scale is not None
    assert model.coefficients is not None
    raw = torch.tensor(model_features(model.kind, x_t, x_tm1, target_month), dtype=DTYPE)
    features = torch.cat((raw[:1], (raw[1:] - model.feature_mean) / model.feature_scale))
    key = "all"
    if model.kind == "threshold_switching":
        assert model.threshold is not None
        key = regime_key(x_t, model.threshold)
    prediction = float(features @ model.coefficients[key])
    if not math.isfinite(prediction) or abs(prediction) > 20.0:
        raise RuntimeError(f"unstable recursive prediction: {prediction}")
    return prediction


def forecast_year(
    model: ScalarForecastModel,
    observations: dict[tuple[int, int], float],
    year: int,
) -> np.ndarray:
    x_tm1 = observations[(year - 1, 11)]
    x_t = observations[(year - 1, 12)]
    forecast = []
    for month in range(1, 13):
        prediction = predict_one(model, x_t, x_tm1, month)
        forecast.append(prediction)
        x_tm1, x_t = x_t, prediction
    return np.asarray(forecast, dtype=float)


def actual_year(observations: dict[tuple[int, int], float], year: int) -> np.ndarray:
    return np.asarray([observations[(year, month)] for month in range(1, 13)], dtype=float)


def rmse(predicted: np.ndarray, observed: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(predicted - observed))))


def regime_labels(values: np.ndarray, threshold: float = REGIME_THRESHOLD) -> np.ndarray:
    return np.where(values > threshold, 1, np.where(values < -threshold, -1, 0))


def evaluate_model(
    model: ScalarForecastModel,
    observations: dict[tuple[int, int], float],
    years: Iterable[int],
) -> dict:
    years = tuple(years)
    forecasts = np.stack([forecast_year(model, observations, year) for year in years])
    actual = np.stack([actual_year(observations, year) for year in years])
    errors = forecasts - actual
    return {
        "rmse": rmse(forecasts, actual),
        "mae": float(np.mean(np.abs(errors))),
        "regime_accuracy": float(np.mean(regime_labels(forecasts) == regime_labels(actual))),
        "annual_rmse": {str(year): rmse(forecasts[index], actual[index]) for index, year in enumerate(years)},
        "lead_month_rmse": [rmse(forecasts[:, month], actual[:, month]) for month in range(12)],
        "forecast": forecasts.tolist(),
        "actual": actual.tolist(),
    }


def paired_year_comparison(
    challenger: dict,
    reference: dict,
    *,
    seed: int = 20260717,
    bootstrap_samples: int = 20_000,
) -> dict:
    """Compare paths while treating whole forecast years as the sampling units."""
    challenger_forecast = np.asarray(challenger["forecast"], dtype=float)
    reference_forecast = np.asarray(reference["forecast"], dtype=float)
    observed = np.asarray(challenger["actual"], dtype=float)
    challenger_mse = np.mean(np.square(challenger_forecast - observed), axis=1)
    reference_mse = np.mean(np.square(reference_forecast - observed), axis=1)
    improvement = reference_mse - challenger_mse

    # Exact paired sign randomization over the eight independent target years.
    observed_difference = float(np.mean(improvement))
    randomized = []
    for mask in range(1 << len(improvement)):
        signs = np.asarray([1.0 if mask & (1 << index) else -1.0 for index in range(len(improvement))])
        randomized.append(float(np.mean(signs * improvement)))
    one_sided_p = float(np.mean(np.asarray(randomized) >= observed_difference - 1e-15))

    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(improvement), size=(bootstrap_samples, len(improvement)))
    challenger_draw_rmse = np.sqrt(np.mean(challenger_mse[draws], axis=1))
    reference_draw_rmse = np.sqrt(np.mean(reference_mse[draws], axis=1))
    relative_skill = 1.0 - challenger_draw_rmse / reference_draw_rmse
    return {
        "independent_units": "target years",
        "years": int(len(improvement)),
        "challenger_wins": int(np.sum(improvement > 0)),
        "rmse_difference": float(reference["rmse"] - challenger["rmse"]),
        "relative_skill": float(1.0 - challenger["rmse"] / reference["rmse"]),
        "relative_skill_year_bootstrap_95_interval": [
            float(np.quantile(relative_skill, 0.025)),
            float(np.quantile(relative_skill, 0.975)),
        ],
        "exact_paired_sign_randomization_one_sided_p": one_sided_p,
        "warning": "Only eight whole-year units; the interval and randomization test are low-power diagnostics, not a forecast-skill certificate.",
    }


def candidate_grid() -> list[dict]:
    candidates: list[dict] = [
        {"kind": "persistence"},
        {"kind": "monthly_climatology"},
    ]
    for kind in ("delayed_oscillator", "weakly_nonlinear"):
        candidates.extend({"kind": kind, "alpha": alpha} for alpha in (0.001, 0.01, 0.1, 1.0))
    candidates.extend(
        {"kind": "threshold_switching", "alpha": alpha, "threshold": threshold}
        for threshold in (0.3, 0.5, 0.7)
        for alpha in (0.01, 0.1, 1.0)
    )
    return candidates


def best_complete_by_family(validation_result) -> dict[str, dict]:
    winners: dict[str, tuple[float, dict]] = {}
    for candidate in validation_result.candidates:
        if candidate.aggregate_score is None or any(fold.score is None for fold in candidate.folds):
            continue
        kind = str(candidate.parameters["kind"])
        item = (float(candidate.aggregate_score), dict(candidate.parameters))
        if kind not in winners or item[0] < winners[kind][0]:
            winners[kind] = item
    return {kind: item[1] for kind, item in winners.items()}


def plot_results(results: dict, path: Path = FIGURE_PATH) -> None:
    selected_kind = results["selection"]["selected_parameters"]["kind"]
    selected = results["test"][selected_kind]
    persistence = results["test"]["persistence"]
    years = results["protocol"]["test_years"]
    actual = np.asarray(selected["actual"]).reshape(-1)
    forecast = np.asarray(selected["forecast"]).reshape(-1)
    dates = np.arange(len(actual)) / 12.0 + years[0]

    fig, axes = plt.subplots(3, 1, figsize=(11, 10), constrained_layout=True)
    axes[0].plot(dates, actual, color="black", lw=1.5, label="observed MEI.v2")
    axes[0].plot(dates, forecast, color="#0072B2", lw=1.25, label=f"preselected {selected_kind}")
    axes[0].axhspan(-0.5, 0.5, color="0.9", zorder=-2, label="neutral ±0.5")
    for year in years:
        axes[0].axvline(year, color="white", lw=0.8, zorder=-1)
    axes[0].set_ylabel("MEI.v2")
    axes[0].set_title("Untouched 2018–2025 annual recursive forecasts")
    axes[0].legend(ncol=3, fontsize=8)

    order = list(results["selection"]["family_parameters"])
    validation_scores = [results["selection"]["family_validation_rmse"][kind] for kind in order]
    test_scores = [results["test"][kind]["rmse"] for kind in order]
    positions = np.arange(len(order))
    width = 0.36
    axes[1].bar(positions - width / 2, validation_scores, width, color="#56B4E9", label="2010–2017 validation")
    axes[1].bar(positions + width / 2, test_scores, width, color="#D55E00", label="2018–2025 test")
    axes[1].set_xticks(positions, [name.replace("_", "\n") for name in order])
    axes[1].set_ylabel("annual-path RMSE")
    axes[1].set_title("Every family was tuned before the holdout was opened")
    axes[1].legend()

    leads = np.arange(1, 13)
    axes[2].plot(leads, persistence["lead_month_rmse"], marker="o", color="0.45", label="persistence")
    axes[2].plot(leads, selected["lead_month_rmse"], marker="o", color="#0072B2", label=selected_kind)
    axes[2].set_xticks(leads)
    axes[2].set_xlabel("forecast lead (months)")
    axes[2].set_ylabel("RMSE")
    axes[2].set_title("Skill decay across the twelve-month recursive path")
    axes[2].legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run() -> dict:
    observations = load_observations()
    groups = tuple(range(1979, VALIDATION_YEARS[-1] + 1))
    splitter = ExpandingWindowGroupSplit(
        groups,
        groups,
        min_train_groups=TRAIN_END - 1979 + 1,
        validation_groups=1,
    )

    def fit(train_years: tuple[int, ...], parameters: dict) -> ScalarForecastModel:
        return fit_model(observations, train_years, parameters)

    def score(model: ScalarForecastModel, year: int) -> float:
        return rmse(forecast_year(model, observations, year), actual_year(observations, year))

    validation = cross_validate(
        candidates=candidate_grid(),
        splitter=splitter,
        fit=fit,
        score=score,
        objective="minimize",
        aggregate="mean",
        failure_policy="visible",
        seed=20260717,
    )
    family_parameters = best_complete_by_family(validation)
    complete_candidates = [
        candidate
        for candidate in validation.candidates
        if candidate.aggregate_score is not None and all(fold.score is not None for fold in candidate.folds)
    ]
    if not complete_candidates:
        raise RuntimeError("every validation candidate failed at least one fold")
    selected_candidate = min(
        complete_candidates,
        key=lambda candidate: (float(candidate.aggregate_score), json.dumps(candidate.parameters, sort_keys=True)),
    )
    selected_parameters = dict(selected_candidate.parameters)
    family_validation_rmse = {
        kind: min(
            float(candidate.aggregate_score)
            for candidate in complete_candidates
            if candidate.parameters["kind"] == kind
        )
        for kind in family_parameters
    }

    refit_years = tuple(range(1979, VALIDATION_YEARS[-1] + 1))
    test = {
        kind: evaluate_model(fit_model(observations, refit_years, parameters), observations, TEST_YEARS)
        for kind, parameters in family_parameters.items()
    }
    persistence_rmse = test["persistence"]["rmse"]
    for metrics in test.values():
        metrics["skill_vs_persistence"] = 1.0 - metrics["rmse"] / persistence_rmse

    selected_kind = str(selected_parameters["kind"])
    comparisons = {
        "selected_vs_persistence": paired_year_comparison(test[selected_kind], test["persistence"]),
    }
    if selected_kind != "delayed_oscillator":
        comparisons["selected_vs_delayed_oscillator"] = paired_year_comparison(
            test[selected_kind], test["delayed_oscillator"], seed=20260718
        )

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    results = {
        "experiment": "scalar ENSO oscillator versus threshold switching",
        "kinopulse_version": version("kinopulse"),
        "source": manifest,
        "data_caveat": "MEI.v2 is an overlapping bimonthly index stored in monthly slots; adjacent-value persistence is partly constructed.",
        "protocol": {
            "training_years": [1979, TRAIN_END],
            "validation_years": list(VALIDATION_YEARS),
            "test_years": list(TEST_YEARS),
            "forecast_contract": "For each target year, observe through December of the prior year and recursively forecast January–December.",
            "test_opened_after_selection": True,
            "regime_threshold": REGIME_THRESHOLD,
        },
        "selection": {
            "selected_parameters": selected_parameters,
            "kinopulse_selected_parameters": validation.selected_parameters,
            "family_parameters": family_parameters,
            "family_validation_rmse": family_validation_rmse,
            "cross_validation": validation.to_dict(),
        },
        "test": test,
        "paired_year_inference": comparisons,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    plot_results(results)
    return results


if __name__ == "__main__":
    outcome = run()
    selected = outcome["selection"]["selected_parameters"]["kind"]
    metrics = outcome["test"][selected]
    print(f"Selected on 2010–2017: {outcome['selection']['selected_parameters']}")
    print(f"Untouched 2018–2025 RMSE: {metrics['rmse']:.4f}")
    print(f"Skill versus persistence: {metrics['skill_vs_persistence']:.1%}")
    print(f"Regime accuracy (±{REGIME_THRESHOLD}): {metrics['regime_accuracy']:.1%}")
    print(f"Wrote {ARTIFACT_PATH}")
    print(f"Wrote {FIGURE_PATH}")
