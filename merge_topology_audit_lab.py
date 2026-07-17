"""Audit how Git merge topology changes measured open-source dynamics."""

from __future__ import annotations

import json
import math
import re
import subprocess
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.opt.least_squares import RidgeSolver
from open_source_commit_ecology_lab import (
    Commit,
    DTYPE,
    canonical_author,
    is_bot_author,
    monday,
)


PR_SUFFIX = re.compile(r"\(#\d+\)\s*$")
MERGE_PR = re.compile(r"^merge pull request #\d+", re.I)


@dataclass(frozen=True)
class TopologyCommit:
    repository: str
    sha: str
    committed_at: datetime
    author: str
    is_bot: bool
    parent_count: int
    subject: str
    first_parent: bool

    @property
    def is_merge(self) -> bool:
        return self.parent_count > 1

    @property
    def has_pr_suffix(self) -> bool:
        return self.parent_count == 1 and bool(PR_SUFFIX.search(self.subject))

    @property
    def is_explicit_pr_merge(self) -> bool:
        return self.is_merge and bool(MERGE_PR.search(self.subject))

    def as_commit(self) -> Commit:
        return Commit(self.repository, self.sha, self.committed_at, self.author, self.is_bot)


def parse_topology_log(repository: str, text: str, first_parent_shas: set[str]) -> list[TopologyCommit]:
    result = []
    for raw in text.split("\x00"):
        record = raw.strip("\r\n")
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) != 6:
            raise ValueError(f"Malformed topology record for {repository}")
        sha, timestamp, email, name, parents, subject = fields
        result.append(
            TopologyCommit(
                repository=repository,
                sha=sha,
                committed_at=datetime.fromisoformat(timestamp).astimezone(timezone.utc),
                author=canonical_author(email, name),
                is_bot=is_bot_author(email, name),
                parent_count=len(parents.split()) if parents else 0,
                subject=subject,
                first_parent=sha in first_parent_shas,
            )
        )
    return result


def read_topology(path: Path, name: str, default_ref: str, expected_head: str) -> list[TopologyCommit]:
    git = ["git", "-c", f"safe.directory={path.resolve().as_posix()}"]
    head = subprocess.run(
        [*git, "rev-parse", default_ref], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()
    if head != expected_head:
        raise ValueError(f"{name} default branch moved: manifest={expected_head}, local={head}")
    first_parent_shas = set(
        subprocess.run(
            [*git, "rev-list", "--first-parent", default_ref],
            cwd=path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.split()
    )
    output = subprocess.run(
        [*git, "log", default_ref, "--format=%H%x1f%cI%x1f%aE%x1f%aN%x1f%P%x1f%s%x00"],
        cwd=path,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", errors="replace")
    return parse_topology_log(name, output, first_parent_shas)


def load_topology(manifest_path: Path) -> tuple[dict, list[TopologyCommit]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    commits = []
    for history in manifest["histories"]:
        commits.extend(
            read_topology(
                Path(history["path"]),
                history["name"],
                history["default_ref"],
                history["head_commit"],
            )
        )
    return manifest, commits


def weekly_topology(commits: list[TopologyCommit], end: datetime) -> list[dict]:
    human = [commit for commit in commits if not commit.is_bot and commit.committed_at <= end]
    by_week: dict[datetime, list[TopologyCommit]] = defaultdict(list)
    for commit in human:
        by_week[monday(commit.committed_at)].append(commit)
    start = monday(min(commit.committed_at for commit in human))
    result = []
    week = start
    while week <= monday(end):
        current = by_week[week]
        first = [commit for commit in current if commit.first_parent]
        result.append(
            {
                "week": week,
                "all_commits": len(current),
                "first_parent_commits": len(first),
                "side_history_commits": len(current) - len(first),
                "merge_commits": sum(commit.is_merge for commit in first),
                "single_parent_pr_suffix_commits": sum(commit.has_pr_suffix for commit in first),
                "all_authors": len({commit.author for commit in current}),
                "first_parent_authors": len({commit.author for commit in first}),
            }
        )
        week += timedelta(days=7)
    return result


def cohort_return_rate(commits: list[Commit], end: datetime, first_year: int, last_year: int) -> dict:
    weeks: dict[str, set[datetime]] = defaultdict(set)
    for commit in commits:
        if not commit.is_bot and commit.committed_at <= end:
            weeks[commit.author].add(monday(commit.committed_at))
    eligible = returned = 0
    for active_weeks in weeks.values():
        first = min(active_weeks)
        if first_year <= first.year <= last_year and first + timedelta(weeks=52) <= end:
            eligible += 1
            returned += any(first < week <= first + timedelta(weeks=52) for week in active_weeks)
    return {
        "cohort_years": [first_year, last_year],
        "eligible_new_author_identifiers": eligible,
        "returned_within_52_weeks": returned,
        "return_rate_52w": returned / eligible if eligible else None,
    }


def fit_observation_map(weekly: list[dict], train_fraction: float = 0.7) -> dict:
    target = torch.tensor([row["all_commits"] for row in weekly], dtype=DTYPE)
    first_parent = torch.tensor([row["first_parent_commits"] for row in weekly], dtype=DTYPE)
    design = torch.tensor(
        [
            [1.0, row["first_parent_commits"], row["merge_commits"], row["single_parent_pr_suffix_commits"]]
            for row in weekly
        ],
        dtype=DTYPE,
    )
    split = max(2, min(len(target) - 1, round(len(target) * train_fraction)))
    coefficient = RidgeSolver(lambda_=0.1).solve(design[:split], target[:split]).x
    prediction = design @ coefficient

    def rmse(values: torch.Tensor) -> float:
        return torch.sqrt(torch.mean((values[split:] - target[split:]) ** 2)).item()

    return {
        "split": split,
        "coefficients": coefficient.tolist(),
        "identity_holdout_rmse": rmse(first_parent),
        "ridge_holdout_rmse": rmse(prediction),
        "holdout_target_mean": target[split:].mean().item(),
    }


def rolling_sum(values: list[int], width: int = 13) -> list[int]:
    return [sum(values[max(0, index - width + 1) : index + 1]) for index in range(len(values))]


def main(
    manifest_path: Path = Path("data/open_source_community/pallets/manifest.json"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, commits = load_topology(manifest_path)
    retrieved = datetime.fromisoformat(manifest["retrieved_at_utc"]).astimezone(timezone.utc)
    end = monday(retrieved) - timedelta(microseconds=1)
    analyzed = [commit for commit in commits if commit.committed_at <= end]
    human = [commit for commit in analyzed if not commit.is_bot]
    weekly = weekly_topology(commits, end)
    observation_fit = fit_observation_map(weekly)

    repositories = []
    for history in manifest["histories"]:
        selected = [commit for commit in analyzed if commit.repository == history["name"]]
        human_selected = [commit for commit in selected if not commit.is_bot]
        first = [commit for commit in human_selected if commit.first_parent]
        repositories.append(
            {
                "name": history["name"],
                "human_reachable_commits": len(human_selected),
                "human_first_parent_commits": len(first),
                "human_side_history_commits": len(human_selected) - len(first),
                "first_parent_merge_commits": sum(commit.is_merge for commit in first),
                "explicit_pull_request_merges": sum(commit.is_explicit_pr_merge for commit in first),
                "single_parent_pr_suffix_commits": sum(commit.has_pr_suffix for commit in first),
                "reachable_author_identifiers": len({commit.author for commit in human_selected}),
                "first_parent_author_identifiers": len({commit.author for commit in first}),
            }
        )

    annual = []
    for year in range(weekly[0]["week"].year, weekly[-1]["week"].year + 1):
        selected = [row for row in weekly if row["week"].year == year]
        if not selected:
            continue
        all_commits = sum(row["all_commits"] for row in selected)
        first_commits = sum(row["first_parent_commits"] for row in selected)
        annual.append(
            {
                "year": year,
                "human_reachable_commits": all_commits,
                "human_first_parent_commits": first_commits,
                "human_side_history_commits": all_commits - first_commits,
                "side_history_fraction": (all_commits - first_commits) / all_commits if all_commits else 0.0,
                "first_parent_merges": sum(row["merge_commits"] for row in selected),
                "single_parent_pr_suffix_commits": sum(
                    row["single_parent_pr_suffix_commits"] for row in selected
                ),
            }
        )

    first_parent_commits = [commit.as_commit() for commit in human if commit.first_parent]
    reachable_commits = [commit.as_commit() for commit in human]
    reachable_authors = {commit.author for commit in human}
    first_parent_authors = {commit.author for commit in human if commit.first_parent}
    report = {
        "experiment": "Git merge-topology measurement audit",
        "interpretation_boundary": "topology changes observable commit history; neither view is collaboration ground truth",
        "organization": manifest["organization"],
        "snapshot_retrieved_at_utc": manifest["retrieved_at_utc"],
        "analysis_through_last_complete_week_utc": end.isoformat(),
        "aggregate": {
            "human_reachable_commits": len(human),
            "human_first_parent_commits": sum(commit.first_parent for commit in human),
            "human_side_history_commits": sum(not commit.first_parent for commit in human),
            "side_history_fraction": sum(not commit.first_parent for commit in human) / len(human),
            "first_parent_merge_commits": sum(commit.first_parent and commit.is_merge for commit in human),
            "explicit_pull_request_merges": sum(
                commit.first_parent and commit.is_explicit_pr_merge for commit in human
            ),
            "single_parent_pr_suffix_commits": sum(
                commit.first_parent and commit.has_pr_suffix for commit in human
            ),
            "reachable_author_identifiers": len(reachable_authors),
            "first_parent_author_identifiers": len(first_parent_authors),
            "first_parent_author_coverage": len(first_parent_authors) / len(reachable_authors),
        },
        "return_rate_sensitivity_2013_2024": {
            "reachable_history": cohort_return_rate(reachable_commits, end, 2013, 2024),
            "first_parent_only": cohort_return_rate(first_parent_commits, end, 2013, 2024),
        },
        "kinopulse_ridge_observation_map": {
            "target": "weekly human reachable commits",
            "features": [
                "bias",
                "weekly human first-parent commits",
                "weekly first-parent merges",
                "weekly single-parent commits ending with a PR reference",
            ],
            "chronological_train_fraction": 0.7,
            "training_weeks": observation_fit["split"],
            "holdout_weeks": len(weekly) - observation_fit["split"],
            "coefficients": observation_fit["coefficients"],
            "identity_map_holdout_rmse_commits": observation_fit["identity_holdout_rmse"],
            "ridge_map_holdout_rmse_commits": observation_fit["ridge_holdout_rmse"],
            "holdout_mean_weekly_reachable_commits": observation_fit["holdout_target_mean"],
        },
        "repositories": repositories,
        "annual_summary": annual,
        "definitions": {
            "reachable_history": "all commits reachable through every parent from the frozen default-branch head",
            "first_parent": "commits on git rev-list --first-parent from that head",
            "side_history": "reachable commits not on the first-parent path",
            "pr_suffix": "single-parent commit subject ending in (#number); suggestive, not proof, of PR integration",
        },
    }
    (output_dir / "merge_topology_audit.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    dates = [row["week"] for row in weekly]
    reachable_rolling = rolling_sum([row["all_commits"] for row in weekly])
    first_rolling = rolling_sum([row["first_parent_commits"] for row in weekly])
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), constrained_layout=True)
    axes[0].plot(dates, reachable_rolling, color="#1565c0", label="all reachable")
    axes[0].plot(dates, first_rolling, color="#ef6c00", label="first parent")
    axes[0].fill_between(dates, first_rolling, reachable_rolling, color="#90caf9", alpha=0.35)
    axes[0].set(title="Git topology changes the observed commit ecology", ylabel="human commits / 13 weeks")
    axes[0].legend(frameon=False, ncol=2)

    years = [row["year"] for row in annual]
    first_annual = [row["human_first_parent_commits"] for row in annual]
    side_annual = [row["human_side_history_commits"] for row in annual]
    axes[1].bar(years, first_annual, color="#ffb74d", label="first parent")
    axes[1].bar(years, side_annual, bottom=first_annual, color="#64b5f6", label="side history")
    axes[1].set(ylabel="human commits", title="Annual reachable history by topology")
    axes[1].legend(frameon=False, ncol=2)

    names = [row["name"] for row in sorted(repositories, key=lambda row: row["human_reachable_commits"], reverse=True)]
    coverage = [
        100 * row["first_parent_author_identifiers"] / max(row["reachable_author_identifiers"], 1)
        for row in sorted(repositories, key=lambda row: row["human_reachable_commits"], reverse=True)
    ]
    axes[2].bar(names, coverage, color="#7e57c2")
    axes[2].axhline(100, color="black", linewidth=0.8)
    axes[2].set(xlabel="repository (ordered by reachable commits)", ylabel="first-parent author coverage (%)", ylim=(0, 105))
    axes[2].tick_params(axis="x", rotation=55)
    axes[2].set_title("First-parent history can hide reachable author identities")
    for axis in axes:
        axis.grid(alpha=0.2, axis="y")
    fig.savefig(output_dir / "merge_topology_audit.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
