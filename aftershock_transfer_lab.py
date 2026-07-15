"""Leave-one-sequence-out transfer of aftershock relaxation laws."""

from __future__ import annotations

import csv
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.identification.parametric import LevenbergMarquardt

from aftershock_lab import (
    DTYPE,
    _encode_p,
    _exprel,
    anscombe_residual,
    fit_relaxation_model,
    poisson_deviance,
)
from fetch_aftershock_benchmark import SEQUENCES, SequenceSpec, source_url


MIN_TIME_DAYS = 1.0 / 24.0
CALIBRATION_END_DAYS = 1.0
MAX_TIME_DAYS = 30.0
CONTROL_START_DAYS = -30.0
CONTROL_END_DAYS = -2.0


@dataclass
class SequenceData:
    spec: SequenceSpec
    times_days: torch.Tensor
    counts: torch.Tensor
    background: float
    sha256: str
    source_rows: int


@dataclass
class SharedFit:
    model: str
    theta: torch.Tensor
    parameters: dict[str, float | list[float]]
    objective: float
    iterations: int


def make_transfer_bins(
    calibration_bins: int = 12, evaluation_bins: int = 24
) -> torch.Tensor:
    calibration = torch.logspace(
        math.log10(MIN_TIME_DAYS),
        math.log10(CALIBRATION_END_DAYS),
        calibration_bins + 1,
        dtype=DTYPE,
    )
    evaluation = torch.logspace(
        math.log10(CALIBRATION_END_DAYS),
        math.log10(MAX_TIME_DAYS),
        evaluation_bins + 1,
        dtype=DTYPE,
    )
    return torch.cat((calibration, evaluation[1:]))


def load_sequence(
    spec: SequenceSpec,
    edges: torch.Tensor,
    data_dir: Path = Path("data/aftershock_benchmark"),
) -> SequenceData:
    path = data_dir / f"{spec.slug}.csv"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing; run `.venv\\Scripts\\python.exe "
            "fetch_aftershock_benchmark.py`"
        )
    payload = path.read_bytes()
    rows = list(csv.DictReader(payload.decode("utf-8").splitlines()))
    times = []
    for row in rows:
        if row["id"] == spec.event_id:
            continue
        event_time = datetime.fromisoformat(
            row["time"].replace("Z", "+00:00")
        )
        times.append((event_time - spec.origin).total_seconds() / 86400.0)
    time_tensor = torch.tensor(times, dtype=DTYPE)
    usable = time_tensor[
        (time_tensor >= edges[0]) & (time_tensor <= edges[-1])
    ]
    counts = torch.histogram(usable, bins=edges).hist.to(dtype=DTYPE)
    control_count = int(
        (
            (time_tensor >= CONTROL_START_DAYS)
            & (time_tensor < CONTROL_END_DAYS)
        ).sum()
    )
    background = control_count / (CONTROL_END_DAYS - CONTROL_START_DAYS)
    return SequenceData(
        spec=spec,
        times_days=time_tensor,
        counts=counts,
        background=background,
        sha256=hashlib.sha256(payload).hexdigest(),
        source_rows=len(rows),
    )


def _power_integral(
    edges: torch.Tensor, offset: torch.Tensor, exponent: torch.Tensor
) -> torch.Tensor:
    start, end = edges[:-1], edges[1:]
    log_start = torch.log(start + offset)
    log_ratio = torch.log((end + offset) / (start + offset))
    one_minus_p = 1.0 - exponent
    return (
        torch.exp(one_minus_p * log_start)
        * log_ratio
        * _exprel(one_minus_p * log_ratio)
    )


def _exponential_integral(
    edges: torch.Tensor, timescale: torch.Tensor
) -> torch.Tensor:
    start, end = edges[:-1], edges[1:]
    return timescale * (
        torch.exp(-start / timescale) - torch.exp(-end / timescale)
    )


def shared_expected_counts(
    theta: torch.Tensor,
    edges: torch.Tensor,
    backgrounds: torch.Tensor,
    model: str,
) -> torch.Tensor:
    sequence_count = len(backgrounds)
    amplitudes = torch.exp(theta[:sequence_count])
    if model == "omori":
        offset = torch.exp(theta[-2])
        exponent = 0.3 + 1.7 * torch.sigmoid(theta[-1])
        kernel = _power_integral(edges, offset, exponent)
    elif model == "exponential":
        timescale = torch.exp(theta[-1])
        kernel = _exponential_integral(edges, timescale)
    else:
        raise ValueError(f"Unknown shared model: {model}")
    widths = torch.diff(edges)
    return (
        amplitudes[:, None] * kernel[None, :]
        + backgrounds[:, None] * widths[None, :]
    )


def _initial_amplitudes(
    sequences: list[SequenceData],
    edges: torch.Tensor,
    kernel: torch.Tensor,
) -> list[float]:
    widths = torch.diff(edges)
    values = []
    for sequence in sequences:
        transient_count = (
            sequence.counts - sequence.background * widths
        ).sum().clamp_min(1.0)
        values.append(float(transient_count / kernel.sum()))
    return values


def fit_shared_shape(
    sequences: list[SequenceData], edges: torch.Tensor, model: str
) -> SharedFit:
    backgrounds = torch.tensor(
        [sequence.background for sequence in sequences], dtype=DTYPE
    )
    observed = torch.stack([sequence.counts for sequence in sequences])
    if model == "omori":
        shape_starts = [(0.01, 0.8), (0.05, 1.05), (0.2, 1.3)]
    elif model == "exponential":
        shape_starts = [(0.2,), (1.0,), (4.0,)]
    else:
        raise ValueError(f"Unknown shared model: {model}")

    def residual(theta: torch.Tensor) -> torch.Tensor:
        expected = shared_expected_counts(theta, edges, backgrounds, model)
        return anscombe_residual(expected, observed).reshape(-1)

    candidates = []
    for shape in shape_starts:
        if model == "omori":
            offset, exponent = shape
            kernel = _power_integral(
                edges,
                torch.tensor(offset, dtype=DTYPE),
                torch.tensor(exponent, dtype=DTYPE),
            )
            amplitudes = _initial_amplitudes(sequences, edges, kernel)
            values = [
                *[math.log(value) for value in amplitudes],
                math.log(offset),
                _encode_p(exponent),
            ]
        else:
            (timescale,) = shape
            kernel = _exponential_integral(
                edges, torch.tensor(timescale, dtype=DTYPE)
            )
            amplitudes = _initial_amplitudes(sequences, edges, kernel)
            values = [
                *[math.log(value) for value in amplitudes],
                math.log(timescale),
            ]
        initial = torch.tensor(values, dtype=DTYPE)
        optimizer = LevenbergMarquardt(residual, initial)
        try:
            theta = optimizer.optimize(max_iter=80, tolerance=1e-8)
            objective = float(residual(theta).square().sum())
        except (RuntimeError, ValueError):
            continue
        if math.isfinite(objective):
            candidates.append((objective, theta, len(optimizer.history)))
    if not candidates:
        raise RuntimeError(f"All KinoPulse shared {model} fits failed")

    objective, theta, iterations = min(candidates, key=lambda item: item[0])
    amplitudes = torch.exp(theta[: len(sequences)]).tolist()
    if model == "omori":
        parameters: dict[str, float | list[float]] = {
            "sequence_amplitudes": amplitudes,
            "c_days": float(torch.exp(theta[-2])),
            "p": float(0.3 + 1.7 * torch.sigmoid(theta[-1])),
        }
    else:
        parameters = {
            "sequence_amplitudes": amplitudes,
            "tau_days": float(torch.exp(theta[-1])),
        }
    return SharedFit(model, theta, parameters, objective, iterations)


def calibrate_amplitude(
    counts: torch.Tensor,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    background: float,
    model: str,
    shape_parameters: dict[str, float | list[float]],
) -> tuple[float, torch.Tensor]:
    if model == "omori":
        kernel = _power_integral(
            edges,
            torch.tensor(shape_parameters["c_days"], dtype=DTYPE),
            torch.tensor(shape_parameters["p"], dtype=DTYPE),
        )
    elif model == "exponential":
        kernel = _exponential_integral(
            edges,
            torch.tensor(shape_parameters["tau_days"], dtype=DTYPE),
        )
    else:
        raise ValueError(f"Unknown calibration model: {model}")
    widths = torch.diff(edges)

    def expected(theta: torch.Tensor) -> torch.Tensor:
        return torch.exp(theta[0]) * kernel + background * widths

    def residual(theta: torch.Tensor) -> torch.Tensor:
        return anscombe_residual(
            expected(theta)[calibration_mask], counts[calibration_mask]
        )

    transient = (
        counts[calibration_mask]
        - background * widths[calibration_mask]
    ).sum().clamp_min(1.0)
    initial_amplitude = float(transient / kernel[calibration_mask].sum())
    optimizer = LevenbergMarquardt(
        residual,
        torch.tensor([math.log(initial_amplitude)], dtype=DTYPE),
    )
    theta = optimizer.optimize(max_iter=60, tolerance=1e-10)
    return float(torch.exp(theta[0])), expected(theta).detach()


def main(
    data_dir: Path = Path("data/aftershock_benchmark"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    sequences = [load_sequence(spec, edges, data_dir) for spec in SEQUENCES]

    folds = []
    for target_index, target in enumerate(sequences):
        training = [
            sequence
            for index, sequence in enumerate(sequences)
            if index != target_index
        ]
        shared_omori = fit_shared_shape(training, edges, "omori")
        shared_exponential = fit_shared_shape(training, edges, "exponential")
        omori_amplitude, omori_expected = calibrate_amplitude(
            target.counts,
            edges,
            calibration_mask,
            target.background,
            "omori",
            shared_omori.parameters,
        )
        exponential_amplitude, exponential_expected = calibrate_amplitude(
            target.counts,
            edges,
            calibration_mask,
            target.background,
            "exponential",
            shared_exponential.parameters,
        )
        local = fit_relaxation_model(
            "omori",
            edges,
            target.counts,
            calibration_mask,
            target.background,
        )

        observed_evaluation = target.counts[evaluation_mask]
        model_rows = {}
        for name, expected, parameters in (
            (
                "transferred_omori",
                omori_expected,
                {
                    "amplitude": omori_amplitude,
                    "c_days": shared_omori.parameters["c_days"],
                    "p": shared_omori.parameters["p"],
                },
            ),
            (
                "transferred_exponential",
                exponential_expected,
                {
                    "amplitude": exponential_amplitude,
                    "tau_days": shared_exponential.parameters["tau_days"],
                },
            ),
            ("target_day1_omori", local.expected_counts, local.parameters),
        ):
            predicted_evaluation = expected[evaluation_mask]
            model_rows[name] = {
                "parameters": parameters,
                "poisson_deviance": poisson_deviance(
                    predicted_evaluation, observed_evaluation
                ),
                "predicted_total": float(predicted_evaluation.sum()),
            }
        folds.append(
            {
                "target": target.spec.slug,
                "name": target.spec.name,
                "mainshock_magnitude": target.spec.magnitude,
                "calibration_events": int(target.counts[calibration_mask].sum()),
                "evaluation_events": int(observed_evaluation.sum()),
                "background_events_per_day": target.background,
                "models": model_rows,
            }
        )

    model_names = (
        "transferred_omori",
        "transferred_exponential",
        "target_day1_omori",
    )
    aggregate = {}
    total_evaluation_events = sum(fold["evaluation_events"] for fold in folds)
    for model in model_names:
        scores = [fold["models"][model]["poisson_deviance"] for fold in folds]
        aggregate[model] = {
            "total_poisson_deviance": sum(scores),
            "mean_sequence_deviance": sum(scores) / len(scores),
            "median_sequence_deviance": float(
                torch.tensor(scores, dtype=DTYPE).median()
            ),
            "deviance_per_evaluation_event": sum(scores)
            / total_evaluation_events,
            "sequence_wins": sum(
                score
                == min(
                    fold["models"][name]["poisson_deviance"]
                    for name in model_names
                )
                for score, fold in zip(scores, folds)
            ),
        }

    provenance = [
        {
            "slug": sequence.spec.slug,
            "name": sequence.spec.name,
            "event_id": sequence.spec.event_id,
            "mainshock_magnitude": sequence.spec.magnitude,
            "source_url": source_url(sequence.spec),
            "source_rows": sequence.source_rows,
            "sha256": sequence.sha256,
            "post_hour1_events": int(sequence.counts.sum()),
        }
        for sequence in sequences
    ]
    report = {
        "experiment": "leave-one-sequence-out aftershock law transfer",
        "prediction_semantics": (
            "shape learned from seven other sequences; target amplitude uses "
            "hour 1 through day 1; evaluation is day 1 through day 30"
        ),
        "catalog_rule": "M2.5+, 100 km, 30 days before and after mainshock",
        "provenance": provenance,
        "folds": folds,
        "aggregate": aggregate,
    }
    (output_dir / "aftershock_transfer_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    names = [fold["name"].rsplit(" ", 1)[0] for fold in folds]
    positions = torch.arange(len(folds), dtype=DTYPE)
    colors = {
        "transferred_omori": "#00b894",
        "transferred_exponential": "#e17055",
        "target_day1_omori": "#6c5ce7",
    }
    labels = {
        "transferred_omori": "transferred Omori",
        "transferred_exponential": "transferred exponential",
        "target_day1_omori": "target-only day-1 Omori",
    }
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)
    score_axis, total_axis, shape_axis, aggregate_axis = axes.ravel()

    width = 0.25
    for offset, model in zip((-width, 0.0, width), model_names):
        score_axis.bar(
            positions + offset,
            [fold["models"][model]["poisson_deviance"] for fold in folds],
            width=width,
            color=colors[model],
            label=labels[model],
        )
    score_axis.set_yscale("log")
    score_axis.set_xticks(positions, names)
    score_axis.set(
        title="Whole-sequence holdout deviance",
        ylabel="day 1-30 Poisson deviance (log scale)",
    )
    score_axis.tick_params(axis="x", labelsize=8, labelrotation=25)
    score_axis.legend(frameon=False, fontsize=8)
    score_axis.grid(alpha=0.2, axis="y")

    observed_totals = torch.tensor(
        [fold["evaluation_events"] for fold in folds], dtype=DTYPE
    )
    low = float(observed_totals.min()) * 0.7
    high = float(observed_totals.max()) * 1.4
    total_axis.plot([low, high], [low, high], "--", color="#636e72")
    for model in model_names:
        predicted = torch.tensor(
            [fold["models"][model]["predicted_total"] for fold in folds],
            dtype=DTYPE,
        )
        total_axis.scatter(
            observed_totals,
            predicted,
            s=45,
            color=colors[model],
            label=labels[model],
        )
    for index, fold in enumerate(folds):
        total_axis.annotate(
            fold["target"].split("_")[0],
            (float(observed_totals[index]), float(fold["models"]["transferred_omori"]["predicted_total"])),
            fontsize=7,
        )
    total_axis.set_xscale("log")
    total_axis.set_yscale("log")
    total_axis.set_xlim(low, high)
    total_axis.set_ylim(low, high)
    total_axis.set(
        title="Held-out event totals",
        xlabel="observed day 1-30",
        ylabel="predicted day 1-30",
    )
    total_axis.grid(alpha=0.2)

    transferred_p = [
        fold["models"]["transferred_omori"]["parameters"]["p"]
        for fold in folds
    ]
    transferred_c = [
        fold["models"]["transferred_omori"]["parameters"]["c_days"]
        for fold in folds
    ]
    shape_scatter = shape_axis.scatter(
        transferred_c,
        transferred_p,
        c=[fold["mainshock_magnitude"] for fold in folds],
        cmap="viridis",
        s=70,
    )
    for c_value, p_value, fold in zip(transferred_c, transferred_p, folds):
        shape_axis.annotate(
            fold["target"].split("_")[0],
            (c_value, p_value),
            fontsize=7,
        )
    shape_axis.set(
        title="Shape learned without target sequence",
        xlabel="shared c (days)",
        ylabel="shared p",
    )
    shape_axis.grid(alpha=0.2)
    fig.colorbar(shape_scatter, ax=shape_axis, label="held-out mainshock M")

    aggregate_values = [
        aggregate[model]["median_sequence_deviance"] for model in model_names
    ]
    aggregate_axis.bar(
        range(3),
        aggregate_values,
        color=[colors[model] for model in model_names],
    )
    aggregate_axis.set_xticks(
        range(3), ["transfer\nOmori", "transfer\nexponential", "target day-1\nOmori"]
    )
    aggregate_axis.set(
        title="Equal-sequence external-validation score",
        ylabel="median sequence Poisson deviance",
    )
    for index, model in enumerate(model_names):
        aggregate_axis.text(
            index,
            aggregate_values[index],
            f'{aggregate[model]["sequence_wins"]}/8 wins',
            ha="center",
            va="bottom",
            fontsize=8,
        )
    aggregate_axis.grid(alpha=0.2, axis="y")

    fig.suptitle(
        "KinoPulse aftershock benchmark - does a relaxation law transfer to a new earthquake?"
    )
    fig.savefig(output_dir / "aftershock_transfer_lab.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
