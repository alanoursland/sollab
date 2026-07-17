"""Causal one-month audit of western-Pacific wind and ocean heat recharge."""

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

from enso_oscillator_lab import DTYPE, TEST_YEARS, VALIDATION_YEARS, load_observations, paired_year_comparison
from enso_recharge_lab import load_heat_content
from fetch_meiv2 import parse_psl_monthly


WIND_PATH = Path("data/enso/uwnd.850.140190.data")
WIND_MANIFEST_PATH = Path("data/enso/wind850_manifest.json")
ARTIFACT_PATH = Path("artifacts/enso_wind_heat_analysis.json")
FIGURE_PATH = Path("artifacts/enso_wind_heat_lab.png")


@dataclass(frozen=True)
class HeatChangeModel:
    kind: str
    alpha: float = 0.0
    feature_mean: torch.Tensor | None = None
    feature_scale: torch.Tensor | None = None
    coefficients: torch.Tensor | None = None


@dataclass(frozen=True)
class HeatRow:
    target_year: int
    target_month: int
    current_heat: float
    actual_next_heat: float
    features: tuple[float, ...]


def load_wind(path: Path = WIND_PATH) -> dict[tuple[int, int], float]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run fetch_enso_wind.py first")
    return {
        (row["year"], row["month"]): float(row["value"])
        for row in parse_psl_monthly(path.read_text(encoding="utf-8"))
        if row["value"] is not None
    }


def shift_month(key: tuple[int, int], steps: int) -> tuple[int, int]:
    absolute = key[0] * 12 + key[1] - 1 + steps
    return absolute // 12, absolute % 12 + 1


def heat_features(
    kind: str,
    target_month: int,
    heat_t: float,
    heat_tm1: float,
    mei_t: float,
    wind_t: float,
    wind_tm1: float,
    wind_tm2: float,
) -> tuple[float, ...]:
    phase = 2.0 * math.pi * (target_month - 1) / 12.0
    values = [1.0, heat_t, heat_t - heat_tm1, mei_t, math.sin(phase), math.cos(phase)]
    if kind in {"state_plus_wind", "state_plus_wind_memory"}:
        values.append(wind_t)
    if kind == "state_plus_wind_memory":
        values.extend((wind_tm1, wind_tm2))
    return tuple(values)


def build_rows(
    mei: dict[tuple[int, int], float],
    heat: dict[tuple[int, int], float],
    wind: dict[tuple[int, int], float],
    kind: str,
) -> list[HeatRow]:
    rows = []
    for current in sorted(set(mei).intersection(heat).intersection(wind)):
        target = shift_month(current, 1)
        previous = shift_month(current, -1)
        wind_previous = previous
        wind_previous2 = shift_month(current, -2)
        if target not in heat or previous not in heat or wind_previous not in wind or wind_previous2 not in wind:
            continue
        features = heat_features(
            kind,
            target[1],
            heat[current],
            heat[previous],
            mei[current],
            wind[current],
            wind[wind_previous],
            wind[wind_previous2],
        )
        rows.append(HeatRow(target[0], target[1], heat[current], heat[target], features))
    return rows


def fit_heat_model(rows: list[HeatRow], years: Iterable[int], parameters: dict) -> HeatChangeModel:
    kind = str(parameters["kind"])
    if kind == "persistence":
        return HeatChangeModel(kind)
    selected_years = set(years)
    selected = [row for row in rows if row.target_year in selected_years]
    if not selected:
        raise ValueError("no heat-change training rows")
    X = torch.tensor([row.features for row in selected], dtype=DTYPE)
    target = torch.tensor([row.actual_next_heat - row.current_heat for row in selected], dtype=DTYPE)
    mean = X[:, 1:].mean(dim=0)
    scale = X[:, 1:].std(dim=0, unbiased=False).clamp_min(1e-12)
    standardized = torch.cat((X[:, :1], (X[:, 1:] - mean) / scale), dim=1)
    alpha = float(parameters["alpha"])
    coefficients = RidgeSolver(lambda_=alpha).solve(standardized, target).x
    return HeatChangeModel(kind, alpha, mean, scale, coefficients)


def predict_change(model: HeatChangeModel, row: HeatRow) -> float:
    if model.kind == "persistence":
        return 0.0
    assert model.feature_mean is not None and model.feature_scale is not None and model.coefficients is not None
    raw = torch.tensor(row.features, dtype=DTYPE)
    standardized = torch.cat((raw[:1], (raw[1:] - model.feature_mean) / model.feature_scale))
    return float(standardized @ model.coefficients)


def evaluate(model: HeatChangeModel, rows: list[HeatRow], years: Iterable[int], extreme_threshold: float) -> dict:
    years = tuple(years)
    grouped = {year: sorted((row for row in rows if row.target_year == year), key=lambda row: row.target_month) for year in years}
    if any(len(grouped[year]) != 12 for year in years):
        raise ValueError("evaluation requires twelve target months per year")
    predicted_change = np.asarray([[predict_change(model, row) for row in grouped[year]] for year in years])
    current_heat = np.asarray([[row.current_heat for row in grouped[year]] for year in years])
    actual_heat = np.asarray([[row.actual_next_heat for row in grouped[year]] for year in years])
    predicted_heat = current_heat + predicted_change
    actual_change = actual_heat - current_heat
    predicted_extreme = predicted_change >= extreme_threshold
    actual_extreme = actual_change >= extreme_threshold
    true_positive = int(np.sum(predicted_extreme & actual_extreme))
    predicted_positive = int(np.sum(predicted_extreme))
    actual_positive = int(np.sum(actual_extreme))
    predicted_flat = predicted_change.reshape(-1)
    actual_flat = actual_change.reshape(-1)
    change_correlation = None
    if float(np.std(predicted_flat)) > 1e-12 and float(np.std(actual_flat)) > 1e-12:
        change_correlation = float(np.corrcoef(predicted_flat, actual_flat)[0, 1])
    return {
        "rmse": float(np.sqrt(np.mean((predicted_heat - actual_heat) ** 2))),
        "change_mae": float(np.mean(np.abs(predicted_change - actual_change))),
        "change_correlation": change_correlation,
        "direction_accuracy": (
            None if model.kind == "persistence" else float(np.mean(np.sign(predicted_change) == np.sign(actual_change)))
        ),
        "extreme_recharge_threshold": extreme_threshold,
        "extreme_recharge_recall": None if actual_positive == 0 else true_positive / actual_positive,
        "extreme_recharge_precision": None if predicted_positive == 0 else true_positive / predicted_positive,
        "extreme_recharge_actual": actual_positive,
        "extreme_recharge_predicted": predicted_positive,
        "annual_rmse": {
            str(year): float(np.sqrt(np.mean((predicted_heat[index] - actual_heat[index]) ** 2)))
            for index, year in enumerate(years)
        },
        "forecast": predicted_heat.tolist(),
        "actual": actual_heat.tolist(),
        "predicted_change": predicted_change.tolist(),
        "actual_change": actual_change.tolist(),
    }


def candidates() -> list[dict]:
    values: list[dict] = [{"kind": "persistence"}]
    for kind in ("state", "state_plus_wind", "state_plus_wind_memory"):
        values.extend({"kind": kind, "alpha": alpha} for alpha in (0.001, 0.01, 0.1, 1.0, 10.0))
    return values


def best_by_family(validation) -> dict[str, dict]:
    winners = {}
    for candidate in validation.candidates:
        if candidate.aggregate_score is None or any(fold.score is None for fold in candidate.folds):
            continue
        kind = str(candidate.parameters["kind"])
        if kind not in winners or candidate.aggregate_score < winners[kind][0]:
            winners[kind] = (float(candidate.aggregate_score), dict(candidate.parameters))
    return {kind: item[1] for kind, item in winners.items()}


def physical_coefficients(model: HeatChangeModel) -> dict[str, float]:
    if model.kind == "persistence":
        return {}
    assert model.coefficients is not None and model.feature_scale is not None
    names = ["heat", "recent_heat_change", "mei", "season_sin", "season_cos"]
    if model.kind in {"state_plus_wind", "state_plus_wind_memory"}:
        names.append("wind")
    if model.kind == "state_plus_wind_memory":
        names.extend(("wind_lag1", "wind_lag2"))
    return {
        name: float(model.coefficients[index + 1] / model.feature_scale[index])
        for index, name in enumerate(names)
    }


def plot_results(results: dict, path: Path = FIGURE_PATH) -> None:
    families = list(results["selection"]["family_parameters"])
    validation = [results["selection"]["family_validation_rmse"][kind] for kind in families]
    test = [results["test_2018_2025"][kind]["rmse"] for kind in families]
    positions = np.arange(len(families))
    selected = results["selection"]["selected_parameters"]["kind"]
    selected_test = results["test_2018_2025"][selected]
    actual_change = np.asarray(selected_test["actual_change"])
    predicted_change = np.asarray(selected_test["predicted_change"])

    fig, axes = plt.subplots(3, 1, figsize=(10.5, 10), constrained_layout=True)
    width = 0.36
    axes[0].bar(positions - width / 2, validation, width, color="#56B4E9", label="2010–2017 validation")
    axes[0].bar(positions + width / 2, test, width, color="#D55E00", label="2018–2025 reused test")
    axes[0].set_xticks(positions, [kind.replace("_", "\n") for kind in families])
    axes[0].set_ylabel("one-month heat RMSE (°C)")
    axes[0].set_title("Does observed low-level wind improve the next heat state?")
    axes[0].legend()

    axes[1].scatter(actual_change.reshape(-1), predicted_change.reshape(-1), c=np.tile(np.arange(12), 8), cmap="twilight", alpha=0.75)
    limits = [-0.9, 0.9]
    axes[1].plot(limits, limits, color="black", lw=1, ls="--")
    axes[1].axhline(0, color="0.7", lw=0.8)
    axes[1].axvline(0, color="0.7", lw=0.8)
    axes[1].set_xlim(limits)
    axes[1].set_ylim(limits)
    axes[1].set_xlabel("observed next-month heat change (°C)")
    axes[1].set_ylabel("predicted change (°C)")
    axes[1].set_title(f"Selected {selected}: change correlation {selected_test['change_correlation']:.3f}")

    months = np.arange(1, 25)
    actual_tail = np.asarray(selected_test["actual_change"])[-2:].reshape(-1)
    axes[2].plot(months, actual_tail, color="black", marker="o", label="observed")
    for kind, color in (("state", "0.55"), ("state_plus_wind", "#0072B2"), ("state_plus_wind_memory", "#009E73")):
        axes[2].plot(months, np.asarray(results["test_2018_2025"][kind]["predicted_change"])[-2:].reshape(-1), color=color, label=kind)
    axes[2].axhline(0, color="0.7", lw=0.8)
    axes[2].set_xticks([1, 4, 7, 10, 13, 16, 19, 22], ["Jan 2024", "Apr", "Jul", "Oct", "Jan 2025", "Apr", "Jul", "Oct"])
    axes[2].set_ylabel("next-month heat change (°C)")
    axes[2].set_title("Latest complete causal targets before the wind archive ends")
    axes[2].legend(fontsize=8, ncol=2)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run() -> dict:
    mei, heat, wind = load_observations(), load_heat_content(), load_wind()
    rows_by_kind = {kind: build_rows(mei, heat, wind, kind) for kind in ("state", "state_plus_wind", "state_plus_wind_memory")}
    rows_by_kind["persistence"] = rows_by_kind["state"]
    groups = tuple(range(1979, VALIDATION_YEARS[-1] + 1))
    splitter = ExpandingWindowGroupSplit(groups, groups, min_train_groups=31, validation_groups=1)

    def fit(train_years: tuple[int, ...], parameters: dict) -> HeatChangeModel:
        return fit_heat_model(rows_by_kind[parameters["kind"]], train_years, parameters)

    def score(model: HeatChangeModel, year: int) -> float:
        evaluation = evaluate(model, rows_by_kind[model.kind], (year,), extreme_threshold=math.inf)
        return float(evaluation["rmse"])

    validation = cross_validate(
        candidates=candidates(),
        splitter=splitter,
        fit=fit,
        score=score,
        objective="minimize",
        aggregate="mean",
        failure_policy="visible",
        seed=20260717,
    )
    family_parameters = best_by_family(validation)
    if validation.selected_parameters is None:
        raise RuntimeError("all heat-change candidates failed")
    refit_years = tuple(range(1979, VALIDATION_YEARS[-1] + 1))
    models = {
        kind: fit_heat_model(rows_by_kind[kind], refit_years, parameters)
        for kind, parameters in family_parameters.items()
    }
    training_changes = np.asarray(
        [row.actual_next_heat - row.current_heat for row in rows_by_kind["state"] if row.target_year in refit_years]
    )
    extreme_threshold = float(np.quantile(training_changes, 0.9))
    test = {
        kind: evaluate(model, rows_by_kind[kind], TEST_YEARS, extreme_threshold)
        for kind, model in models.items()
    }
    family_validation_rmse = {
        kind: min(
            float(candidate.aggregate_score)
            for candidate in validation.candidates
            if candidate.parameters["kind"] == kind and candidate.aggregate_score is not None
        )
        for kind in family_parameters
    }
    selected_kind = str(validation.selected_parameters["kind"])
    paired = {
        f"{selected_kind}_vs_{kind}": paired_year_comparison(test[selected_kind], test[kind], seed=20260730 + index)
        for index, kind in enumerate(family_parameters)
        if kind != selected_kind
    }
    wind_memory_diagnostics = None
    if selected_kind == "state_plus_wind_memory":
        selected_rows = [row for row in rows_by_kind[selected_kind] if row.target_year in refit_years]
        wind_design = np.asarray([row.features[-3:] for row in selected_rows], dtype=float)
        fold_coefficients = []
        for fold in splitter:
            fold_model = fit_heat_model(rows_by_kind[selected_kind], fold.train_group_ids, validation.selected_parameters)
            fold_coefficients.append(
                {
                    "training_end_year": int(max(fold.train_group_ids)),
                    **{
                        key: value
                        for key, value in physical_coefficients(fold_model).items()
                        if key in {"wind", "wind_lag1", "wind_lag2"}
                    },
                }
            )
        kernel = physical_coefficients(models[selected_kind])
        wind_memory_diagnostics = {
            "training_wind_lag_correlation": np.corrcoef(wind_design.T).tolist(),
            "selected_kernel": {key: kernel[key] for key in ("wind", "wind_lag1", "wind_lag2")},
            "selected_kernel_sum": float(sum(kernel[key] for key in ("wind", "wind_lag1", "wind_lag2"))),
            "expanding_fold_kernels": fold_coefficients,
        }
    results = {
        "experiment": "causal low-level wind contribution to ENSO heat recharge",
        "kinopulse_version": version("kinopulse"),
        "source": {
            "mei": json.loads(Path("data/enso/manifest.json").read_text(encoding="utf-8")),
            "heat_content": json.loads(Path("data/enso/heatcentra_manifest.json").read_text(encoding="utf-8")),
            "wind": json.loads(WIND_MANIFEST_PATH.read_text(encoding="utf-8")),
        },
        "protocol": {
            "training_years": [1979, 2009],
            "validation_years": list(VALIDATION_YEARS),
            "test_years": list(TEST_YEARS),
            "information_contract": "Predict heat[t+1]-heat[t] using only MEI, heat, and wind observed through t.",
            "test_status": "reused exploratory evidence; heat outcomes were viewed in report 48",
            "archive_boundary": "wind ends November 2025, so no 2026 wind-forcing forecast is attempted",
        },
        "selection": {
            "selected_parameters": validation.selected_parameters,
            "family_parameters": family_parameters,
            "family_validation_rmse": family_validation_rmse,
            "cross_validation": validation.to_dict(),
        },
        "test_2018_2025": test,
        "paired_year_diagnostics": paired,
        "physical_coefficients": {kind: physical_coefficients(model) for kind, model in models.items()},
        "wind_memory_diagnostics": wind_memory_diagnostics,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    plot_results(results)
    return results


if __name__ == "__main__":
    outcome = run()
    selected = outcome["selection"]["selected_parameters"]["kind"]
    metrics = outcome["test_2018_2025"][selected]
    print(f"Selected: {outcome['selection']['selected_parameters']}")
    print(f"Reused 2018-2025 one-month heat RMSE: {metrics['rmse']:.4f} °C")
    print(f"Heat-change correlation: {metrics['change_correlation']:.3f}")
    print(f"Wrote {ARTIFACT_PATH}")
    print(f"Wrote {FIGURE_PATH}")
