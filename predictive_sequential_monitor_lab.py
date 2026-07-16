"""Calibrate the external sequential monitor with hierarchy-predictive paths."""

from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from aftershock_hierarchy_lab import PopulationShape, robust_population
from aftershock_lab import DTYPE, _encode_p, fit_relaxation_model
from aftershock_meta_lab import load_population_manifest
from aftershock_transfer_lab import CALIBRATION_END_DAYS, load_sequence, make_transfer_bins
from external_sequential_monitor_lab import first_alarm_record
from poisson_regime_monitor import tail_scale_scan


DEVELOPMENT_DIR = Path("data/aftershock_population")
EXTERNAL_DIR = Path("data/aftershock_external/alaska_2010_2025")
FIXED_MONITOR_EVIDENCE = Path("artifacts/external_sequential_monitor.json")
FALSE_ALARM_RATE = 0.01
PROPOSAL_COUNT = 4096
CALIBRATION_SAMPLES = 8192
VALIDATION_SAMPLES = 4096


def population_predictive_expected(
    sequence,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    population: PopulationShape,
    generator: torch.Generator,
    proposal_count: int = PROPOSAL_COUNT,
) -> tuple[torch.Tensor, torch.Tensor, float]:
    """Condition population shape proposals on target first-day counts."""
    if proposal_count < 1:
        raise ValueError("proposal_count must be positive")
    proposed = (
        population.center[None, :]
        + population.scale[None, :]
        * torch.randn((proposal_count, 2), dtype=DTYPE, generator=generator)
    )
    proposed[:, 0].clamp_(math.log(1e-4), math.log(2.0))
    proposed[:, 1].clamp_(_encode_p(0.35), _encode_p(1.95))
    offset = torch.exp(proposed[:, 0])
    exponent = 0.3 + 1.7 * torch.sigmoid(proposed[:, 1])
    start, end = edges[:-1], edges[1:]
    log_start = torch.log(start[None, :] + offset[:, None])
    log_ratio = torch.log(
        (end[None, :] + offset[:, None]) / (start[None, :] + offset[:, None])
    )
    one_minus_p = 1.0 - exponent[:, None]
    value = one_minus_p * log_ratio
    safe = torch.where(value.abs() < 1e-7, torch.ones_like(value), value)
    exprel = torch.expm1(value) / safe
    series = 1.0 + value / 2.0 + value.square() / 6.0
    exprel = torch.where(value.abs() < 1e-5, series, exprel)
    kernel = torch.exp(one_minus_p * log_start) * log_ratio * exprel
    widths = torch.diff(edges)
    transient = (
        sequence.counts[calibration_mask]
        - sequence.background * widths[calibration_mask]
    ).sum().clamp_min(1.0)
    amplitude = transient / kernel[:, calibration_mask].sum(dim=1).clamp_min(1e-12)
    expected = amplitude[:, None] * kernel + sequence.background * widths[None, :]

    observed_calibration = sequence.counts[calibration_mask][None, :]
    expected_calibration = expected[:, calibration_mask].clamp_min(1e-12)
    log_term = torch.where(
        observed_calibration > 0,
        observed_calibration * torch.log(observed_calibration / expected_calibration),
        torch.zeros_like(expected_calibration),
    )
    calibration_deviance = 2.0 * (
        log_term - (observed_calibration - expected_calibration)
    ).sum(dim=1)
    log_weight = -0.5 * (calibration_deviance - calibration_deviance.min())
    weights = torch.softmax(log_weight, dim=0)
    effective_sample_size = float(1.0 / weights.square().sum())
    return expected, weights, effective_sample_size


def sample_population_predictive_counts(
    sequence,
    edges: torch.Tensor,
    calibration_mask: torch.Tensor,
    evaluation_mask: torch.Tensor,
    population: PopulationShape,
    sample_count: int,
    seed: int,
    proposal_count: int = PROPOSAL_COUNT,
) -> tuple[torch.Tensor, float]:
    """Draw complete future streams from the first-day-conditioned hierarchy."""
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    generator = torch.Generator().manual_seed(seed)
    expected, weights, effective_sample_size = population_predictive_expected(
        sequence,
        edges,
        calibration_mask,
        population,
        generator,
        proposal_count,
    )
    selected = torch.multinomial(
        weights, sample_count, replacement=True, generator=generator
    )
    counts = torch.poisson(
        expected[selected][:, evaluation_mask], generator=generator
    )
    return counts, effective_sample_size


def threshold_from_predictive_streams(
    counts: torch.Tensor,
    central_expected: torch.Tensor,
    false_alarm_rate: float = FALSE_ALARM_RATE,
) -> tuple[float, torch.Tensor, int]:
    """Calibrate the complete scan against already-sampled predictive paths."""
    if counts.ndim != 2 or counts.shape[1] != len(central_expected):
        raise ValueError("counts must be [samples, bins] matching central_expected")
    if not 0.0 < false_alarm_rate < 1.0:
        raise ValueError("false_alarm_rate must lie strictly between zero and one")
    statistics_trace, _ = tail_scale_scan(counts, central_expected)
    maxima = statistics_trace.max(dim=1).values.sort().values
    rank = math.ceil((len(maxima) + 1) * (1.0 - false_alarm_rate)) - 1
    rank = max(0, min(len(maxima) - 1, rank))
    return float(maxima[rank]), maxima, rank


def summarize(records: list[dict]) -> dict:
    fixed_alarm = [record for record in records if record["fixed_alarm"]]
    predictive_alarm = [record for record in records if record["predictive_alarm"]]
    both = [
        record
        for record in records
        if record["fixed_alarm"] and record["predictive_alarm"]
    ]
    raw_misses = [record for record in records if record["raw_interval_miss"]]
    raw_covered = [record for record in records if not record["raw_interval_miss"]]
    rolling = [record for record in records if record["rolling_interval_miss"] is not None]
    rolling_misses = [record for record in rolling if record["rolling_interval_miss"]]
    rolling_covered = [record for record in rolling if not record["rolling_interval_miss"]]
    rolling_alarms = [record for record in rolling if record["predictive_alarm"]]
    rolling_quiet = [record for record in rolling if not record["predictive_alarm"]]
    null_rates = [record["predictive_null_validation_rate"] for record in records]
    threshold_multipliers = [
        record["predictive_threshold"] / record["fixed_threshold"]
        for record in records
    ]
    return {
        "sequence_count": len(records),
        "fixed_alarm_count": len(fixed_alarm),
        "predictive_alarm_count": len(predictive_alarm),
        "both_alarm_count": len(both),
        "fixed_only_alarm_count": sum(
            record["fixed_alarm"] and not record["predictive_alarm"]
            for record in records
        ),
        "predictive_only_alarm_count": sum(
            record["predictive_alarm"] and not record["fixed_alarm"]
            for record in records
        ),
        "predictive_alarm_fraction": len(predictive_alarm) / len(records),
        "raw_misses_alarmed": sum(record["predictive_alarm"] for record in raw_misses),
        "raw_miss_count": len(raw_misses),
        "raw_covered_alarmed": sum(
            record["predictive_alarm"] for record in raw_covered
        ),
        "raw_covered_count": len(raw_covered),
        "predictive_alarm_precision_for_raw_miss": (
            sum(record["raw_interval_miss"] for record in predictive_alarm)
            / len(predictive_alarm)
            if predictive_alarm
            else None
        ),
        "rolling_interval_association": {
            "eligible": len(rolling),
            "miss_count": len(rolling_misses),
            "covered_count": len(rolling_covered),
            "alarmed": len(rolling_alarms),
            "misses_alarmed": sum(
                record["predictive_alarm"] for record in rolling_misses
            ),
            "covered_alarmed": sum(
                record["predictive_alarm"] for record in rolling_covered
            ),
            "alarm_precision": (
                sum(record["rolling_interval_miss"] for record in rolling_alarms)
                / len(rolling_alarms)
                if rolling_alarms
                else None
            ),
            "miss_sensitivity": (
                sum(record["predictive_alarm"] for record in rolling_misses)
                / len(rolling_misses)
                if rolling_misses
                else None
            ),
            "quiet_coverage": (
                sum(not record["rolling_interval_miss"] for record in rolling_quiet)
                / len(rolling_quiet)
                if rolling_quiet
                else None
            ),
        },
        "median_first_predictive_alarm_day": (
            statistics.median(record["predictive_first_alarm_day"] for record in predictive_alarm)
            if predictive_alarm
            else None
        ),
        "median_threshold_multiplier": statistics.median(threshold_multipliers),
        "minimum_threshold_multiplier": min(threshold_multipliers),
        "maximum_threshold_multiplier": max(threshold_multipliers),
        "mean_predictive_null_validation_rate": statistics.mean(null_rates),
        "minimum_predictive_null_validation_rate": min(null_rates),
        "maximum_predictive_null_validation_rate": max(null_rates),
        "median_proposal_effective_sample_size": statistics.median(
            record["calibration_proposal_effective_sample_size"] for record in records
        ),
    }


def run_predictive_monitor_calibration(
    development_dir: Path = DEVELOPMENT_DIR,
    external_dir: Path = EXTERNAL_DIR,
    fixed_evidence_path: Path = FIXED_MONITOR_EVIDENCE,
) -> dict:
    fixed = json.loads(fixed_evidence_path.read_text(encoding="utf-8"))
    fixed_by_id = {record["event_id"]: record for record in fixed["records"]}
    edges = make_transfer_bins()
    calibration_mask = edges[1:] <= CALIBRATION_END_DAYS
    evaluation_mask = edges[:-1] >= CALIBRATION_END_DAYS
    evaluation_starts = edges[:-1][evaluation_mask]
    evaluation_ends = edges[1:][evaluation_mask]
    all_mask = torch.ones(len(edges) - 1, dtype=torch.bool)

    development_specs, _ = load_population_manifest(development_dir / "manifest.json")
    development_sequences = [
        load_sequence(spec, edges, development_dir) for spec in development_specs
    ]
    development_fits = [
        fit_relaxation_model("omori", edges, sequence.counts, all_mask, sequence.background)
        for sequence in development_sequences
    ]
    population = robust_population(development_fits, list(range(len(development_fits))))

    external_specs, _ = load_population_manifest(external_dir / "manifest.json")
    external_sequences = [
        load_sequence(spec, edges, external_dir) for spec in external_specs
    ]
    records = []
    for index, sequence in enumerate(external_sequences):
        fixed_record = fixed_by_id[sequence.spec.event_id]
        central_expected = torch.tensor(fixed_record["expected_counts"], dtype=DTYPE)
        observed = torch.tensor(fixed_record["observed_counts"], dtype=DTYPE)
        calibration_seed = 20260728 + index
        validation_seed = 20261728 + index
        calibration_counts, calibration_ess = sample_population_predictive_counts(
            sequence,
            edges,
            calibration_mask,
            evaluation_mask,
            population,
            CALIBRATION_SAMPLES,
            calibration_seed,
        )
        threshold, calibration_maxima, rank = threshold_from_predictive_streams(
            calibration_counts, central_expected
        )
        validation_counts, validation_ess = sample_population_predictive_counts(
            sequence,
            edges,
            calibration_mask,
            evaluation_mask,
            population,
            VALIDATION_SAMPLES,
            validation_seed,
        )
        validation_statistics, _ = tail_scale_scan(validation_counts, central_expected)
        validation_maxima = validation_statistics.max(dim=1).values
        validation_rate = float((validation_maxima > threshold).to(DTYPE).mean())
        predictive_monitor = first_alarm_record(
            observed,
            central_expected,
            threshold,
            evaluation_starts,
            evaluation_ends,
        )
        records.append(
            {
                "event_id": sequence.spec.event_id,
                "name": sequence.spec.name,
                "time": fixed_record["time"],
                "raw_interval_miss": fixed_record["raw_interval_miss"],
                "rolling_interval_miss": fixed_record["rolling_interval_miss"],
                "fixed_threshold": fixed_record["threshold"],
                "fixed_alarm": fixed_record["first_alarm_bin"] is not None,
                "fixed_first_alarm_day": fixed_record["first_alarm_day"],
                "predictive_threshold": threshold,
                "predictive_threshold_rank": rank,
                "predictive_alarm": predictive_monitor["first_alarm_bin"] is not None,
                "predictive_first_alarm_day": predictive_monitor["first_alarm_day"],
                "predictive_direction": predictive_monitor["direction"],
                "predictive_rate_multiplier_at_alarm": predictive_monitor[
                    "rate_multiplier_at_alarm"
                ],
                "observed_maximum_statistic": predictive_monitor["maximum_statistic"],
                "observed_maximum_predictive_threshold_ratio": predictive_monitor[
                    "maximum_threshold_ratio"
                ],
                "calibration_seed": calibration_seed,
                "validation_seed": validation_seed,
                "calibration_proposal_effective_sample_size": calibration_ess,
                "validation_proposal_effective_sample_size": validation_ess,
                "calibration_maximum_p99": float(torch.quantile(calibration_maxima, 0.99)),
                "predictive_null_validation_rate": validation_rate,
            }
        )
    return {
        "experiment": "hierarchy-predictive sequential monitor calibration",
        "claim_boundary": (
            "post-hoc external null-model repair; sampler propagates empirical "
            "population shape and Poisson uncertainty, but not all process uncertainty"
        ),
        "false_alarm_rate": FALSE_ALARM_RATE,
        "proposal_count": PROPOSAL_COUNT,
        "calibration_samples_per_sequence": CALIBRATION_SAMPLES,
        "validation_samples_per_sequence": VALIDATION_SAMPLES,
        "summary": summarize(records),
        "records": records,
    }


def plot_predictive_monitor(report: dict, output_path: Path) -> None:
    records = report["records"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 9), constrained_layout=True)
    fig.patch.set_facecolor("white")
    threshold_axis, count_axis, outcome_axis, validation_axis = axes.ravel()

    fixed = [record["fixed_threshold"] for record in records]
    predictive = [record["predictive_threshold"] for record in records]
    threshold_axis.scatter(fixed, predictive, color="#6c5ce7", alpha=0.8)
    lower = min(fixed + predictive)
    upper = max(fixed + predictive)
    threshold_axis.plot([lower, upper], [lower, upper], "--", color="#2d3436")
    threshold_axis.set_xscale("log")
    threshold_axis.set_yscale("log")
    threshold_axis.set(
        title="Predictive uncertainty raises scan thresholds",
        xlabel="fixed-Poisson threshold",
        ylabel="hierarchy-predictive threshold",
    )
    threshold_axis.grid(alpha=0.2, which="both")

    fixed_alarm = sum(record["fixed_alarm"] for record in records)
    predictive_alarm = sum(record["predictive_alarm"] for record in records)
    count_axis.bar(
        (0, 1),
        (fixed_alarm, predictive_alarm),
        color=["#d63031", "#6c5ce7"],
    )
    count_axis.set_xticks((0, 1), ("fixed Poisson", "predictive hierarchy"))
    count_axis.set(title="Real external alarms", ylabel="sequences")
    count_axis.grid(axis="y", alpha=0.2)

    groups = (
        [record for record in records if record["raw_interval_miss"]],
        [record for record in records if not record["raw_interval_miss"]],
    )
    alarmed = [sum(record["predictive_alarm"] for record in group) for group in groups]
    quiet = [len(group) - count for group, count in zip(groups, alarmed)]
    outcome_axis.bar((0, 1), alarmed, color="#6c5ce7", label="predictive alarm")
    outcome_axis.bar((0, 1), quiet, bottom=alarmed, color="#b2bec3", label="quiet")
    outcome_axis.set_xticks((0, 1), ("raw interval\nmiss", "raw interval\ncovered"))
    outcome_axis.set(title="Predictive-null alarm outcomes", ylabel="sequences")
    outcome_axis.legend(frameon=False)
    outcome_axis.grid(axis="y", alpha=0.2)

    rates = [record["predictive_null_validation_rate"] for record in records]
    validation_axis.scatter(range(len(rates)), rates, color="#00b894")
    validation_axis.axhline(FALSE_ALARM_RATE, color="#2d3436", linestyle="--")
    validation_axis.set(
        title="Independent predictive-null validation",
        xlabel="external target",
        ylabel="probability of any alarm",
    )
    validation_axis.grid(alpha=0.2)

    fig.suptitle("A broader hierarchy-predictive null for sequential monitoring")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report = run_predictive_monitor_calibration()
    (output_dir / "predictive_sequential_monitor.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    plot_predictive_monitor(report, output_dir / "predictive_sequential_monitor.png")
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    main()
