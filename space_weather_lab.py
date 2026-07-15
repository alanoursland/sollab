"""Learn a compact forced model of a geomagnetic storm from NASA OMNI data."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.opt.least_squares import RidgeSolver


DTYPE = torch.float64
SOURCE_URL = "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_2015.dat"


@dataclass
class OmniData:
    year: torch.Tensor
    day: torch.Tensor
    hour: torch.Tensor
    bz_gsm: torch.Tensor
    speed: torch.Tensor
    pressure: torch.Tensor
    electric_field: torch.Tensor
    dst: torch.Tensor
    valid: torch.Tensor


def parse_omni_lines(lines) -> OmniData:
    rows = [[float(value) for value in line.split()] for line in lines if line.strip()]
    values = torch.tensor(rows, dtype=DTYPE)
    if values.ndim != 2 or values.shape[1] < 41:
        raise ValueError("Expected NASA OMNI2 rows with at least 41 columns")
    bz, speed = values[:, 16], values[:, 24]
    pressure, electric, dst = values[:, 28], values[:, 35], values[:, 40]
    valid = (bz < 900) & (speed < 9000) & (pressure < 90) & (electric < 900) & (dst < 90000)
    return OmniData(values[:, 0], values[:, 1], values[:, 2], bz, speed, pressure, electric, dst, valid)


def load_omni(path: Path = Path("data/omni/omni2_2015.dat")) -> OmniData:
    if not path.exists():
        raise FileNotFoundError(f"{path} is missing; run `.venv\\Scripts\\python.exe fetch_omni.py`")
    return parse_omni_lines(path.read_text(encoding="ascii").splitlines())


def prepare_regression(data: OmniData, holdout=(70, 90)):
    consecutive = ((data.hour[1:] - data.hour[:-1]) % 24) == 1
    pair_valid = data.valid[:-1] & data.valid[1:] & consecutive
    indices = torch.where(pair_valid)[0]
    held_out = (data.day[indices] >= holdout[0]) & (data.day[indices] <= holdout[1])
    features = torch.stack(
        (
            torch.ones_like(data.dst[indices]),
            data.dst[indices],
            data.electric_field[indices].clamp_min(0),
            data.pressure[indices + 1] - data.pressure[indices],
        ),
        dim=1,
    )
    target = data.dst[indices + 1] - data.dst[indices]
    mean = features[~held_out, 1:].mean(dim=0)
    scale = features[~held_out, 1:].std(dim=0)
    standardized = torch.cat((features[:, :1], (features[:, 1:] - mean) / scale), dim=1)
    return indices, held_out, features, standardized, target, mean, scale


def fit_models(data: OmniData):
    indices, held_out, features, standardized, target, mean, scale = prepare_regression(data)
    solver = RidgeSolver(lambda_=0.01)
    continuous = solver.solve(standardized[~held_out], target[~held_out]).x
    driven = features[:, 2] > 0.5
    hybrid = {
        "quiet": solver.solve(standardized[(~held_out) & (~driven)], target[(~held_out) & (~driven)]).x,
        "driven": solver.solve(standardized[(~held_out) & driven], target[(~held_out) & driven]).x,
    }
    return continuous, hybrid, (indices, held_out, features, standardized, target, mean, scale)


def rollout(data: OmniData, coefficients, mean, scale, holdout=(70, 90), hybrid=False):
    selected = torch.where((data.day >= holdout[0]) & (data.day <= holdout[1]) & data.valid)[0]
    estimate = data.dst[selected[0]].item()
    predictions = [estimate]
    for current, following in zip(selected[:-1], selected[1:]):
        if following != current + 1:
            estimate = data.dst[following].item()
            predictions.append(estimate)
            continue
        raw = torch.tensor(
            [
                1.0,
                estimate,
                max(data.electric_field[current].item(), 0.0),
                (data.pressure[following] - data.pressure[current]).item(),
            ],
            dtype=DTYPE,
        )
        design = torch.cat((raw[:1], (raw[1:] - mean) / scale))
        if hybrid:
            mode = "driven" if raw[2] > 0.5 else "quiet"
            estimate += (design @ coefficients[mode]).item()
        else:
            estimate += (design @ coefficients).item()
        predictions.append(estimate)
    return selected, torch.tensor(predictions, dtype=DTYPE)


def rmse(predicted, observed):
    return torch.sqrt(torch.mean((predicted - observed) ** 2)).item()


def main(data_path: Path = Path("data/omni/omni2_2015.dat"), output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_omni(data_path)
    continuous, hybrid, prepared = fit_models(data)
    indices, held_out, _, standardized, target, mean, scale = prepared
    selected, continuous_rollout = rollout(data, continuous, mean, scale)
    _, hybrid_rollout = rollout(data, hybrid, mean, scale, hybrid=True)
    observed = data.dst[selected]
    one_step = standardized @ continuous

    report = {
        "experiment": "compact forced model of the 2015 St. Patrick's Day geomagnetic storm",
        "source": SOURCE_URL,
        "source_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "holdout_day_of_year": [70, 90],
        "observed_storm_minimum_dst_nt": observed.min().item(),
        "continuous_model_minimum_dst_nt": continuous_rollout.min().item(),
        "hybrid_model_minimum_dst_nt": hybrid_rollout.min().item(),
        "continuous_rollout_rmse_nt": rmse(continuous_rollout, observed),
        "hybrid_rollout_rmse_nt": rmse(hybrid_rollout, observed),
        "constant_initial_state_rmse_nt": rmse(torch.full_like(observed, observed[0]), observed),
        "held_out_one_step_change_rmse_nt": rmse(one_step[held_out], target[held_out]),
        "held_out_persistence_change_rmse_nt": rmse(torch.zeros_like(target[held_out]), target[held_out]),
        "continuous_coefficients_standardized": continuous.tolist(),
        "hybrid_coefficients_standardized": {key: value.tolist() for key, value in hybrid.items()},
        "features": ["bias", "Dst", "positive solar-wind electric field", "pressure change"],
    }
    (output_dir / "space_weather_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    hours = torch.arange(len(selected), dtype=DTYPE)
    fig, (forcing, response) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, constrained_layout=True)
    forcing.plot(hours, data.electric_field[selected].clamp_min(0), color="#e17055")
    forcing.set(ylabel="southward electric field (mV/m)", title="Observed solar-wind forcing")
    forcing.grid(alpha=0.2)

    response.plot(hours, observed, color="#2d3436", linewidth=1.8, label="observed Dst")
    response.plot(hours, continuous_rollout, color="#0984e3", label="continuous model")
    response.plot(hours, hybrid_rollout, color="#6c5ce7", linestyle="--", label="two-regime model")
    response.axhline(0, color="black", linewidth=0.7)
    response.set(xlabel="hours since day 70 of 2015", ylabel="Dst (nT)", title="Held-out geomagnetic response")
    response.legend(frameon=False, ncol=3)
    response.grid(alpha=0.2)
    fig.suptitle("KinoPulse real-data exploration · learning a geomagnetic storm")
    fig.savefig(output_dir / "space_weather_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
