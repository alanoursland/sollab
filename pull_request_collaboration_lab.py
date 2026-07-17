"""Validate Git-topology contrasts with a frozen public pull-request panel."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.identification.counts import poisson_deviance
from kinopulse.stochastic import TemporalPointProcess
from merge_topology_audit_lab import TopologyCommit, load_topology
from open_source_commit_ecology_lab import DTYPE


INTERNAL_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def is_bot_login(login: str | None) -> bool:
    return bool(login and (login.casefold().endswith("[bot]") or "dependabot" in login.casefold()))


def causal_formal_reviews(pull_request: dict) -> list[dict]:
    created = parse_time(pull_request["created_at"])
    merged = parse_time(pull_request["merged_at"])
    author = pull_request["author_login"].casefold()
    result = []
    for review in pull_request["reviews"]:
        login = review["reviewer_login"]
        submitted = review["submitted_at"]
        if not login or not submitted or login.casefold() == author or is_bot_login(login):
            continue
        timestamp = parse_time(submitted)
        if created <= timestamp < merged:
            result.append(
                {
                    "hours": (timestamp - created).total_seconds() / 3600.0,
                    "state": review["state"],
                    "reviewer_login": login,
                }
            )
    return sorted(result, key=lambda review: review["hours"])


def causal_issue_comment_responses(pull_request: dict) -> list[dict]:
    created = parse_time(pull_request["created_at"])
    merged = parse_time(pull_request["merged_at"])
    author = pull_request["author_login"].casefold()
    result = []
    for comment in pull_request.get("issue_comment_events", []):
        login = comment["author_login"]
        if not login or login.casefold() == author or is_bot_login(login):
            continue
        timestamp = parse_time(comment["created_at"])
        if created <= timestamp < merged:
            result.append(
                {
                    "hours": (timestamp - created).total_seconds() / 3600.0,
                    "participant_login": login,
                }
            )
    return sorted(result, key=lambda comment: comment["hours"])


def integration_class(sha: str | None, topology_by_sha: dict[str, TopologyCommit]) -> str:
    commit = topology_by_sha.get(sha or "")
    if commit is None:
        return "merge_sha_not_reachable"
    if commit.parent_count > 1:
        return "merge_commit"
    if commit.parent_count == 1:
        return "linear_single_parent"
    return "root_commit"


def homogeneous_process(rate_per_hour: float) -> TemporalPointProcess:
    def intensity(times: torch.Tensor, history: torch.Tensor, params) -> torch.Tensor:
        del history, params
        return torch.full_like(times, rate_per_hour)

    def compensator(times: torch.Tensor, history: torch.Tensor, params) -> torch.Tensor:
        del history, params
        return rate_per_hour * times

    return TemporalPointProcess(intensity, compensator, homogeneous=True)


def point_process_diagnostic(event_streams: list[list[float]], horizons: list[float]) -> dict:
    total_events = sum(len(stream) for stream in event_streams)
    total_exposure = sum(horizons)
    rate = total_events / total_exposure if total_events else 0.0
    safe_rate = max(rate, 1e-12)
    process = homogeneous_process(safe_rate)
    log_likelihood = 0.0
    for events, horizon in zip(event_streams, horizons):
        tensor = torch.tensor(events, dtype=DTYPE)
        log_likelihood += float(process.log_likelihood(tensor, horizon).log_likelihood)
    expected = torch.tensor([safe_rate * horizon for horizon in horizons], dtype=DTYPE)
    observed = torch.tensor([len(stream) for stream in event_streams], dtype=DTYPE)
    return {
        "mle_event_rate_per_day": rate * 24.0,
        "total_events": total_events,
        "total_open_exposure_days": total_exposure / 24.0,
        "log_likelihood_at_mle": log_likelihood,
        "poisson_deviance": poisson_deviance(expected, observed).item(),
        "observed_zero_event_fraction": sum(not stream for stream in event_streams) / len(event_streams),
        "expected_zero_event_fraction": sum(math.exp(-rate * horizon) for horizon in horizons)
        / len(horizons),
        "warning": "descriptive homogeneous response-arrival model on a systematic n=10 validation sample",
    }


def summarize_repository(repository: dict, topology_by_sha: dict[str, TopologyCommit]) -> tuple[dict, list[dict]]:
    rows = []
    all_reviewers = set()
    authors = set()
    for rank, pull_request in enumerate(repository["pull_requests"]):
        created = parse_time(pull_request["created_at"])
        merged = parse_time(pull_request["merged_at"])
        horizon_hours = (merged - created).total_seconds() / 3600.0
        reviews = causal_formal_reviews(pull_request)
        issue_responses = causal_issue_comment_responses(pull_request)
        response_events = [
            *(dict(hours=review["hours"], participant_login=review["reviewer_login"]) for review in reviews),
            *issue_responses,
        ]
        response_events.sort(key=lambda event: event["hours"])
        all_reviewers.update(review["reviewer_login"].casefold() for review in reviews)
        authors.add(pull_request["author_login"].casefold())
        rows.append(
            {
                "sample_rank": rank,
                "pull_request_number": pull_request["number"],
                "hours_open_to_merge": horizon_hours,
                "formal_review_events": len(reviews),
                "non_author_issue_comment_responses": len(issue_responses),
                "combined_response_events": len(response_events),
                "unique_formal_reviewers": len({review["reviewer_login"].casefold() for review in reviews}),
                "unique_response_participants": len(
                    {event["participant_login"].casefold() for event in response_events}
                ),
                "hours_to_first_formal_review": reviews[0]["hours"] if reviews else None,
                "hours_to_first_combined_response": response_events[0]["hours"] if response_events else None,
                "had_approval": any(review["state"] == "APPROVED" for review in reviews),
                "had_changes_requested": any(review["state"] == "CHANGES_REQUESTED" for review in reviews),
                "non_internal_author_association": pull_request["author_association"] not in INTERNAL_ASSOCIATIONS,
                "integration_class": integration_class(pull_request["merge_commit_sha"], topology_by_sha),
                "commits_reported_by_api": pull_request["commits"],
                "changed_files": pull_request["changed_files"],
                "lines_changed": pull_request["additions"] + pull_request["deletions"],
                "issue_comments": pull_request["comments"],
                "inline_review_comments": pull_request["review_comments"],
                "review_event_hours": [review["hours"] for review in reviews],
                "combined_response_event_hours": [event["hours"] for event in response_events],
            }
        )
    reviewed_delays = [row["hours_to_first_formal_review"] for row in rows if row["hours_to_first_formal_review"] is not None]
    response_delays = [
        row["hours_to_first_combined_response"]
        for row in rows
        if row["hours_to_first_combined_response"] is not None
    ]
    horizons = [row["hours_open_to_merge"] for row in rows]
    streams = [row["combined_response_event_hours"] for row in rows]
    summary = {
        "repository": repository["name"],
        "merged_2024_population": repository["search_total"],
        "systematic_sample_size": len(rows),
        "sampled_distinct_authors": len(authors),
        "sampled_distinct_formal_reviewers": len(all_reviewers),
        "non_internal_author_prs": sum(row["non_internal_author_association"] for row in rows),
        "non_internal_author_prs_with_observed_response": sum(
            row["non_internal_author_association"] and row["combined_response_events"] > 0
            for row in rows
        ),
        "prs_with_formal_review": sum(row["formal_review_events"] > 0 for row in rows),
        "prs_with_non_author_issue_response": sum(
            row["non_author_issue_comment_responses"] > 0 for row in rows
        ),
        "prs_with_any_observed_response": sum(row["combined_response_events"] > 0 for row in rows),
        "prs_with_approval": sum(row["had_approval"] for row in rows),
        "prs_with_changes_requested": sum(row["had_changes_requested"] for row in rows),
        "median_hours_to_merge": median(horizons),
        "maximum_days_to_merge": max(horizons) / 24.0,
        "median_hours_to_first_formal_review_when_observed": median(reviewed_delays) if reviewed_delays else None,
        "median_hours_to_first_observed_response": median(response_delays) if response_delays else None,
        "median_lines_changed": median(row["lines_changed"] for row in rows),
        "median_changed_files": median(row["changed_files"] for row in rows),
        "integration_classes": dict(Counter(row["integration_class"] for row in rows)),
        "combined_response_point_process": point_process_diagnostic(streams, horizons),
    }
    return summary, rows


def main(
    panel_path: Path = Path("data/open_source_community/pull_request_panel.json"),
    manifest_path: Path = Path("data/open_source_community/pallets/manifest.json"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    panel = json.loads(panel_path.read_text(encoding="utf-8"))
    _, topology = load_topology(manifest_path)
    topology_by_sha = {commit.sha: commit for commit in topology}
    summaries = []
    rows_by_repository = {}
    for repository in panel["repositories"]:
        summary, rows = summarize_repository(repository, topology_by_sha)
        summaries.append(summary)
        rows_by_repository[repository["name"]] = rows

    report = {
        "experiment": "bounded pull-request collaboration validation panel",
        "interpretation_boundary": "systematic n=10 samples validate mechanisms but do not estimate repository populations",
        "source_snapshot_retrieved_at_utc": panel["retrieved_at_utc"],
        "merged_window": panel["merged_window"],
        "selection_rule": panel["selection_rule"],
        "review_scope": panel["review_scope"],
        "repositories": summaries,
        "privacy": "raw public logins remain only in ignored source data; artifacts contain aggregate and PR-number evidence",
        "sampled_pull_requests": {
            name: [
                {
                    key: value
                    for key, value in row.items()
                    if key not in {"review_event_hours", "combined_response_event_hours"}
                }
                for row in rows
            ]
            for name, rows in rows_by_repository.items()
        },
    }
    (output_dir / "pull_request_collaboration_panel.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    names = [summary["repository"] for summary in summaries]
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    merge_counts = [summary["integration_classes"].get("merge_commit", 0) for summary in summaries]
    linear_counts = [summary["integration_classes"].get("linear_single_parent", 0) for summary in summaries]
    axes[0, 0].bar(names, merge_counts, color="#1565c0", label="merge commit")
    axes[0, 0].bar(names, linear_counts, bottom=merge_counts, color="#ffb300", label="linear single parent")
    axes[0, 0].set(ylabel="sampled PRs", title="Frozen merge topology")
    axes[0, 0].legend(frameon=False)

    responded = [summary["prs_with_any_observed_response"] for summary in summaries]
    unreviewed = [summary["systematic_sample_size"] - summary["prs_with_any_observed_response"] for summary in summaries]
    axes[0, 1].bar(names, responded, color="#00897b", label="formal review or non-author comment")
    axes[0, 1].bar(names, unreviewed, bottom=responded, color="#cfd8dc", label="none observed")
    axes[0, 1].set(ylabel="sampled PRs", title="Observed response-event coverage")
    axes[0, 1].legend(frameon=False)

    for name in names:
        rows = rows_by_repository[name]
        axes[1, 0].scatter(
            [row["lines_changed"] for row in rows],
            [row["hours_open_to_merge"] / 24.0 for row in rows],
            label=name,
            alpha=0.8,
        )
    axes[1, 0].set(xscale="log", xlabel="lines changed (log scale)", ylabel="days to merge", title="Size and merge delay")
    axes[1, 0].legend(frameon=False)

    observed_zero = [100 * summary["combined_response_point_process"]["observed_zero_event_fraction"] for summary in summaries]
    expected_zero = [100 * summary["combined_response_point_process"]["expected_zero_event_fraction"] for summary in summaries]
    x = torch.arange(len(names), dtype=DTYPE).numpy()
    axes[1, 1].bar(x - 0.18, observed_zero, width=0.36, color="#7e57c2", label="observed")
    axes[1, 1].bar(x + 0.18, expected_zero, width=0.36, color="#90a4ae", label="homogeneous clock")
    axes[1, 1].set(xticks=x, xticklabels=names, ylabel="zero-response PRs (%)", title="KinoPulse homogeneous response-arrival check")
    axes[1, 1].legend(frameon=False)
    for axis in axes.flat:
        axis.grid(alpha=0.2, axis="y")
    fig.savefig(output_dir / "pull_request_collaboration_panel.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
