"""Reusable sequential Poisson tail-regime monitoring and calibration."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import NamedTuple

import torch


DEFAULT_MIN_PRECHANGE_BINS = 3
DEFAULT_MIN_POSTCHANGE_BINS = 3


class MonitorOutput(NamedTuple):
    statistic: torch.Tensor
    split_index: torch.Tensor
    rate_multiplier: torch.Tensor
    direction: torch.Tensor
    alarm: torch.Tensor


@dataclass(frozen=True)
class CalibrationResult:
    threshold: float
    false_alarm_rate: float
    sample_count: int
    seed: int
    horizon_bins: int
    min_prechange_bins: int
    min_postchange_bins: int
    order_statistic_rank: int


class SequentialPoissonRegimeMonitor(torch.nn.Module):
    """TorchScript-compatible scan at the current end of a count prefix.

    The caller supplies the observed prefix, the forecast expected-count prefix,
    and a threshold calibrated for the complete intended monitoring procedure.
    Direction is -1 for lower rate, 0 before the monitor is ready, and +1 for
    higher rate.
    """

    def __init__(
        self,
        min_prechange: int = DEFAULT_MIN_PRECHANGE_BINS,
        min_postchange: int = DEFAULT_MIN_POSTCHANGE_BINS,
    ) -> None:
        super().__init__()
        if min_prechange < 1 or min_postchange < 1:
            raise ValueError("minimum segment lengths must be positive")
        self.min_prechange = min_prechange
        self.min_postchange = min_postchange

    def forward(
        self,
        observed: torch.Tensor,
        expected: torch.Tensor,
        threshold: torch.Tensor,
    ) -> MonitorOutput:
        if observed.dim() != 1 or expected.dim() != 1:
            raise RuntimeError("observed and expected must be one-dimensional")
        if observed.numel() != expected.numel():
            raise RuntimeError("observed and expected must have equal lengths")
        if threshold.numel() != 1:
            raise RuntimeError("threshold must contain exactly one value")
        if bool(torch.sum((observed < 0.0).to(dtype=torch.long)) > 0):
            raise RuntimeError("observed counts must be non-negative")
        if bool(torch.sum((expected <= 0.0).to(dtype=torch.long)) > 0):
            raise RuntimeError("expected counts must be strictly positive")
        if not bool(torch.isfinite(threshold).all()) or bool(threshold <= 0.0):
            raise RuntimeError("threshold must be finite and positive")

        bin_count = observed.numel()
        zero = torch.zeros((), dtype=expected.dtype, device=expected.device)
        minus_one = torch.tensor(-1, dtype=torch.long, device=expected.device)
        one = torch.ones((), dtype=expected.dtype, device=expected.device)
        no_direction = torch.zeros((), dtype=torch.long, device=expected.device)
        no_alarm = torch.zeros((), dtype=torch.long, device=expected.device)
        if bin_count < self.min_prechange + self.min_postchange:
            return MonitorOutput(zero, minus_one, one, no_direction, no_alarm)

        best_statistic = zero
        best_split = minus_one
        best_multiplier = one
        final_split = bin_count - self.min_postchange
        for split in range(self.min_prechange, final_split + 1):
            tail_count = torch.sum(observed[split:bin_count])
            tail_expected = torch.sum(expected[split:bin_count])
            if bool(tail_count > 0.0):
                log_term = tail_count * torch.log(tail_count / tail_expected)
            else:
                log_term = zero
            statistic = 2.0 * (
                log_term - (tail_count - tail_expected)
            )
            if bool(statistic > best_statistic):
                best_statistic = statistic
                best_split = torch.tensor(
                    split, dtype=torch.long, device=expected.device
                )
                best_multiplier = tail_count / tail_expected

        direction = torch.sign(best_multiplier - 1.0).to(dtype=torch.long)
        alarm = (best_statistic > threshold.reshape(())).to(dtype=torch.long)
        return MonitorOutput(
            best_statistic,
            best_split,
            best_multiplier,
            direction,
            alarm,
        )


def tail_scale_scan(
    counts: torch.Tensor,
    expected: torch.Tensor,
    min_prechange: int = DEFAULT_MIN_PRECHANGE_BINS,
    min_postchange: int = DEFAULT_MIN_POSTCHANGE_BINS,
) -> tuple[torch.Tensor, torch.Tensor]:
    """Evaluate the monitor statistic at every prefix, optionally in batches."""
    squeeze = counts.ndim == 1
    if squeeze:
        counts = counts[None, :]
    if counts.ndim != 2 or expected.ndim != 1:
        raise ValueError("counts must be [samples, bins] and expected must be [bins]")
    if counts.shape[1] != len(expected):
        raise ValueError("counts and expected must contain the same number of bins")
    if min_prechange < 1 or min_postchange < 1:
        raise ValueError("minimum segment lengths must be positive")
    batch, bin_count = counts.shape
    cumulative_counts = torch.cat(
        (torch.zeros((batch, 1), dtype=counts.dtype), counts.cumsum(dim=1)),
        dim=1,
    )
    cumulative_expected = torch.cat(
        (torch.zeros(1, dtype=expected.dtype), expected.cumsum(dim=0))
    )
    statistics = torch.zeros_like(counts)
    split_indices = torch.full(
        counts.shape, -1, dtype=torch.long, device=counts.device
    )
    for end in range(min_prechange + min_postchange, bin_count + 1):
        candidates = []
        for split in range(min_prechange, end - min_postchange + 1):
            tail_count = cumulative_counts[:, end] - cumulative_counts[:, split]
            tail_expected = cumulative_expected[end] - cumulative_expected[split]
            log_term = torch.where(
                tail_count > 0,
                tail_count * torch.log(tail_count / tail_expected),
                torch.zeros_like(tail_count),
            )
            candidates.append(2.0 * (log_term - (tail_count - tail_expected)))
        candidate_statistics = torch.stack(candidates, dim=1)
        statistics[:, end - 1], best = candidate_statistics.max(dim=1)
        split_indices[:, end - 1] = best + min_prechange
    if squeeze:
        return statistics[0], split_indices[0]
    return statistics, split_indices


def monte_carlo_threshold(
    expected: torch.Tensor,
    false_alarm_rate: float,
    sample_count: int,
    generator: torch.Generator,
    min_prechange: int = DEFAULT_MIN_PRECHANGE_BINS,
    min_postchange: int = DEFAULT_MIN_POSTCHANGE_BINS,
) -> tuple[float, torch.Tensor]:
    if not 0.0 < false_alarm_rate < 1.0:
        raise ValueError("false_alarm_rate must be strictly between zero and one")
    if sample_count < 1:
        raise ValueError("sample_count must be positive")
    simulated = torch.poisson(
        expected.expand(sample_count, -1), generator=generator
    )
    statistics, _ = tail_scale_scan(
        simulated, expected, min_prechange, min_postchange
    )
    maxima = statistics.max(dim=1).values.sort().values
    rank = math.ceil((sample_count + 1) * (1.0 - false_alarm_rate)) - 1
    rank = max(0, min(sample_count - 1, rank))
    return float(maxima[rank]), maxima


def calibrate_poisson_monitor(
    expected: torch.Tensor,
    false_alarm_rate: float = 0.01,
    sample_count: int = 8192,
    seed: int = 20260717,
    min_prechange: int = DEFAULT_MIN_PRECHANGE_BINS,
    min_postchange: int = DEFAULT_MIN_POSTCHANGE_BINS,
) -> CalibrationResult:
    generator = torch.Generator(device=expected.device).manual_seed(seed)
    threshold, _ = monte_carlo_threshold(
        expected,
        false_alarm_rate,
        sample_count,
        generator,
        min_prechange,
        min_postchange,
    )
    rank = math.ceil((sample_count + 1) * (1.0 - false_alarm_rate)) - 1
    rank = max(0, min(sample_count - 1, rank))
    return CalibrationResult(
        threshold=threshold,
        false_alarm_rate=false_alarm_rate,
        sample_count=sample_count,
        seed=seed,
        horizon_bins=len(expected),
        min_prechange_bins=min_prechange,
        min_postchange_bins=min_postchange,
        order_statistic_rank=rank,
    )
