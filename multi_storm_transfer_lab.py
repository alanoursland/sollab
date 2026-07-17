"""Chronological transfer test for compact Dst response models across storms."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
import numpy as np
from scipy.signal import lfilter
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.opt.least_squares import RidgeSolver
from open_source_commit_ecology_lab import DTYPE
from space_weather_lab import parse_omni_lines


STORM_THRESHOLD_NT = -100.0
LOCAL_RADIUS_HOURS = 120
MINIMUM_SEPARATION_HOURS = 14 * 24
PRE_HOURS = 48
POST_HOURS = 168
MEMORY_HALF_LIVES_HOURS = (3.0, 6.0, 12.0, 24.0, 48.0)


@dataclass
class PopulationData:
    timestamps: list[datetime]
    year: torch.Tensor
    bz_gsm: torch.Tensor
    speed: torch.Tensor
    pressure: torch.Tensor
    electric_field: torch.Tensor
    dst: torch.Tensor
    valid: torch.Tensor
    source_records: list[dict]


@dataclass(frozen=True)
class Storm:
    index: int
    timestamp: datetime
    minimum_dst_nt: float
    complete_forcing_window: bool


@dataclass
class FittedResponseModel:
    coefficients: torch.Tensor
    feature_mean: torch.Tensor
    feature_scale: torch.Tensor
    memory_half_life_hours: float | None
    training_years: tuple[int, int]


def electric_valid(data: PopulationData) -> torch.Tensor:
    return torch.isfinite(data.electric_field) & (data.electric_field < 900)


def response_valid(data: PopulationData) -> torch.Tensor:
    return (
        electric_valid(data)
        & torch.isfinite(data.pressure)
        & (data.pressure < 90)
        & torch.isfinite(data.dst)
        & (data.dst < 90000)
    )


def load_population(manifest_path: Path = Path("data/omni_population/manifest.json")) -> PopulationData:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    timestamps = []
    years = []
    fields = {name: [] for name in ("bz_gsm", "speed", "pressure", "electric_field", "dst", "valid")}
    for record in manifest["records"]:
        path = Path(record["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError(f"Source digest mismatch for {path}")
        parsed = parse_omni_lines(path.read_text(encoding="ascii").splitlines())
        year = int(record["year"])
        years.append(torch.full_like(parsed.year, year))
        for day, hour in zip(parsed.day.tolist(), parsed.hour.tolist()):
            timestamps.append(
                datetime(year, 1, 1, tzinfo=timezone.utc)
                + timedelta(days=int(day) - 1, hours=int(hour))
            )
        for name in fields:
            fields[name].append(getattr(parsed, name))
    if any(right - left != timedelta(hours=1) for left, right in zip(timestamps[:-1], timestamps[1:])):
        raise ValueError("OMNI population is not a continuous hourly grid")
    return PopulationData(
        timestamps=timestamps,
        year=torch.cat(years),
        source_records=manifest["records"],
        **{name: torch.cat(values) for name, values in fields.items()},
    )


def select_storms(data: PopulationData) -> list[Storm]:
    dst_valid = torch.isfinite(data.dst) & (data.dst < 90000)
    candidates = []
    for index in range(LOCAL_RADIUS_HOURS, len(data.dst) - LOCAL_RADIUS_HOURS):
        if not dst_valid[index] or data.dst[index] > STORM_THRESHOLD_NT:
            continue
        window = data.dst[index - LOCAL_RADIUS_HOURS : index + LOCAL_RADIUS_HOURS + 1].clone()
        valid_window = dst_valid[index - LOCAL_RADIUS_HOURS : index + LOCAL_RADIUS_HOURS + 1]
        window[~valid_window] = torch.inf
        if index - LOCAL_RADIUS_HOURS + int(torch.argmin(window)) == index:
            candidates.append(index)

    accepted = []
    for index in sorted(candidates, key=lambda candidate: (float(data.dst[candidate]), candidate)):
        if all(abs(index - other) >= MINIMUM_SEPARATION_HOURS for other in accepted):
            accepted.append(index)
    result = []
    required_valid = response_valid(data)
    for index in sorted(accepted):
        start, stop = index - PRE_HOURS, index + POST_HOURS
        complete = start >= 0 and stop < len(data.dst) and bool(required_valid[start : stop + 1].all())
        result.append(
            Storm(index, data.timestamps[index], float(data.dst[index]), complete)
        )
    return result


def forcing_memory(electric_field: torch.Tensor, valid: torch.Tensor, half_life_hours: float) -> torch.Tensor:
    alpha = math.exp(-math.log(2.0) / half_life_hours)
    values = electric_field.detach().cpu().numpy().clip(min=0)
    mask = valid.detach().cpu().numpy().astype(bool)
    result = np.zeros_like(values)
    padded = np.concatenate(([False], mask, [False]))
    starts = np.flatnonzero(~padded[:-1] & padded[1:])
    stops = np.flatnonzero(padded[:-1] & ~padded[1:])
    for start, stop in zip(starts, stops):
        segment = values[start:stop]
        result[start:stop], _ = lfilter(
            [1.0 - alpha], [1.0, -alpha], segment, zi=[alpha * segment[0]]
        )
    return torch.as_tensor(result, dtype=electric_field.dtype, device=electric_field.device)


def design_matrix(
    data: PopulationData,
    memory_half_life_hours: float | None,
    memory_trace: torch.Tensor | None = None,
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    consecutive = torch.tensor(
        [right - left == timedelta(hours=1) for left, right in zip(data.timestamps[:-1], data.timestamps[1:])],
        dtype=torch.bool,
    )
    required_valid = response_valid(data)
    pair_valid = required_valid[:-1] & required_valid[1:] & consecutive
    features = [
        torch.ones_like(data.dst[:-1]),
        data.dst[:-1],
        data.electric_field[:-1].clamp_min(0),
        data.pressure[1:] - data.pressure[:-1],
    ]
    if memory_half_life_hours is not None:
        memory_trace = (
            forcing_memory(data.electric_field, electric_valid(data), memory_half_life_hours)
            if memory_trace is None
            else memory_trace
        )
        features.append(memory_trace[:-1])
    return torch.stack(features, dim=1), data.dst[1:] - data.dst[:-1], pair_valid


def fit_response_model(
    data: PopulationData,
    training_years: tuple[int, int],
    memory_half_life_hours: float | None = None,
    memory_trace: torch.Tensor | None = None,
) -> FittedResponseModel:
    features, target, pair_valid = design_matrix(data, memory_half_life_hours, memory_trace)
    year_mask = (data.year[:-1] >= training_years[0]) & (data.year[:-1] <= training_years[1])
    selected = pair_valid & year_mask
    mean = features[selected, 1:].mean(dim=0)
    scale = features[selected, 1:].std(dim=0).clamp_min(1e-12)
    standardized = torch.cat((features[:, :1], (features[:, 1:] - mean) / scale), dim=1)
    coefficient = RidgeSolver(lambda_=0.01).solve(standardized[selected], target[selected]).x
    return FittedResponseModel(coefficient, mean, scale, memory_half_life_hours, training_years)


def rollout_storm(
    data: PopulationData,
    storm: Storm,
    model: FittedResponseModel,
    memory_trace: torch.Tensor | None = None,
) -> torch.Tensor:
    start, stop = storm.index - PRE_HOURS, storm.index + POST_HOURS
    if not storm.complete_forcing_window:
        raise ValueError("storm window has incomplete forcing")
    memory = memory_trace
    if model.memory_half_life_hours is not None and memory is None:
        memory = forcing_memory(data.electric_field, electric_valid(data), model.memory_half_life_hours)
    estimate = float(data.dst[start])
    predictions = [estimate]
    for index in range(start, stop):
        raw = [
            1.0,
            estimate,
            float(data.electric_field[index].clamp_min(0)),
            float(data.pressure[index + 1] - data.pressure[index]),
        ]
        if memory is not None:
            raw.append(float(memory[index]))
        raw_tensor = torch.tensor(raw, dtype=DTYPE)
        design = torch.cat((raw_tensor[:1], (raw_tensor[1:] - model.feature_mean) / model.feature_scale))
        estimate += float(design @ model.coefficients)
        predictions.append(estimate)
    return torch.tensor(predictions, dtype=DTYPE)


def evaluate_model(
    data: PopulationData,
    storms: list[Storm],
    model: FittedResponseModel,
    memory_trace: torch.Tensor | None = None,
) -> dict:
    rows = []
    for storm in storms:
        start, stop = storm.index - PRE_HOURS, storm.index + POST_HOURS
        observed = data.dst[start : stop + 1]
        predicted = rollout_storm(data, storm, model, memory_trace)
        persistence = torch.full_like(observed, observed[0])
        tail = slice(len(observed) - 72, len(observed))
        rows.append(
            {
                "timestamp_utc": storm.timestamp.isoformat(),
                "minimum_dst_nt": storm.minimum_dst_nt,
                "rollout_rmse_nt": torch.sqrt(torch.mean((predicted - observed) ** 2)).item(),
                "persistence_rmse_nt": torch.sqrt(torch.mean((persistence - observed) ** 2)).item(),
                "tail_72h_rmse_nt": torch.sqrt(torch.mean((predicted[tail] - observed[tail]) ** 2)).item(),
                "observed_minimum_nt": observed.min().item(),
                "predicted_minimum_nt": predicted.min().item(),
            }
        )
    return {
        "events": rows,
        "mean_event_rmse_nt": sum(row["rollout_rmse_nt"] for row in rows) / len(rows),
        "mean_persistence_rmse_nt": sum(row["persistence_rmse_nt"] for row in rows) / len(rows),
        "mean_tail_72h_rmse_nt": sum(row["tail_72h_rmse_nt"] for row in rows) / len(rows),
    }


def storm_completeness_diagnostics(data: PopulationData, storm: Storm) -> dict:
    start, stop = storm.index - PRE_HOURS, storm.index + POST_HOURS
    channels = {
        "bz_gsm": torch.isfinite(data.bz_gsm) & (data.bz_gsm < 900),
        "speed": torch.isfinite(data.speed) & (data.speed < 9000),
        "pressure": torch.isfinite(data.pressure) & (data.pressure < 90),
        "electric_field": torch.isfinite(data.electric_field) & (data.electric_field < 900),
        "dst": torch.isfinite(data.dst) & (data.dst < 90000),
    }
    return {
        "timestamp_utc": storm.timestamp.isoformat(),
        "minimum_dst_nt": storm.minimum_dst_nt,
        "complete_forcing_window": storm.complete_forcing_window,
        "invalid_hours": {
            name: int((~valid[start : stop + 1]).sum()) for name, valid in channels.items()
        },
    }


def main(
    manifest_path: Path = Path("data/omni_population/manifest.json"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = load_population(manifest_path)
    all_storms = select_storms(data)
    eligible = [storm for storm in all_storms if storm.complete_forcing_window]
    validation_storms = [storm for storm in eligible if 2016 <= storm.timestamp.year <= 2018]
    test_storms = [storm for storm in eligible if 2019 <= storm.timestamp.year <= 2025]
    if not validation_storms or not test_storms:
        raise RuntimeError("The frozen selection produced no validation or test storms")

    memory_cache = {
        half_life: forcing_memory(data.electric_field, electric_valid(data), half_life)
        for half_life in MEMORY_HALF_LIVES_HOURS
    }
    initial_base = fit_response_model(data, (2010, 2015), None)
    validation_base = evaluate_model(data, validation_storms, initial_base)
    candidate_results = []
    for half_life in MEMORY_HALF_LIVES_HOURS:
        model = fit_response_model(data, (2010, 2015), half_life, memory_cache[half_life])
        evaluation = evaluate_model(data, validation_storms, model, memory_cache[half_life])
        candidate_results.append({"half_life_hours": half_life, **evaluation})
    selected_half_life = min(candidate_results, key=lambda result: result["mean_event_rmse_nt"])[
        "half_life_hours"
    ]

    base = fit_response_model(data, (2010, 2018), None)
    memory = fit_response_model(data, (2010, 2018), selected_half_life, memory_cache[selected_half_life])
    base_test = evaluate_model(data, test_storms, base)
    memory_test = evaluate_model(data, test_storms, memory, memory_cache[selected_half_life])
    manifest_digest = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    report = {
        "experiment": "chronological multi-storm transfer of compact Dst response models",
        "source": "NASA/SPDF hourly OMNI2 annual files",
        "manifest_sha256": manifest_digest,
        "source_years": [2010, 2025],
        "hourly_rows": len(data.timestamps),
        "valid_required_input_rows": int(response_valid(data).sum()),
        "storm_selection": {
            "threshold_dst_nt": STORM_THRESHOLD_NT,
            "local_minimum_radius_hours": LOCAL_RADIUS_HOURS,
            "minimum_separation_hours": MINIMUM_SEPARATION_HOURS,
            "window_hours_relative_to_minimum": [-PRE_HOURS, POST_HOURS],
            "candidate_storms": len(all_storms),
            "complete_forcing_storms": len(eligible),
            "excluded_incomplete_forcing_storms": [
                {"timestamp_utc": storm.timestamp.isoformat(), "minimum_dst_nt": storm.minimum_dst_nt}
                for storm in all_storms
                if not storm.complete_forcing_window
            ],
            "completeness_diagnostics": [
                storm_completeness_diagnostics(data, storm) for storm in all_storms
            ],
            "period_counts": {
                "initial_fit_2010_2015": {
                    "candidates": sum(storm.timestamp.year <= 2015 for storm in all_storms),
                    "complete": sum(storm.timestamp.year <= 2015 for storm in eligible),
                },
                "validation_2016_2018": {
                    "candidates": sum(2016 <= storm.timestamp.year <= 2018 for storm in all_storms),
                    "complete": len(validation_storms),
                },
                "test_2019_2025": {
                    "candidates": sum(storm.timestamp.year >= 2019 for storm in all_storms),
                    "complete": len(test_storms),
                },
            },
        },
        "chronology": {
            "initial_fit_years": [2010, 2015],
            "memory_selection_years": [2016, 2018],
            "final_refit_years": [2010, 2018],
            "untouched_test_years": [2019, 2025],
            "validation_storm_count": len(validation_storms),
            "test_storm_count": len(test_storms),
        },
        "validation_base_model": validation_base,
        "memory_candidates": candidate_results,
        "selected_memory_half_life_hours": selected_half_life,
        "test_base_model": base_test,
        "test_memory_model": memory_test,
        "test_relative_rmse_change": memory_test["mean_event_rmse_nt"] / base_test["mean_event_rmse_nt"] - 1,
        "test_event_win_counts": {
            "base_better_than_persistence": sum(
                row["rollout_rmse_nt"] < row["persistence_rmse_nt"]
                for row in base_test["events"]
            ),
            "memory_better_than_base": sum(
                memory_row["rollout_rmse_nt"] < base_row["rollout_rmse_nt"]
                for base_row, memory_row in zip(base_test["events"], memory_test["events"])
            ),
            "events": len(test_storms),
        },
        "fitted_models": {
            "base": {
                "coefficients": base.coefficients.tolist(),
                "feature_mean": base.feature_mean.tolist(),
                "feature_scale": base.feature_scale.tolist(),
            },
            "memory": {
                "coefficients": memory.coefficients.tolist(),
                "feature_mean": memory.feature_mean.tolist(),
                "feature_scale": memory.feature_scale.tolist(),
                "half_life_hours": selected_half_life,
            },
        },
        "interpretation_boundary": (
            "models use observed solar-wind forcing throughout each rollout and are response models, not autonomous forecasts"
        ),
    }
    (output_dir / "multi_storm_transfer.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    fig, axes = plt.subplots(len(test_storms), 1, figsize=(12, 2.7 * len(test_storms)), constrained_layout=True)
    axes = [axes] if len(test_storms) == 1 else list(axes)
    for axis, storm in zip(axes, test_storms):
        start, stop = storm.index - PRE_HOURS, storm.index + POST_HOURS
        hours = torch.arange(-PRE_HOURS, POST_HOURS + 1)
        observed = data.dst[start : stop + 1]
        axis.plot(hours, observed, color="black", label="observed Dst")
        axis.plot(hours, rollout_storm(data, storm, base), color="#1565c0", label="compact base")
        axis.plot(
            hours,
            rollout_storm(data, storm, memory, memory_cache[selected_half_life]),
            color="#d84315",
            label="forcing memory",
        )
        axis.axvline(0, color="gray", linewidth=0.8, linestyle="--")
        axis.set(ylabel="Dst (nT)", title=f"{storm.timestamp:%Y-%m-%d} · observed minimum {storm.minimum_dst_nt:.0f} nT")
        axis.grid(alpha=0.2)
    axes[-1].set(xlabel="hours relative to selected Dst minimum")
    axes[0].legend(frameon=False, ncol=3)
    fig.savefig(output_dir / "multi_storm_transfer.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
