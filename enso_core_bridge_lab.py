"""Audit an observation-system bridge from retired R1 winds to active CORe."""

from __future__ import annotations

import json
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
from kinopulse.validation import SplitConformalIntervalCalibrator

from enso_oscillator_lab import DTYPE, TEST_YEARS, VALIDATION_YEARS, load_observations
from enso_recharge_lab import load_heat_content
from enso_wind_heat_lab import (
    HeatRow,
    build_rows,
    evaluate,
    fit_heat_model,
    heat_features,
    load_wind,
    physical_coefficients,
    predict_change,
    shift_month,
)
from fetch_enso_core_wind import parse_core_csv


CORE_PATH = Path("data/enso/core_uwnd850_140190.csv")
CORE_MANIFEST_PATH = Path("data/enso/core_wind850_manifest.json")
ARTIFACT_PATH = Path("artifacts/enso_core_bridge_analysis.json")
FIGURE_PATH = Path("artifacts/enso_core_bridge_lab.png")
BRIDGE_TRAIN_YEARS = tuple(range(1979, 2010))
BRIDGE_VALIDATION_YEARS = VALIDATION_YEARS
BRIDGE_TEST_YEARS = TEST_YEARS
WIND_PARAMETERS = {"kind": "state_plus_wind_memory", "alpha": 0.001}
STATE_PARAMETERS = {"kind": "state", "alpha": 0.001}


@dataclass(frozen=True)
class BridgeModel:
    kind: str
    alpha: float
    intercept: float
    slope: float

    def predict(self, value: float) -> float:
        return self.intercept + self.slope * value


def load_core_wind(path: Path = CORE_PATH) -> dict[tuple[int, int], float]:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run fetch_enso_core_wind.py first")
    return {
        (int(row["year"]), int(row["month"])): float(row["value"])
        for row in parse_core_csv(path.read_text(encoding="utf-8-sig"))
        if row["value"] is not None
    }


def paired_values(
    core: dict[tuple[int, int], float],
    r1: dict[tuple[int, int], float],
    years: Iterable[int],
) -> tuple[np.ndarray, np.ndarray, list[tuple[int, int]]]:
    selected = set(years)
    keys = sorted(key for key in set(core).intersection(r1) if key[0] in selected)
    if not keys:
        raise ValueError("no paired CORe/R1 wind values")
    return (
        np.asarray([core[key] for key in keys], dtype=float),
        np.asarray([r1[key] for key in keys], dtype=float),
        keys,
    )


def fit_bridge(
    core: dict[tuple[int, int], float],
    r1: dict[tuple[int, int], float],
    years: Iterable[int],
    parameters: dict,
) -> BridgeModel:
    x, target, _ = paired_values(core, r1, years)
    kind = str(parameters["kind"])
    if kind == "identity":
        return BridgeModel(kind, 0.0, 0.0, 1.0)
    if kind == "bias":
        return BridgeModel(kind, 0.0, float(np.mean(target - x)), 1.0)
    if kind != "affine":
        raise ValueError(f"unknown bridge kind {kind!r}")
    alpha = float(parameters["alpha"])
    mean = float(np.mean(x))
    scale = max(float(np.std(x)), 1e-12)
    design = torch.tensor(np.column_stack((np.ones_like(x), (x - mean) / scale)), dtype=DTYPE)
    response = torch.tensor(target, dtype=DTYPE)
    beta = RidgeSolver(lambda_=alpha).solve(design, response).x
    slope = float(beta[1]) / scale
    intercept = float(beta[0]) - slope * mean
    return BridgeModel(kind, alpha, intercept, slope)


def bridge_candidates() -> list[dict]:
    return [
        {"kind": "identity"},
        {"kind": "bias"},
        *({"kind": "affine", "alpha": alpha} for alpha in (0.0, 0.001, 0.01, 0.1, 1.0, 10.0)),
    ]


def bridge_metrics(
    model: BridgeModel,
    core: dict[tuple[int, int], float],
    r1: dict[tuple[int, int], float],
    years: Iterable[int],
) -> dict:
    x, target, keys = paired_values(core, r1, years)
    prediction = model.intercept + model.slope * x
    errors = prediction - target
    annual_rmse = {}
    for year in sorted({key[0] for key in keys}):
        mask = np.asarray([key[0] == year for key in keys])
        annual_rmse[str(year)] = float(np.sqrt(np.mean(errors[mask] ** 2)))
    return {
        "n": len(keys),
        "rmse": float(np.sqrt(np.mean(errors**2))),
        "mae": float(np.mean(np.abs(errors))),
        "bias": float(np.mean(errors)),
        "correlation": float(np.corrcoef(prediction, target)[0, 1]),
        "scale_ratio": float(np.std(prediction) / np.std(target)),
        "sign_agreement": float(np.mean(np.sign(prediction) == np.sign(target))),
        "mean_annual_rmse": float(np.mean(list(annual_rmse.values()))),
        "annual_rmse": annual_rmse,
    }


def select_bridge(core: dict[tuple[int, int], float], r1: dict[tuple[int, int], float]) -> tuple[BridgeModel, list[dict]]:
    audit = []
    for parameters in bridge_candidates():
        model = fit_bridge(core, r1, BRIDGE_TRAIN_YEARS, parameters)
        metrics = bridge_metrics(model, core, r1, BRIDGE_VALIDATION_YEARS)
        audit.append({"parameters": parameters, "model": model.__dict__, "validation": metrics})
    winner = min(audit, key=lambda row: (row["validation"]["mean_annual_rmse"], len(row["parameters"])))
    return BridgeModel(**winner["model"]), audit


def transform_wind(wind: dict[tuple[int, int], float], model: BridgeModel) -> dict[tuple[int, int], float]:
    return {key: model.predict(value) for key, value in wind.items()}


def impulse_metrics(
    model,
    core_bridged: dict[tuple[int, int], float],
    r1: dict[tuple[int, int], float],
    years: Iterable[int],
) -> dict:
    kernel = physical_coefficients(model)
    weights = np.asarray([kernel["wind"], kernel["wind_lag1"], kernel["wind_lag2"]])
    selected = set(years)
    paired = []
    for current in sorted(set(core_bridged).intersection(r1)):
        if shift_month(current, 1)[0] not in selected:
            continue
        lag1, lag2 = shift_month(current, -1), shift_month(current, -2)
        if lag1 not in core_bridged or lag2 not in core_bridged or lag1 not in r1 or lag2 not in r1:
            continue
        core_effect = float(weights @ [core_bridged[current], core_bridged[lag1], core_bridged[lag2]])
        r1_effect = float(weights @ [r1[current], r1[lag1], r1[lag2]])
        paired.append((core_effect, r1_effect))
    values = np.asarray(paired)
    error = values[:, 0] - values[:, 1]
    return {
        "n": len(values),
        "rmse_celsius": float(np.sqrt(np.mean(error**2))),
        "mae_celsius": float(np.mean(np.abs(error))),
        "correlation": float(np.corrcoef(values.T)[0, 1]),
        "sign_agreement": float(np.mean(np.sign(values[:, 0]) == np.sign(values[:, 1]))),
    }


def partial_evaluation(model, rows: list[HeatRow], year: int) -> dict:
    selected = sorted((row for row in rows if row.target_year == year), key=lambda row: row.target_month)
    predicted_change = np.asarray([predict_change(model, row) for row in selected])
    actual_change = np.asarray([row.actual_next_heat - row.current_heat for row in selected])
    return {
        "months": [row.target_month for row in selected],
        "actual_heat": [row.actual_next_heat for row in selected],
        "predicted_heat": [row.current_heat + value for row, value in zip(selected, predicted_change)],
        "actual_change": actual_change.tolist(),
        "predicted_change": predicted_change.tolist(),
        "rmse": float(np.sqrt(np.mean((predicted_change - actual_change) ** 2))),
        "change_correlation": float(np.corrcoef(predicted_change, actual_change)[0, 1]),
    }


def prospective_row(
    mei: dict[tuple[int, int], float],
    heat: dict[tuple[int, int], float],
    wind: dict[tuple[int, int], float],
    kind: str,
    current: tuple[int, int],
) -> HeatRow:
    target = shift_month(current, 1)
    previous, previous2 = shift_month(current, -1), shift_month(current, -2)
    features = heat_features(
        kind,
        target[1],
        heat[current],
        heat[previous],
        mei[current],
        wind[current],
        wind[previous],
        wind[previous2],
    )
    return HeatRow(target[0], target[1], heat[current], float("nan"), features)


def plot_results(results: dict, path: Path = FIGURE_PATH) -> None:
    test = results["bridge"]["test_2018_2025"]
    candidates = results["bridge"]["candidate_audit"]
    labels = [
        row["parameters"]["kind"] if row["parameters"]["kind"] != "affine" else f"affine\n{row['parameters']['alpha']:g}"
        for row in candidates
    ]
    validation = [row["validation"]["mean_annual_rmse"] for row in candidates]
    downstream = results["downstream_heat_test_2018_2025"]
    replay = results["opened_2026_replay"]

    fig, axes = plt.subplots(3, 1, figsize=(10.5, 11), constrained_layout=True)
    axes[0].bar(np.arange(len(labels)), validation, color="#56B4E9")
    axes[0].set_xticks(np.arange(len(labels)), labels)
    axes[0].set_ylabel("mean annual bridge RMSE (m/s)")
    axes[0].set_title("Bridge complexity selected only on 2010–2017 overlap")

    names = ["state", "R1 wind", "bridged CORe wind"]
    values = [downstream[name]["rmse"] for name in names]
    axes[1].bar(names, values, color=["0.55", "#0072B2", "#009E73"])
    axes[1].set_ylabel("2018–2025 heat RMSE (°C)")
    axes[1].set_title(
        f"Untouched bridge test: r={test['correlation']:.3f}, impulse r={results['impulse_test_2018_2025']['correlation']:.3f}"
    )

    months = replay["months"]
    axes[2].plot(months, replay["actual_heat"], color="black", marker="o", label="observed")
    axes[2].plot(months, replay["state_predicted_heat"], color="0.55", marker="o", label="state")
    axes[2].plot(months, replay["wind_predicted_heat"], color="#009E73", marker="o", label="bridged wind")
    forecast = results["prospective_july_2026"]
    axes[2].vlines(
        7,
        forecast["wind_group_conformal_interval"][0],
        forecast["wind_group_conformal_interval"][1],
        color="#009E73",
        lw=4,
        alpha=0.35,
        label="80% whole-year band",
    )
    axes[2].scatter([7], [forecast["wind_predicted_heat"]], color="#009E73", marker="*", s=150, zorder=4)
    axes[2].scatter([7], [forecast["state_predicted_heat"]], color="0.55", marker="*", s=150, zorder=4)
    axes[2].axvline(6.5, color="#D55E00", ls="--", lw=1)
    axes[2].set_xticks(range(1, 8), ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul\nprospective"])
    axes[2].set_ylabel("upper-300m heat anomaly (°C)")
    axes[2].set_title("Opened 2026 replay and frozen July prediction")
    axes[2].legend()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180)
    plt.close(fig)


def run() -> dict:
    mei, heat = load_observations(), load_heat_content()
    r1, core = load_wind(), load_core_wind()
    selected_bridge, candidate_audit = select_bridge(core, r1)
    validation = bridge_metrics(selected_bridge, core, r1, BRIDGE_VALIDATION_YEARS)
    bridge_test = bridge_metrics(selected_bridge, core, r1, BRIDGE_TEST_YEARS)
    core_test_scale = transform_wind(core, selected_bridge)

    refit_years = tuple(range(1979, 2018))
    r1_rows = build_rows(mei, heat, r1, "state_plus_wind_memory")
    core_test_rows = build_rows(mei, heat, core_test_scale, "state_plus_wind_memory")
    state_rows = build_rows(mei, heat, r1, "state")
    wind_model = fit_heat_model(r1_rows, refit_years, WIND_PARAMETERS)
    state_model = fit_heat_model(state_rows, refit_years, STATE_PARAMETERS)
    heat_test = {
        "state": evaluate(state_model, state_rows, BRIDGE_TEST_YEARS, float("inf")),
        "R1 wind": evaluate(wind_model, r1_rows, BRIDGE_TEST_YEARS, float("inf")),
        "bridged CORe wind": evaluate(wind_model, core_test_rows, BRIDGE_TEST_YEARS, float("inf")),
    }
    core_actual = np.asarray(heat_test["bridged CORe wind"]["actual"])
    core_forecast = np.asarray(heat_test["bridged CORe wind"]["forecast"])
    annual_max_errors = np.max(np.abs(core_forecast - core_actual), axis=1)
    conformal = SplitConformalIntervalCalibrator(
        coverage=0.8,
        mode="joint",
        group_ids=[str(year) for year in BRIDGE_TEST_YEARS],
        ordering=list(BRIDGE_TEST_YEARS),
    ).fit(
        lower=np.zeros(len(annual_max_errors)),
        upper=np.zeros(len(annual_max_errors)),
        observed=annual_max_errors,
    )
    if not conformal.supported or conformal.joint_correction is None:
        raise RuntimeError("whole-year conformal calibration is unsupported")
    conformal_radius = float(conformal.joint_correction)
    impulse_test = impulse_metrics(wind_model, core_test_scale, r1, BRIDGE_TEST_YEARS)
    original_gain = heat_test["state"]["rmse"] - heat_test["R1 wind"]["rmse"]
    retained_gain = heat_test["state"]["rmse"] - heat_test["bridged CORe wind"]["rmse"]
    pass_contract = {
        "bridge_correlation_at_least_0_95": bridge_test["correlation"] >= 0.95,
        "bridge_scale_ratio_between_0_9_and_1_1": 0.9 <= bridge_test["scale_ratio"] <= 1.1,
        "impulse_correlation_at_least_0_90": impulse_test["correlation"] >= 0.90,
        "at_least_half_original_heat_gain_retained": retained_gain >= 0.5 * original_gain,
    }
    pass_contract["passed"] = all(pass_contract.values())

    operational_bridge = fit_bridge(core, r1, range(1979, 2026), {"kind": selected_bridge.kind, "alpha": selected_bridge.alpha})
    operational_core = transform_wind(core, operational_bridge)
    operational_rows = build_rows(mei, heat, operational_core, "state_plus_wind_memory")
    replay = partial_evaluation(wind_model, operational_rows, 2026)
    replay_state = partial_evaluation(state_model, build_rows(mei, heat, operational_core, "state"), 2026)
    replay_combined = {
        "status": "opened explanatory replay; 2026 heat outcomes were viewed in report 48",
        "months": replay["months"],
        "actual_heat": replay["actual_heat"],
        "actual_change": replay["actual_change"],
        "wind_predicted_heat": replay["predicted_heat"],
        "wind_predicted_change": replay["predicted_change"],
        "wind_rmse": replay["rmse"],
        "state_predicted_heat": replay_state["predicted_heat"],
        "state_predicted_change": replay_state["predicted_change"],
        "state_rmse": replay_state["rmse"],
    }

    if not pass_contract["passed"]:
        raise RuntimeError(f"CORe bridge failed its frozen continuation contract: {pass_contract}")
    current = (2026, 6)
    wind_row = prospective_row(mei, heat, operational_core, "state_plus_wind_memory", current)
    state_row = prospective_row(mei, heat, operational_core, "state", current)
    prospective = {
        "issued_after_data_through": "2026-06",
        "target": "2026-07",
        "outcome_status": "unobserved in the frozen NOAA heat-content snapshot",
        "current_heat": heat[current],
        "bridged_core_wind_current": operational_core[current],
        "wind_predicted_change": predict_change(wind_model, wind_row),
        "wind_predicted_heat": heat[current] + predict_change(wind_model, wind_row),
        "wind_group_conformal_coverage": 0.8,
        "wind_group_conformal_calibration_years": list(BRIDGE_TEST_YEARS),
        "wind_group_conformal_rank": conformal.joint_rank,
        "wind_group_conformal_radius": conformal_radius,
        "wind_group_conformal_interval": [
            heat[current] + predict_change(wind_model, wind_row) - conformal_radius,
            heat[current] + predict_change(wind_model, wind_row) + conformal_radius,
        ],
        "wind_group_conformal_contract": "calibrated on each later year's maximum monthly absolute error; reused exploratory evidence, only eight groups",
        "state_predicted_change": predict_change(state_model, state_row),
        "state_predicted_heat": heat[current] + predict_change(state_model, state_row),
    }

    results = {
        "experiment": "R1-to-CORe tropical-wind measurement bridge",
        "kinopulse_version": version("kinopulse"),
        "source": {
            "r1_wind": json.loads(Path("data/enso/wind850_manifest.json").read_text(encoding="utf-8")),
            "core_wind": json.loads(CORE_MANIFEST_PATH.read_text(encoding="utf-8")),
            "mei": json.loads(Path("data/enso/manifest.json").read_text(encoding="utf-8")),
            "heat_content": json.loads(Path("data/enso/heatcentra_manifest.json").read_text(encoding="utf-8")),
        },
        "protocol": {
            "bridge_training_years": [1979, 2009],
            "bridge_validation_years": list(BRIDGE_VALIDATION_YEARS),
            "bridge_test_years": list(BRIDGE_TEST_YEARS),
            "selection_metric": "mean of whole-year monthly bridge RMSE",
            "test_status": "first use of 2018-2025 for the CORe/R1 measurement bridge",
            "downstream_model": "report-49 R1 wind-memory structure and penalty, refit only through 2017",
        },
        "bridge": {
            "candidate_audit": candidate_audit,
            "selected_training_fit": selected_bridge.__dict__,
            "validation_2010_2017": validation,
            "test_2018_2025": bridge_test,
            "operational_refit_1979_2025": operational_bridge.__dict__,
        },
        "impulse_test_2018_2025": impulse_test,
        "downstream_heat_test_2018_2025": heat_test,
        "continuation_contract": {
            **pass_contract,
            "original_r1_gain_over_state": original_gain,
            "bridged_core_gain_over_state": retained_gain,
            "fraction_of_gain_retained": retained_gain / original_gain,
        },
        "opened_2026_replay": replay_combined,
        "prospective_july_2026": prospective,
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    plot_results(results)
    return results


if __name__ == "__main__":
    outcome = run()
    bridge = outcome["bridge"]["selected_training_fit"]
    test = outcome["bridge"]["test_2018_2025"]
    forecast = outcome["prospective_july_2026"]
    print(f"Selected bridge: {bridge}")
    print(f"2018-2025 bridge correlation: {test['correlation']:.4f}; RMSE {test['rmse']:.4f} m/s")
    print(f"July 2026 predicted heat: {forecast['wind_predicted_heat']:.3f} °C")
    print(f"Wrote {ARTIFACT_PATH}")
    print(f"Wrote {FIGURE_PATH}")
