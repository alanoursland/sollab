"""Explore whether equatorial subsurface heat adds ENSO forecast memory."""

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

from enso_oscillator_lab import (
    DTYPE,
    TEST_YEARS,
    VALIDATION_YEARS,
    actual_year,
    evaluate_model,
    fit_model,
    load_observations,
    paired_year_comparison,
    previous_month,
    rmse,
)
from fetch_meiv2 import parse_psl_monthly


HEAT_PATH = Path("data/enso/heatcentra.data")
HEAT_MANIFEST_PATH = Path("data/enso/heatcentra_manifest.json")
ARTIFACT_PATH = Path("artifacts/enso_recharge_analysis.json")
FIGURE_PATH = Path("artifacts/enso_recharge_lab.png")
FRESH_YEAR = 2026
FRESH_MONTHS = 6

FROZEN_SCALAR_PARAMETERS = {
    "delayed_oscillator": {"kind": "delayed_oscillator", "alpha": 0.001},
    "threshold_switching": {"kind": "threshold_switching", "alpha": 0.01, "threshold": 0.3},
}


@dataclass(frozen=True)
class CoupledForecastModel:
    kind: str
    alpha: float
    feature_mean: torch.Tensor
    feature_scale: torch.Tensor
    coefficients: torch.Tensor


def load_heat_content(path: Path = HEAT_PATH) -> dict[tuple[int, int], float]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run fetch_enso_heat_content.py first")
    return {
        (row["year"], row["month"]): float(row["value"])
        for row in parse_psl_monthly(path.read_text(encoding="utf-8"))
        if row["value"] is not None
    }


def coupled_features(
    kind: str,
    state_t: tuple[float, float],
    state_tm1: tuple[float, float],
    target_month: int,
) -> list[float]:
    phase = 2.0 * math.pi * (target_month - 1) / 12.0
    features = [1.0, state_t[0], state_t[1]]
    if kind == "delayed_recharge":
        features.extend(state_tm1)
    features.extend((math.sin(phase), math.cos(phase)))
    return features


def _coupled_training_rows(
    mei: dict[tuple[int, int], float],
    heat: dict[tuple[int, int], float],
    years: Iterable[int],
    kind: str,
) -> tuple[torch.Tensor, torch.Tensor]:
    selected_years = set(years)
    rows: list[list[float]] = []
    targets: list[list[float]] = []
    for year, month in sorted(set(mei).intersection(heat)):
        key = (year, month)
        if year not in selected_years:
            continue
        p1, p2 = previous_month(year, month), previous_month(year, month, 2)
        if p1 not in mei or p1 not in heat or p2 not in mei or p2 not in heat:
            continue
        state_t = (mei[p1], heat[p1])
        state_tm1 = (mei[p2], heat[p2])
        rows.append(coupled_features(kind, state_t, state_tm1, month))
        targets.append([mei[key], heat[key]])
    if not rows:
        raise ValueError("no complete coupled training rows")
    return torch.tensor(rows, dtype=DTYPE), torch.tensor(targets, dtype=DTYPE)


def fit_coupled_model(
    mei: dict[tuple[int, int], float],
    heat: dict[tuple[int, int], float],
    years: Iterable[int],
    parameters: dict,
) -> CoupledForecastModel:
    kind = str(parameters["kind"])
    alpha = float(parameters["alpha"])
    X, target = _coupled_training_rows(mei, heat, years, kind)
    mean = X[:, 1:].mean(dim=0)
    scale = X[:, 1:].std(dim=0, unbiased=False).clamp_min(1e-12)
    standardized = torch.cat((X[:, :1], (X[:, 1:] - mean) / scale), dim=1)
    # RidgeSolver currently summarizes residuals with a vector-only dot product,
    # so solve each coupled state equation explicitly. See the recorded gap.
    coefficients = torch.stack(
        [RidgeSolver(lambda_=alpha).solve(standardized, target[:, column]).x for column in range(target.shape[1])],
        dim=1,
    )
    return CoupledForecastModel(kind, alpha, mean, scale, coefficients)


def predict_coupled_one(
    model: CoupledForecastModel,
    state_t: tuple[float, float],
    state_tm1: tuple[float, float],
    target_month: int,
) -> tuple[float, float]:
    raw = torch.tensor(coupled_features(model.kind, state_t, state_tm1, target_month), dtype=DTYPE)
    features = torch.cat((raw[:1], (raw[1:] - model.feature_mean) / model.feature_scale))
    prediction = features @ model.coefficients
    values = (float(prediction[0]), float(prediction[1]))
    if not all(math.isfinite(value) for value in values) or abs(values[0]) > 20 or abs(values[1]) > 20:
        raise RuntimeError(f"unstable coupled prediction: {values}")
    return values


def forecast_coupled(
    model: CoupledForecastModel,
    mei: dict[tuple[int, int], float],
    heat: dict[tuple[int, int], float],
    year: int,
    months: int = 12,
) -> np.ndarray:
    state_tm1 = (mei[(year - 1, 11)], heat[(year - 1, 11)])
    state_t = (mei[(year - 1, 12)], heat[(year - 1, 12)])
    forecast = []
    for month in range(1, months + 1):
        prediction = predict_coupled_one(model, state_t, state_tm1, month)
        forecast.append(prediction)
        state_tm1, state_t = state_t, prediction
    return np.asarray(forecast, dtype=float)


def evaluate_coupled(
    model: CoupledForecastModel,
    mei: dict[tuple[int, int], float],
    heat: dict[tuple[int, int], float],
    years: Iterable[int],
) -> dict:
    years = tuple(years)
    forecasts = np.stack([forecast_coupled(model, mei, heat, year) for year in years])
    actual_mei = np.stack([actual_year(mei, year) for year in years])
    actual_heat = np.stack([actual_year(heat, year) for year in years])
    mei_forecast = forecasts[:, :, 0]
    heat_forecast = forecasts[:, :, 1]
    return {
        "rmse": rmse(mei_forecast, actual_mei),
        "heat_content_rmse": rmse(heat_forecast, actual_heat),
        "annual_rmse": {str(year): rmse(mei_forecast[index], actual_mei[index]) for index, year in enumerate(years)},
        "lead_month_rmse": [rmse(mei_forecast[:, month], actual_mei[:, month]) for month in range(12)],
        "forecast": mei_forecast.tolist(),
        "heat_content_forecast": heat_forecast.tolist(),
        "actual": actual_mei.tolist(),
        "actual_heat_content": actual_heat.tolist(),
    }


def state_matrix(model: CoupledForecastModel) -> np.ndarray:
    """Return the unforced physical transition, including delayed state."""
    current = model.coefficients[1:3, :].T / model.feature_scale[:2]
    if model.kind == "recharge":
        return current.detach().cpu().numpy()
    delayed = model.coefficients[3:5, :].T / model.feature_scale[2:4]
    identity = torch.eye(2, dtype=DTYPE)
    zeros = torch.zeros((2, 2), dtype=DTYPE)
    companion = torch.cat((torch.cat((current, delayed), dim=1), torch.cat((identity, zeros), dim=1)), dim=0)
    return companion.detach().cpu().numpy()


def candidate_grid() -> list[dict]:
    return [
        {"kind": kind, "alpha": alpha}
        for kind in ("recharge", "delayed_recharge")
        for alpha in (0.001, 0.01, 0.1, 1.0, 10.0)
    ]


def _fresh_scalar_forecast(model, mei: dict[tuple[int, int], float]) -> np.ndarray:
    from enso_oscillator_lab import forecast_year

    return forecast_year(model, mei, FRESH_YEAR)[:FRESH_MONTHS]


def plot_results(results: dict, path: Path = FIGURE_PATH) -> None:
    families = list(results["reused_2018_2025"])
    test_rmse = [results["reused_2018_2025"][kind]["rmse"] for kind in families]
    actual = np.asarray(results["fresh_2026"]["actual_mei"])
    months = np.arange(1, FRESH_MONTHS + 1)

    fig, axes = plt.subplots(3, 1, figsize=(10.5, 10), constrained_layout=True)
    years = np.asarray(results["context_series"]["decimal_year"])
    axes[0].plot(years, results["context_series"]["mei"], color="#D55E00", label="MEI.v2")
    axes[0].plot(years, results["context_series"]["heat_content"], color="#0072B2", label="upper-300 m heat anomaly")
    axes[0].axhline(0, color="0.65", lw=0.8)
    axes[0].set_xlim(2008, 2026.55)
    axes[0].set_ylabel("standardized index / °C anomaly")
    axes[0].set_title("Surface expression and subsurface recharge do not move identically")
    axes[0].legend()

    colors = ["0.55", "0.7", "#56B4E9", "#0072B2"]
    axes[1].bar(np.arange(len(families)), test_rmse, color=colors)
    axes[1].set_xticks(np.arange(len(families)), [name.replace("_", "\n") for name in families])
    axes[1].set_ylabel("MEI.v2 RMSE")
    axes[1].set_title("Reused 2018–2025 evidence (exploratory, not a fresh holdout)")

    axes[2].plot(months, actual, color="black", marker="o", lw=2, label="observed MEI.v2")
    for kind, color in (("delayed_oscillator", "0.55"), ("threshold_switching", "0.7"), (results["selection"]["selected_physical_parameters"]["kind"], "#0072B2")):
        axes[2].plot(months, results["fresh_2026"][kind]["mei_forecast"], marker="o", color=color, label=kind)
    axes[2].set_xticks(months, ["Jan", "Feb", "Mar", "Apr", "May", "Jun"])
    axes[2].set_ylabel("MEI.v2")
    axes[2].set_title("Newly scored January–June 2026 path")
    axes[2].legend(fontsize=8, ncol=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run() -> dict:
    mei = load_observations()
    heat = load_heat_content()
    groups = tuple(range(1979, VALIDATION_YEARS[-1] + 1))
    splitter = ExpandingWindowGroupSplit(groups, groups, min_train_groups=31, validation_groups=1)

    def fit(train_years: tuple[int, ...], parameters: dict) -> CoupledForecastModel:
        return fit_coupled_model(mei, heat, train_years, parameters)

    def score(model: CoupledForecastModel, year: int) -> float:
        return rmse(forecast_coupled(model, mei, heat, year)[:, 0], actual_year(mei, year))

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
    selected_parameters = validation.selected_parameters
    if selected_parameters is None:
        raise RuntimeError("all physical-state candidates failed")

    refit_years = tuple(range(1979, VALIDATION_YEARS[-1] + 1))
    physical_models = {
        kind: fit_coupled_model(
            mei,
            heat,
            refit_years,
            min(
                (
                    candidate.parameters
                    for candidate in validation.candidates
                    if candidate.parameters["kind"] == kind and candidate.aggregate_score is not None
                ),
                key=lambda parameters: next(
                    candidate.aggregate_score
                    for candidate in validation.candidates
                    if candidate.parameters == parameters
                ),
            ),
        )
        for kind in ("recharge", "delayed_recharge")
    }
    scalar_models = {
        name: fit_model(mei, refit_years, parameters)
        for name, parameters in FROZEN_SCALAR_PARAMETERS.items()
    }
    reused = {
        name: evaluate_model(model, mei, TEST_YEARS) for name, model in scalar_models.items()
    }
    reused.update(
        {name: evaluate_coupled(model, mei, heat, TEST_YEARS) for name, model in physical_models.items()}
    )

    selected_physical_kind = str(selected_parameters["kind"])
    comparisons = {
        f"{selected_physical_kind}_vs_{name}": paired_year_comparison(reused[selected_physical_kind], reused[name], seed=20260720 + index)
        for index, name in enumerate(FROZEN_SCALAR_PARAMETERS)
    }

    fresh_actual = np.asarray([mei[(FRESH_YEAR, month)] for month in range(1, FRESH_MONTHS + 1)], dtype=float)
    fresh: dict = {"actual_mei": fresh_actual.tolist()}
    for name, model in scalar_models.items():
        forecast = _fresh_scalar_forecast(model, mei)
        fresh[name] = {"mei_forecast": forecast.tolist(), "rmse": rmse(forecast, fresh_actual)}
    for name, model in physical_models.items():
        forecast = forecast_coupled(model, mei, heat, FRESH_YEAR, FRESH_MONTHS)
        fresh[name] = {
            "mei_forecast": forecast[:, 0].tolist(),
            "heat_content_forecast": forecast[:, 1].tolist(),
            "rmse": rmse(forecast[:, 0], fresh_actual),
            "heat_content_rmse": rmse(
                forecast[:, 1], np.asarray([heat[(FRESH_YEAR, month)] for month in range(1, FRESH_MONTHS + 1)])
            ),
        }

    common_keys = sorted(set(mei).intersection(heat))
    context = {
        "decimal_year": [year + (month - 1) / 12 for year, month in common_keys],
        "mei": [mei[key] for key in common_keys],
        "heat_content": [heat[key] for key in common_keys],
    }
    model_diagnostics = {}
    for name, model in physical_models.items():
        matrix = state_matrix(model)
        eigenvalues = np.linalg.eigvals(matrix)
        model_diagnostics[name] = {
            "unforced_transition_matrix": matrix.tolist(),
            "unforced_transition_eigenvalues": [
                {
                    "real": float(value.real),
                    "imag": float(value.imag),
                    "magnitude": float(abs(value)),
                    "oscillation_period_months": (
                        None if abs(value.imag) < 1e-12 else float(2.0 * math.pi / abs(np.angle(value)))
                    ),
                    "amplitude_e_folding_months": (
                        None if abs(abs(value) - 1.0) < 1e-12 else float(-1.0 / math.log(abs(value)))
                    ),
                }
                for value in eigenvalues
            ],
        }

    results = {
        "experiment": "ENSO coupled recharge-state follow-up",
        "kinopulse_version": version("kinopulse"),
        "source": {
            "mei": json.loads(Path("data/enso/manifest.json").read_text(encoding="utf-8")),
            "heat_content": json.loads(HEAT_MANIFEST_PATH.read_text(encoding="utf-8")),
        },
        "protocol": {
            "training_years": [1979, 2009],
            "validation_years": list(VALIDATION_YEARS),
            "reused_evidence_years": list(TEST_YEARS),
            "fresh_path": {"year": FRESH_YEAR, "months": FRESH_MONTHS},
            "warning": "2018-2025 outcomes were opened by report 47 before this physical-state follow-up; only Jan-Jun 2026 is newly scored.",
            "scalar_parameters_frozen_from_report_47": FROZEN_SCALAR_PARAMETERS,
        },
        "selection": {
            "selected_physical_parameters": selected_parameters,
            "cross_validation": validation.to_dict(),
        },
        "reused_2018_2025": reused,
        "paired_year_diagnostics": comparisons,
        "fresh_2026": fresh,
        "model_diagnostics": model_diagnostics,
        "context_series": context,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    plot_results(results)
    return results


if __name__ == "__main__":
    outcome = run()
    selected = outcome["selection"]["selected_physical_parameters"]["kind"]
    print(f"Selected physical model: {outcome['selection']['selected_physical_parameters']}")
    print(f"Reused 2018-2025 RMSE: {outcome['reused_2018_2025'][selected]['rmse']:.4f}")
    print(f"Fresh Jan-Jun 2026 RMSE: {outcome['fresh_2026'][selected]['rmse']:.4f}")
    print(f"Wrote {ARTIFACT_PATH}")
    print(f"Wrote {FIGURE_PATH}")
