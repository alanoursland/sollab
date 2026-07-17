"""Measure the commit ecology of a whole public GitHub organization.

This is a data-feasibility lab, not a project-health classifier.  It uses only
default-branch Git history and frozen public repository metadata.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.identification.online.recursive import RecursiveLeastSquares


DTYPE = torch.float64
BOT_PATTERN = re.compile(r"(?:\[bot\]|dependabot|renovate|pre-commit-ci|github-actions)", re.I)


@dataclass(frozen=True)
class Commit:
    repository: str
    sha: str
    committed_at: datetime
    author: str
    is_bot: bool


@dataclass
class WeeklyState:
    week: datetime
    commits: int
    bot_commits: int
    active_contributors: int
    new_contributors: int
    active_repositories: int
    contributor_hhi: float
    trailing_13w_commits: int = 0
    trailing_13w_contributors: int = 0


def canonical_author(email: str, name: str) -> str:
    """Normalize an author privately; identifiers are never written to artifacts."""
    email = email.strip().casefold()
    name = " ".join(name.split()).casefold()
    if email.endswith("@users.noreply.github.com"):
        local = email.split("@", 1)[0]
        return f"github:{local.split('+', 1)[-1]}"
    return f"email:{email}" if email else f"name:{name}"


def is_bot_author(email: str, name: str) -> bool:
    return bool(BOT_PATTERN.search(f"{email} {name}"))


def parse_git_log(repository: str, text: str) -> list[Commit]:
    commits = []
    for raw_record in text.split("\x00"):
        record = raw_record.strip("\r\n")
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) != 4:
            raise ValueError(f"Malformed git log record for {repository}")
        sha, timestamp, email, name = fields
        commits.append(
            Commit(
                repository=repository,
                sha=sha,
                committed_at=datetime.fromisoformat(timestamp).astimezone(timezone.utc),
                author=canonical_author(email, name),
                is_bot=is_bot_author(email, name),
            )
        )
    return commits


def read_repository_history(path: Path, name: str, default_ref: str, head: str) -> list[Commit]:
    git = ["git", "-c", f"safe.directory={path.resolve().as_posix()}"]
    resolved = subprocess.run(
        [*git, "rev-parse", default_ref], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()
    if resolved != head:
        raise ValueError(f"{name} default branch moved: manifest={head}, local={resolved}")
    output = subprocess.run(
        [*git, "log", default_ref, "--format=%H%x1f%cI%x1f%aE%x1f%aN%x00"],
        cwd=path,
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8", errors="replace")
    return parse_git_log(name, output)


def monday(timestamp: datetime) -> datetime:
    day = timestamp.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return day - timedelta(days=day.weekday())


def summarize_weekly(commits: list[Commit], end: datetime) -> list[WeeklyState]:
    human = [commit for commit in commits if not commit.is_bot and commit.committed_at <= end]
    if not human:
        return []
    first_week, final_week = monday(min(c.committed_at for c in human)), monday(end)
    by_week: dict[datetime, list[Commit]] = defaultdict(list)
    bots_by_week: Counter = Counter()
    for commit in commits:
        if commit.committed_at > end:
            continue
        week = monday(commit.committed_at)
        if commit.is_bot:
            bots_by_week[week] += 1
        else:
            by_week[week].append(commit)

    seen: set[str] = set()
    states = []
    week = first_week
    while week <= final_week:
        current = by_week[week]
        counts = Counter(commit.author for commit in current)
        total = len(current)
        contributors = set(counts)
        hhi = sum((count / total) ** 2 for count in counts.values()) if total else 0.0
        states.append(
            WeeklyState(
                week=week,
                commits=total,
                bot_commits=bots_by_week[week],
                active_contributors=len(contributors),
                new_contributors=len(contributors - seen),
                active_repositories=len({commit.repository for commit in current}),
                contributor_hhi=hhi,
            )
        )
        seen.update(contributors)
        week += timedelta(days=7)

    trailing: deque[list[Commit]] = deque(maxlen=13)
    for state in states:
        trailing.append(by_week[state.week])
        state.trailing_13w_commits = sum(len(batch) for batch in trailing)
        state.trailing_13w_contributors = len({c.author for batch in trailing for c in batch})
    return states


def persistence_trace(states: list[WeeklyState], forgetting_factor: float = 0.995) -> list[float]:
    """Track an AR(1) slope for log trailing activity with KinoPulse RLS."""
    values = torch.tensor(
        [math.log1p(state.trailing_13w_commits) for state in states], dtype=DTYPE
    )
    if len(values) < 3:
        return [math.nan] * len(values)
    scale = values.std().clamp_min(1e-12)
    standardized = (values - values.mean()) / scale
    estimator = RecursiveLeastSquares(
        n_params=2,
        forgetting_factor=forgetting_factor,
        initial_covariance=100.0,
        dtype=DTYPE,
    )
    slopes = [math.nan]
    for previous, current in zip(standardized[:-1], standardized[1:]):
        theta = estimator.update(torch.stack((torch.ones((), dtype=DTYPE), previous)), current)
        slopes.append(theta[1].item())
    return slopes


def window_summary(states: list[WeeklyState], start: int, stop: int) -> dict:
    selected = states[start:stop]
    return {
        "weeks": len(selected),
        "human_commits": sum(state.commits for state in selected),
        "bot_commits": sum(state.bot_commits for state in selected),
        "median_weekly_active_contributors": float(
            torch.tensor([state.active_contributors for state in selected], dtype=DTYPE).median().item()
        ),
        "median_weekly_active_repositories": float(
            torch.tensor([state.active_repositories for state in selected], dtype=DTYPE).median().item()
        ),
    }


def add_author_concentration(summary: dict, commits: list[Commit], start: datetime, end: datetime) -> None:
    counts = Counter(
        commit.author
        for commit in commits
        if not commit.is_bot and start <= commit.committed_at <= end
    )
    total = sum(counts.values())
    summary.update(
        {
            "distinct_human_author_identifiers": len(counts),
            "top_author_commit_share": max(counts.values()) / total if total else 0.0,
            "author_commit_hhi": sum((count / total) ** 2 for count in counts.values()) if total else 0.0,
        }
    )


def load_cohort(manifest_path: Path) -> tuple[dict, list[Commit]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    commits = []
    for history in manifest["histories"]:
        commits.extend(
            read_repository_history(
                Path(history["path"]),
                history["name"],
                history["default_ref"],
                history["head_commit"],
            )
        )
    return manifest, commits


def main(
    manifest_path: Path = Path("data/open_source_community/pallets/manifest.json"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, commits = load_cohort(manifest_path)
    retrieved_at = datetime.fromisoformat(manifest["retrieved_at_utc"]).astimezone(timezone.utc)
    analysis_end = monday(retrieved_at) - timedelta(microseconds=1)
    states = summarize_weekly(commits, analysis_end)
    slopes = persistence_trace(states)
    human_commits = [commit for commit in commits if not commit.is_bot]
    bot_commits = [commit for commit in commits if commit.is_bot]
    authors = {commit.author for commit in human_commits}
    analyzed_human = [commit for commit in human_commits if commit.committed_at <= analysis_end]
    author_counts = Counter(commit.author for commit in analyzed_human)
    total_analyzed = len(analyzed_human)
    burn_in = 104

    repository_summaries = []
    metadata = {repo["name"]: repo for repo in manifest["repositories"]}
    for history in manifest["histories"]:
        selected = [commit for commit in commits if commit.repository == history["name"]]
        humans = [commit for commit in selected if not commit.is_bot]
        repository_summaries.append(
            {
                "name": history["name"],
                "archived_at_snapshot": metadata[history["name"]]["archived"],
                "default_branch_commit_count": len(selected),
                "human_commit_count": len(humans),
                "bot_commit_count": len(selected) - len(humans),
                "distinct_human_authors": len({commit.author for commit in humans}),
                "first_commit_utc": min(c.committed_at for c in selected).isoformat(),
                "last_commit_utc": max(c.committed_at for c in selected).isoformat(),
                "head_commit": history["head_commit"],
            }
        )

    recent = window_summary(states, -52, len(states))
    previous = window_summary(states, -104, -52)
    add_author_concentration(recent, commits, states[-52].week, analysis_end)
    add_author_concentration(
        previous,
        commits,
        states[-104].week,
        states[-52].week - timedelta(microseconds=1),
    )
    annual = []
    for year in range(states[0].week.year, states[-1].week.year + 1):
        selected = [state for state in states if state.week.year == year]
        if selected:
            annual.append(
                {
                    "year": year,
                    "human_commits": sum(state.commits for state in selected),
                    "new_contributors": sum(state.new_contributors for state in selected),
                    "peak_13w_contributors": max(state.trailing_13w_contributors for state in selected),
                    "median_active_repositories": float(
                        torch.tensor([s.active_repositories for s in selected], dtype=DTYPE).median().item()
                    ),
                }
            )

    valid_slopes = [slope for slope in slopes[burn_in:] if math.isfinite(slope)]
    report = {
        "experiment": "whole-organization default-branch commit ecology",
        "interpretation_boundary": "commit activity is not project health or community decline",
        "organization": manifest["organization"],
        "snapshot_retrieved_at_utc": manifest["retrieved_at_utc"],
        "analysis_through_last_complete_week_utc": analysis_end.isoformat(),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "selection_rule": manifest["selection_rule"],
        "repository_count": len(manifest["repositories"]),
        "archived_repository_count": sum(repo["archived"] for repo in manifest["repositories"]),
        "history": {
            "first_commit_utc": min(c.committed_at for c in commits).isoformat(),
            "last_commit_utc": max(c.committed_at for c in commits).isoformat(),
            "default_branch_commits": len(commits),
            "human_commits": len(human_commits),
            "bot_commits": len(bot_commits),
            "distinct_human_author_identifiers": len(authors),
            "identity_resolution": "repository mailmap-aware author email; GitHub noreply variants normalized",
            "weeks": len(states),
            "top_author_commit_share_through_complete_week": max(author_counts.values()) / total_analyzed,
            "author_commit_hhi_through_complete_week": sum(
                (count / total_analyzed) ** 2 for count in author_counts.values()
            ),
        },
        "recent_52_weeks": recent,
        "previous_52_weeks": previous,
        "recent_to_previous_commit_ratio": recent["human_commits"] / max(previous["human_commits"], 1),
        "kinopulse_rls_persistence": {
            "signal": "log1p trailing-13-week human commits",
            "forgetting_factor": 0.995,
            "burn_in_weeks": burn_in,
            "median_slope_after_burn_in": float(torch.tensor(valid_slopes, dtype=DTYPE).median().item()),
            "latest_slope": slopes[-1],
            "warning": "descriptive persistence diagnostic; trends and seasonality can mimic critical slowing",
        },
        "annual_summary": annual,
        "repositories": repository_summaries,
        "excluded_channels": [
            "non-default branches",
            "issues and pull requests",
            "reviews and comments",
            "releases except insofar as they create commits",
            "private activity",
        ],
    }
    (output_dir / "open_source_commit_ecology.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    dates = [state.week for state in states]
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), sharex=True, constrained_layout=True)
    axes[0].plot(dates, [state.trailing_13w_commits for state in states], color="#2962a3")
    axes[0].set(ylabel="human commits / 13 weeks", title="Pallets default-branch commit ecology")
    axes[1].plot(
        dates,
        [state.trailing_13w_contributors for state in states],
        color="#00897b",
        label="contributors in trailing 13 weeks",
    )
    axes[1].plot(
        dates,
        [state.active_repositories for state in states],
        color="#ef6c00",
        alpha=0.65,
        label="active repositories this week",
    )
    axes[1].set(ylabel="breadth")
    axes[1].legend(frameon=False, ncol=2)
    axes[2].plot(dates[burn_in:], slopes[burn_in:], color="#7b1fa2")
    axes[2].axhline(1.0, color="black", linewidth=0.8, linestyle="--")
    axes[2].set(
        xlabel="commit week (UTC)",
        ylabel="online AR(1) slope",
        title="KinoPulse RLS persistence diagnostic (descriptive, not a tipping-point test)",
    )
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.savefig(output_dir / "open_source_commit_ecology.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
