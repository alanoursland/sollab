"""Model a fixed pull-request cohort as a causal marked event process."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import matplotlib.pyplot as plt
import numpy as np
import torch

from kinopulse.stochastic import MarkedEventHistory, MultitypeTemporalPointProcess


TYPE_RESPONSE = 0
TYPE_MERGE = 1
TYPE_CLOSE = 2
TYPE_NAMES = ("maintainer_response", "merge", "unmerged_close")
MAINTAINER_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
EXTERNAL_ASSOCIATIONS = {"NONE", "CONTRIBUTOR", "FIRST_TIMER", "FIRST_TIME_CONTRIBUTOR"}
DAY_SECONDS = 86_400.0
EPSILON_DAYS = 1e-9
AGE_BIN_STARTS = (0.0, 1.0, 7.0, 30.0, 180.0)


@dataclass(frozen=True)
class PullRequestSequence:
    repository: str
    number: int
    author_origin: str
    duration_days: float
    event_times: tuple[float, ...]
    event_types: tuple[int, ...]
    terminal_type: int | None
    response_time_days: float | None

    @property
    def terminal_observed(self) -> bool:
        return self.terminal_type is not None

    @property
    def response_observed(self) -> bool:
        return self.response_time_days is not None


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def days_between(left: datetime, right: datetime) -> float:
    return (right - left).total_seconds() / DAY_SECONDS


def author_origin(association: str | None, login: str | None = None) -> str:
    if login and login.lower().endswith("[bot]"):
        return "automation"
    return "maintainer" if association in MAINTAINER_ASSOCIATIONS else "external"


def first_maintainer_response(pull: dict, created: datetime, stop: datetime) -> datetime | None:
    author = pull.get("author_login")
    candidates: list[datetime] = []
    for event in pull.get("issue_comment_events", []):
        when = parse_time(event["created_at"])
        if (
            event.get("author_association") in MAINTAINER_ASSOCIATIONS
            and event.get("author_login") != author
            and created <= when < stop
        ):
            candidates.append(when)
    for review in pull.get("reviews", []):
        when = parse_time(review["submitted_at"])
        if (
            review.get("author_association") in MAINTAINER_ASSOCIATIONS
            and review.get("reviewer_login") != author
            and created <= when < stop
        ):
            candidates.append(when)
    return min(candidates) if candidates else None


def build_sequence(repository: str, pull: dict, cutoff: datetime) -> PullRequestSequence:
    created = parse_time(pull["created_at"])
    merged = parse_time(pull["merged_at"]) if pull.get("merged_at") else None
    closed = parse_time(pull["closed_at"]) if pull.get("closed_at") else None

    terminal_time = None
    terminal_type = None
    if merged is not None and merged <= cutoff:
        terminal_time, terminal_type = merged, TYPE_MERGE
    elif closed is not None and closed <= cutoff:
        terminal_time, terminal_type = closed, TYPE_CLOSE
    stop = terminal_time or cutoff
    if stop <= created:
        raise ValueError(f"PR #{pull['number']} has a nonpositive observation interval")

    response = first_maintainer_response(pull, created, stop)
    timed_events: list[tuple[float, int]] = []
    if response is not None:
        timed_events.append((days_between(created, response), TYPE_RESPONSE))
    if terminal_time is not None:
        timed_events.append((days_between(created, terminal_time), terminal_type))
    timed_events.sort(key=lambda value: (value[0], value[1]))

    return PullRequestSequence(
        repository=repository,
        number=int(pull["number"]),
        author_origin=author_origin(pull.get("author_association"), pull.get("author_login")),
        duration_days=days_between(created, stop),
        event_times=tuple(value[0] for value in timed_events),
        event_types=tuple(value[1] for value in timed_events),
        terminal_type=terminal_type,
        response_time_days=None if response is None else days_between(created, response),
    )


def load_sequences(path: Path) -> tuple[list[PullRequestSequence], dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cutoff = parse_time(payload["observation_end"])
    sequences = [
        build_sequence(repository["name"], pull, cutoff)
        for repository in payload["repositories"]
        for pull in repository["pull_requests"]
    ]
    return sequences, payload


def active_rates(history: MarkedEventHistory, rates: torch.Tensor) -> torch.Tensor:
    marks = history.marks
    if bool(torch.any((marks == TYPE_MERGE) | (marks == TYPE_CLOSE))):
        return torch.zeros_like(rates)
    if bool(torch.any(marks == TYPE_RESPONSE)):
        return torch.cat((torch.zeros_like(rates[..., :1]), rates[..., 1:]), dim=-1)
    return rates


def make_process() -> MultitypeTemporalPointProcess:
    def intensity(times, history, params):
        rates = active_rates(history, params)
        return rates.expand(*times.shape, len(TYPE_NAMES))

    def integrated(times, history, params):
        rates = active_rates(history, params)
        return times.unsqueeze(-1) * rates

    return MultitypeTemporalPointProcess(
        intensity,
        num_types=len(TYPE_NAMES),
        integrated_intensity=integrated,
        type_names=TYPE_NAMES,
    )


def make_piecewise_process(bin_starts: tuple[float, ...] = AGE_BIN_STARTS) -> MultitypeTemporalPointProcess:
    starts = torch.tensor(bin_starts, dtype=torch.float64)

    def intensity(times, history, params):
        local_starts = starts.to(dtype=times.dtype, device=times.device)
        indices = torch.bucketize(times, local_starts[1:], right=True)
        rates = active_rates(history, params)
        return rates[indices]

    def integrated(times, history, params):
        local_starts = starts.to(dtype=times.dtype, device=times.device)
        overlap = torch.clamp(times.unsqueeze(-1) - local_starts, min=0.0)
        if len(bin_starts) > 1:
            widths = local_starts[1:] - local_starts[:-1]
            overlap[..., :-1] = torch.minimum(overlap[..., :-1], widths)
        rates = active_rates(history, params)
        return overlap @ rates

    return MultitypeTemporalPointProcess(
        intensity,
        num_types=len(TYPE_NAMES),
        integrated_intensity=integrated,
        type_names=TYPE_NAMES,
    )


def sufficient_statistics(sequences: list[PullRequestSequence]) -> tuple[np.ndarray, np.ndarray]:
    counts = np.zeros(len(TYPE_NAMES), dtype=float)
    exposure = np.zeros(len(TYPE_NAMES), dtype=float)
    for sequence in sequences:
        exposure[TYPE_RESPONSE] += (
            sequence.response_time_days
            if sequence.response_time_days is not None
            else sequence.duration_days
        )
        exposure[TYPE_MERGE] += sequence.duration_days
        exposure[TYPE_CLOSE] += sequence.duration_days
        for event_type in sequence.event_types:
            counts[event_type] += 1
    return counts, exposure


def maximum_likelihood_rates(sequences: list[PullRequestSequence]) -> np.ndarray:
    counts, exposure = sufficient_statistics(sequences)
    return np.divide(counts, exposure, out=np.zeros_like(counts), where=exposure > 0)


def interval_exposure(horizon: float, bin_starts: tuple[float, ...]) -> np.ndarray:
    starts = np.asarray(bin_starts, dtype=float)
    exposure = np.maximum(horizon - starts, 0.0)
    if len(starts) > 1:
        exposure[:-1] = np.minimum(exposure[:-1], np.diff(starts))
    return exposure


def piecewise_statistics(
    sequences: list[PullRequestSequence], bin_starts: tuple[float, ...] = AGE_BIN_STARTS
) -> tuple[np.ndarray, np.ndarray]:
    counts = np.zeros((len(bin_starts), len(TYPE_NAMES)), dtype=float)
    exposure = np.zeros_like(counts)
    for sequence in sequences:
        response_horizon = (
            sequence.response_time_days
            if sequence.response_time_days is not None
            else sequence.duration_days
        )
        exposure[:, TYPE_RESPONSE] += interval_exposure(response_horizon, bin_starts)
        terminal_exposure = interval_exposure(sequence.duration_days, bin_starts)
        exposure[:, TYPE_MERGE] += terminal_exposure
        exposure[:, TYPE_CLOSE] += terminal_exposure
        for event_time, event_type in zip(sequence.event_times, sequence.event_types):
            bin_index = int(np.searchsorted(bin_starts[1:], event_time, side="right"))
            counts[bin_index, event_type] += 1
    return counts, exposure


def piecewise_maximum_likelihood_rates(
    sequences: list[PullRequestSequence], bin_starts: tuple[float, ...] = AGE_BIN_STARTS
) -> np.ndarray:
    counts, exposure = piecewise_statistics(sequences, bin_starts)
    return np.divide(counts, exposure, out=np.zeros_like(counts), where=exposure > 0)


def sequence_log_likelihood(
    process: MultitypeTemporalPointProcess,
    sequence: PullRequestSequence,
    rates: np.ndarray,
) -> float:
    times = torch.tensor(sequence.event_times, dtype=torch.float64)
    types = torch.tensor(sequence.event_types, dtype=torch.long)
    end = sequence.duration_days + (EPSILON_DAYS if sequence.terminal_observed else 0.0)
    result = process.log_likelihood(
        times,
        types,
        end=end,
        params=torch.tensor(rates, dtype=torch.float64),
    )
    return float(result.log_likelihood)


def piecewise_sequence_log_likelihood(
    process: MultitypeTemporalPointProcess,
    sequence: PullRequestSequence,
    rates: np.ndarray,
) -> float:
    times = torch.tensor(sequence.event_times, dtype=torch.float64)
    types = torch.tensor(sequence.event_types, dtype=torch.long)
    end = sequence.duration_days + (EPSILON_DAYS if sequence.terminal_observed else 0.0)
    result = process.log_likelihood(
        times,
        types,
        end=end,
        params=torch.tensor(rates, dtype=torch.float64),
    )
    return float(result.log_likelihood)


def group_key_function(name: str) -> Callable[[PullRequestSequence], str]:
    functions = {
        "pooled": lambda sequence: "all",
        "repository": lambda sequence: sequence.repository,
        "author_origin": lambda sequence: sequence.author_origin,
        "repository_origin": lambda sequence: f"{sequence.repository}:{sequence.author_origin}",
    }
    return functions[name]


def grouped_fit(
    sequences: list[PullRequestSequence], key_function: Callable[[PullRequestSequence], str]
) -> dict[str, dict]:
    groups: dict[str, list[PullRequestSequence]] = {}
    for sequence in sequences:
        groups.setdefault(key_function(sequence), []).append(sequence)
    fitted = {}
    process = make_process()
    for key, values in sorted(groups.items()):
        counts, exposure = sufficient_statistics(values)
        rates = maximum_likelihood_rates(values)
        likelihood = sum(sequence_log_likelihood(process, value, rates) for value in values)
        fitted[key] = {
            "sample_size": len(values),
            "counts": counts.astype(int).tolist(),
            "exposure_days": exposure.tolist(),
            "rates_per_day": rates.tolist(),
            "log_likelihood": likelihood,
        }
    return fitted


def leave_one_out_scores(
    sequences: list[PullRequestSequence], *, shrinkage_days: float = 180.0
) -> dict[str, float]:
    process = make_process()
    scores = {}
    for model_name in ("pooled", "repository", "author_origin", "repository_origin"):
        key_function = group_key_function(model_name)
        total = 0.0
        for index, holdout in enumerate(sequences):
            training = [
                sequence for peer_index, sequence in enumerate(sequences) if peer_index != index
            ]
            peers = [
                sequence
                for sequence in training
                if key_function(sequence) == key_function(holdout)
            ]
            global_counts, global_exposure = sufficient_statistics(training)
            global_rates = (global_counts + 0.5) / (global_exposure + 1.0)
            counts, exposure = sufficient_statistics(peers)
            rates = (counts + shrinkage_days * global_rates) / (exposure + shrinkage_days)
            total += sequence_log_likelihood(process, holdout, rates)
        scores[model_name] = total
    return scores


def leave_one_out_time_model_scores(
    sequences: list[PullRequestSequence], *, shrinkage_days: float = 180.0
) -> dict[str, float]:
    model_specs = {
        "homogeneous_pooled": ("pooled", False),
        "homogeneous_repository_origin": ("repository_origin", False),
        "piecewise_pooled": ("pooled", True),
        "piecewise_repository": ("repository", True),
        "piecewise_repository_origin": ("repository_origin", True),
    }
    scores = {}
    for model_name, (group_name, piecewise) in model_specs.items():
        key_function = group_key_function(group_name)
        process = make_piecewise_process() if piecewise else make_process()
        total = 0.0
        for index, holdout in enumerate(sequences):
            training = [
                sequence for peer_index, sequence in enumerate(sequences) if peer_index != index
            ]
            peers = [
                sequence for sequence in training if key_function(sequence) == key_function(holdout)
            ]
            if piecewise:
                global_counts, global_exposure = piecewise_statistics(training)
                counts, exposure = piecewise_statistics(peers)
                pooled_type_rates = (
                    global_counts.sum(axis=0) + 0.5
                ) / (global_exposure.sum(axis=0) + 1.0)
                rates = (counts + shrinkage_days * pooled_type_rates) / (
                    exposure + shrinkage_days
                )
                total += piecewise_sequence_log_likelihood(process, holdout, rates)
            else:
                global_counts, global_exposure = sufficient_statistics(training)
                counts, exposure = sufficient_statistics(peers)
                pooled_type_rates = (global_counts + 0.5) / (global_exposure + 1.0)
                rates = (counts + shrinkage_days * pooled_type_rates) / (
                    exposure + shrinkage_days
                )
                total += sequence_log_likelihood(process, holdout, rates)
        scores[model_name] = total
    return scores


def kaplan_meier(sequences: list[PullRequestSequence]) -> tuple[np.ndarray, np.ndarray]:
    times = np.array([sequence.duration_days for sequence in sequences], dtype=float)
    observed = np.array([sequence.terminal_observed for sequence in sequences], dtype=bool)
    survival = 1.0
    curve_times = [0.0]
    curve_values = [1.0]
    for time in sorted(set(times)):
        at_risk = int(np.sum(times >= time))
        events = int(np.sum((times == time) & observed))
        if events:
            survival *= 1.0 - events / at_risk
            curve_times.append(float(time))
            curve_values.append(survival)
    return np.asarray(curve_times), np.asarray(curve_values)


def survival_at(curve_times: np.ndarray, curve_values: np.ndarray, horizon: float) -> float:
    locations = np.flatnonzero(curve_times <= horizon)
    return float(curve_values[locations[-1]]) if len(locations) else 1.0


def evaluate_panel(sequences: list[PullRequestSequence], source: dict) -> dict:
    process = make_process()
    pooled_rates = maximum_likelihood_rates(sequences)
    pooled_counts, pooled_exposure = sufficient_statistics(sequences)

    # A direct oracle catches accidental violations of the one-shot/absorbing history contract.
    package_likelihood = sum(
        sequence_log_likelihood(process, sequence, pooled_rates) for sequence in sequences
    )
    positive = pooled_rates > 0
    analytic_likelihood = float(
        np.sum(pooled_counts[positive] * np.log(pooled_rates[positive]))
        - np.sum(pooled_rates * pooled_exposure)
    )
    if not math.isclose(package_likelihood, analytic_likelihood, abs_tol=1e-8):
        raise AssertionError("KinoPulse likelihood disagrees with the analytical oracle")

    curve_times, curve_values = kaplan_meier(sequences)
    terminal_rate = float(pooled_rates[TYPE_MERGE] + pooled_rates[TYPE_CLOSE])
    horizons = (1.0, 7.0, 30.0, 180.0, 365.0)
    survival = [
        {
            "days": horizon,
            "kaplan_meier": survival_at(curve_times, curve_values, horizon),
            "homogeneous_model": math.exp(-terminal_rate * horizon),
        }
        for horizon in horizons
    ]

    repository_summaries = {}
    for repository in sorted({sequence.repository for sequence in sequences}):
        values = [sequence for sequence in sequences if sequence.repository == repository]
        rates = maximum_likelihood_rates(values)
        observed_zero = np.mean([not sequence.response_observed for sequence in values])
        expected_zero = np.mean(
            [math.exp(-rates[TYPE_RESPONSE] * sequence.duration_days) for sequence in values]
        )
        repository_summaries[repository] = {
            "sample_size": len(values),
            "merged": sum(sequence.terminal_type == TYPE_MERGE for sequence in values),
            "unmerged_closed": sum(sequence.terminal_type == TYPE_CLOSE for sequence in values),
            "right_censored": sum(sequence.terminal_type is None for sequence in values),
            "maintainer_responses": sum(sequence.response_observed for sequence in values),
            "observed_zero_response_fraction": float(observed_zero),
            "model_zero_response_fraction_at_observed_durations": float(expected_zero),
            "rates_per_day": dict(zip(TYPE_NAMES, rates.tolist())),
        }

    loo = {
        str(days): leave_one_out_scores(sequences, shrinkage_days=days)
        for days in (30.0, 180.0, 365.0)
    }
    time_model_loo = {
        str(days): leave_one_out_time_model_scores(sequences, shrinkage_days=days)
        for days in (30.0, 180.0, 365.0)
    }
    piecewise_rates = piecewise_maximum_likelihood_rates(sequences)
    piecewise_process = make_piecewise_process()
    piecewise_likelihood = sum(
        piecewise_sequence_log_likelihood(piecewise_process, sequence, piecewise_rates)
        for sequence in sequences
    )
    return {
        "schema_version": 1,
        "source": {
            "retrieved_at_utc": source["retrieved_at_utc"],
            "created_window": source["created_window"],
            "observation_end": source["observation_end"],
            "selection_rule": source["selection_rule"],
        },
        "event_contract": {
            "type_names": TYPE_NAMES,
            "maintainer_response": "first nonauthor OWNER/MEMBER/COLLABORATOR issue comment or formal review before terminal/censoring",
            "terminal_marks": ["merge", "unmerged_close"],
            "history_semantics": "response intensity becomes zero after response; every intensity becomes zero after a terminal mark",
        },
        "sample_size": len(sequences),
        "pooled": {
            "counts": dict(zip(TYPE_NAMES, pooled_counts.astype(int).tolist())),
            "exposure_days": dict(zip(TYPE_NAMES, pooled_exposure.tolist())),
            "rates_per_day": dict(zip(TYPE_NAMES, pooled_rates.tolist())),
            "kinopulse_log_likelihood": package_likelihood,
            "analytical_log_likelihood": analytic_likelihood,
        },
        "by_repository": repository_summaries,
        "grouped_fits": {
            name: grouped_fit(sequences, group_key_function(name))
            for name in ("pooled", "repository", "author_origin", "repository_origin")
        },
        "leave_one_out_log_predictive_density": {
            "prior": "empirical-Bayes Gamma centered on the pooled fold rate",
            "scores_by_shrinkage_days": loo,
        },
        "age_hazard_comparison": {
            "bin_starts_days": AGE_BIN_STARTS,
            "piecewise_pooled_rates_per_day": {
                name: piecewise_rates[:, index].tolist()
                for index, name in enumerate(TYPE_NAMES)
            },
            "piecewise_pooled_log_likelihood": piecewise_likelihood,
            "scores_by_shrinkage_days": time_model_loo,
            "shrinkage_contract": "each age/type cell shrinks toward its fold-wide homogeneous type rate",
        },
        "terminal_survival": survival,
        "terminal_survival_curve": {
            "days": curve_times.tolist(),
            "kaplan_meier": curve_values.tolist(),
        },
        "sequences": [
            {
                "repository": sequence.repository,
                "number": sequence.number,
                "author_origin": sequence.author_origin,
                "duration_days": sequence.duration_days,
                "response_time_days": sequence.response_time_days,
                "terminal": (
                    "merge"
                    if sequence.terminal_type == TYPE_MERGE
                    else "unmerged_close"
                    if sequence.terminal_type == TYPE_CLOSE
                    else "right_censored"
                ),
            }
            for sequence in sequences
        ],
        "kinopulse_provenance": process.provenance,
    }


def render_figure(result: dict, output_path: Path) -> None:
    sequences = sorted(
        result["sequences"], key=lambda value: (value["repository"], value["duration_days"])
    )
    colors = {"merge": "#2b8cbe", "unmerged_close": "#e34a33", "right_censored": "#636363"}
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.5), constrained_layout=True)

    ax = axes[0, 0]
    for row, sequence in enumerate(sequences):
        duration = sequence["duration_days"]
        ax.hlines(row, 0.03, max(duration, 0.03), color="#bdbdbd", linewidth=1)
        ax.scatter(max(duration, 0.03), row, color=colors[sequence["terminal"]], s=22, zorder=3)
        if sequence["response_time_days"] is not None:
            ax.scatter(max(sequence["response_time_days"], 0.03), row, marker="|", s=75, color="#31a354", zorder=4)
    ax.set_xscale("log")
    ax.set_xlabel("days since PR creation (log scale)")
    ax.set_ylabel("systematic sample row")
    ax.set_title("Lifecycle paths; green tick = first maintainer response")

    ax = axes[0, 1]
    survival_curve = result["terminal_survival_curve"]
    ax.step(
        survival_curve["days"],
        survival_curve["kaplan_meier"],
        where="post",
        label="Kaplan–Meier",
        linewidth=2,
    )
    dense = np.linspace(0, 365, 300)
    terminal_rate = sum(
        result["pooled"]["rates_per_day"][name] for name in ("merge", "unmerged_close")
    )
    ax.plot(dense, np.exp(-terminal_rate * dense), label="homogeneous marked model", linestyle="--")
    ax.set_ylim(0, 1.02)
    ax.set_xlabel("days since PR creation")
    ax.set_ylabel("probability still unresolved")
    ax.set_title("Constant terminal hazards miss the fast/long-tail mixture")
    ax.legend(frameon=False)

    ax = axes[1, 0]
    repositories = list(result["by_repository"])
    x = np.arange(len(repositories))
    width = 0.24
    for offset, name, label, color in (
        (-width, "maintainer_response", "response", "#31a354"),
        (0, "merge", "merge", "#2b8cbe"),
        (width, "unmerged_close", "close", "#e34a33"),
    ):
        ax.bar(
            x + offset,
            [result["by_repository"][repo]["rates_per_day"][name] for repo in repositories],
            width,
            label=label,
            color=color,
        )
    ax.set_xticks(x, repositories)
    ax.set_ylabel("fitted events per exposure-day")
    ax.set_title("Descriptive homogeneous rates")
    ax.legend(frameon=False)

    ax = axes[1, 1]
    scores = result["age_hazard_comparison"]["scores_by_shrinkage_days"]["180.0"]
    names = list(scores)
    values = np.array([scores[name] for name in names])
    ax.barh(names, values - values.min(), color="#756bb1")
    ax.set_xlabel("LOO log predictive density above worst model (nats)")
    ax.set_title("Age structure earns its complexity out of sample")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=180)
    plt.close(fig)


def run(
    source_path: Path = Path("data/open_source_community/pull_request_lifecycle_panel.json"),
    artifact_path: Path = Path("artifacts/pull_request_lifecycle_marked_process.json"),
    figure_path: Path = Path("artifacts/pull_request_lifecycle_marked_process.png"),
) -> dict:
    sequences, source = load_sequences(source_path)
    result = evaluate_panel(sequences, source)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    render_figure(result, figure_path)
    print(f"Wrote {artifact_path} (sha256 {hashlib.sha256(artifact_path.read_bytes()).hexdigest()})")
    print(f"Wrote {figure_path}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=Path("data/open_source_community/pull_request_lifecycle_panel.json"))
    parser.add_argument("--artifact", type=Path, default=Path("artifacts/pull_request_lifecycle_marked_process.json"))
    parser.add_argument("--figure", type=Path, default=Path("artifacts/pull_request_lifecycle_marked_process.png"))
    arguments = parser.parse_args()
    run(arguments.source, arguments.artifact, arguments.figure)
