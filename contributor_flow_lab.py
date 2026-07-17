"""Decompose public commit activity into contributor arrival and return flows."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import matplotlib
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from kinopulse.solvers.opt.least_squares import RidgeSolver
from open_source_commit_ecology_lab import Commit, DTYPE, load_cohort, monday


@dataclass
class ContributorFlow:
    week: datetime
    active: int
    new: int
    continuing: int
    returning: int
    commits: int


def classify_contributor_flow(
    commits: list[Commit], end: datetime, dormancy_weeks: int = 13
) -> list[ContributorFlow]:
    human = [commit for commit in commits if not commit.is_bot and commit.committed_at <= end]
    if not human:
        return []
    by_week: dict[datetime, list[Commit]] = defaultdict(list)
    for commit in human:
        by_week[monday(commit.committed_at)].append(commit)

    last_seen: dict[str, datetime] = {}
    result = []
    week = monday(min(commit.committed_at for commit in human))
    final_week = monday(end)
    while week <= final_week:
        current = by_week[week]
        authors = {commit.author for commit in current}
        categories = Counter()
        for author in authors:
            previous = last_seen.get(author)
            if previous is None:
                category = "new"
            elif (week - previous).days <= 7 * dormancy_weeks:
                category = "continuing"
            else:
                category = "returning"
            categories[category] += 1
            last_seen[author] = week
        result.append(
            ContributorFlow(
                week=week,
                active=len(authors),
                new=categories["new"],
                continuing=categories["continuing"],
                returning=categories["returning"],
                commits=len(current),
            )
        )
        week += timedelta(days=7)
    return result


def newcomer_cohorts(commits: list[Commit], end: datetime) -> list[dict]:
    weeks_by_author: dict[str, set[datetime]] = defaultdict(set)
    for commit in commits:
        if not commit.is_bot and commit.committed_at <= end:
            weeks_by_author[commit.author].add(monday(commit.committed_at))
    cohorts: dict[int, list[tuple[datetime, set[datetime]]]] = defaultdict(list)
    for weeks in weeks_by_author.values():
        first = min(weeks)
        cohorts[first.year].append((first, weeks))

    result = []
    for year, members in sorted(cohorts.items()):
        eligible_13 = [(first, weeks) for first, weeks in members if first + timedelta(weeks=13) <= end]
        eligible_52 = [(first, weeks) for first, weeks in members if first + timedelta(weeks=52) <= end]

        def returned(member: tuple[datetime, set[datetime]], horizon: int) -> bool:
            first, weeks = member
            return any(first < week <= first + timedelta(weeks=horizon) for week in weeks)

        result.append(
            {
                "cohort_year": year,
                "new_author_identifiers": len(members),
                "eligible_for_13w_return": len(eligible_13),
                "returned_within_13w": sum(returned(member, 13) for member in eligible_13),
                "return_rate_13w": (
                    sum(returned(member, 13) for member in eligible_13) / len(eligible_13)
                    if eligible_13
                    else None
                ),
                "eligible_for_52w_return": len(eligible_52),
                "returned_within_52w": sum(returned(member, 52) for member in eligible_52),
                "return_rate_52w": (
                    sum(returned(member, 52) for member in eligible_52) / len(eligible_52)
                    if eligible_52
                    else None
                ),
            }
        )
    return result


def fit_flow_models(flows: list[ContributorFlow], train_fraction: float = 0.7) -> dict:
    target = torch.tensor([flow.active for flow in flows[1:]], dtype=DTYPE)
    baseline = torch.tensor([[1.0, flow.active] for flow in flows[:-1]], dtype=DTYPE)
    expanded = torch.tensor(
        [[1.0, flow.active, flow.new, flow.returning] for flow in flows[:-1]], dtype=DTYPE
    )
    split = max(2, min(len(target) - 1, round(len(target) * train_fraction)))

    def fit(design: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        coefficient = RidgeSolver(lambda_=0.1).solve(design[:split], target[:split]).x
        return coefficient, design @ coefficient

    baseline_coefficient, baseline_prediction = fit(baseline)
    expanded_coefficient, expanded_prediction = fit(expanded)

    def rmse(prediction: torch.Tensor) -> float:
        return torch.sqrt(torch.mean((prediction[split:] - target[split:]) ** 2)).item()

    return {
        "split": split,
        "target": target,
        "baseline_prediction": baseline_prediction,
        "expanded_prediction": expanded_prediction,
        "baseline_coefficients": baseline_coefficient,
        "expanded_coefficients": expanded_coefficient,
        "baseline_holdout_rmse": rmse(baseline_prediction),
        "expanded_holdout_rmse": rmse(expanded_prediction),
    }


def rolling_sum(values: list[int], width: int = 13) -> list[int]:
    return [sum(values[max(0, index - width + 1) : index + 1]) for index in range(len(values))]


def main(
    manifest_path: Path = Path("data/open_source_community/pallets/manifest.json"),
    output_dir: Path = Path("artifacts"),
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest, commits = load_cohort(manifest_path)
    retrieved = datetime.fromisoformat(manifest["retrieved_at_utc"]).astimezone(timezone.utc)
    end = monday(retrieved) - timedelta(microseconds=1)
    flows = classify_contributor_flow(commits, end)
    cohorts = newcomer_cohorts(commits, end)
    fit = fit_flow_models(flows)

    recent = flows[-52:]
    prior = flows[-104:-52]
    eligible_cohorts = [cohort for cohort in cohorts if cohort["return_rate_52w"] is not None]
    weighted_return_52 = sum(c["returned_within_52w"] for c in eligible_cohorts) / sum(
        c["eligible_for_52w_return"] for c in eligible_cohorts
    )
    threshold_sensitivity = {}
    for threshold in (4, 13, 26):
        sensitivity = classify_contributor_flow(commits, end, threshold)
        threshold_sensitivity[str(threshold)] = {
            "recent_52w_returning_author_weeks": sum(flow.returning for flow in sensitivity[-52:]),
            "all_returning_author_weeks": sum(flow.returning for flow in sensitivity),
        }

    def period_summary(selected: list[ContributorFlow]) -> dict:
        return {
            "active_author_weeks": sum(flow.active for flow in selected),
            "new_author_arrivals": sum(flow.new for flow in selected),
            "continuing_author_weeks": sum(flow.continuing for flow in selected),
            "returning_author_weeks": sum(flow.returning for flow in selected),
            "human_commits": sum(flow.commits for flow in selected),
        }

    report = {
        "experiment": "contributor arrival, continuity, and reactivation flows",
        "interpretation_boundary": "author identifiers and commits are activity proxies, not people or health",
        "organization": manifest["organization"],
        "snapshot_retrieved_at_utc": manifest["retrieved_at_utc"],
        "analysis_through_last_complete_week_utc": end.isoformat(),
        "dormancy_definition_weeks": 13,
        "category_contract": {
            "new": "first observed default-branch commit by normalized author identifier",
            "continuing": "observed previously and within the preceding 13 weeks",
            "returning": "observed previously but absent for more than 13 weeks",
        },
        "previous_52_weeks": period_summary(prior),
        "recent_52_weeks": period_summary(recent),
        "newcomer_cohorts": cohorts,
        "all_cohort_weighted_52w_return_rate": weighted_return_52,
        "dormancy_threshold_sensitivity": threshold_sensitivity,
        "kinopulse_ridge_next_week_active_authors": {
            "chronological_train_fraction": 0.7,
            "training_weeks": fit["split"],
            "holdout_weeks": len(fit["target"]) - fit["split"],
            "baseline_features": ["bias", "current active authors"],
            "expanded_features": ["bias", "current active authors", "new authors", "returning authors"],
            "baseline_coefficients": fit["baseline_coefficients"].tolist(),
            "expanded_coefficients": fit["expanded_coefficients"].tolist(),
            "baseline_holdout_rmse_authors": fit["baseline_holdout_rmse"],
            "expanded_holdout_rmse_authors": fit["expanded_holdout_rmse"],
            "relative_rmse_change": fit["expanded_holdout_rmse"] / fit["baseline_holdout_rmse"] - 1,
        },
    }
    (output_dir / "contributor_flow.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    dates = [flow.week for flow in flows]
    new_rolling = rolling_sum([flow.new for flow in flows])
    returning_rolling = rolling_sum([flow.returning for flow in flows])
    continuing_rolling = rolling_sum([flow.continuing for flow in flows])
    fig, axes = plt.subplots(3, 1, figsize=(12, 9), constrained_layout=True)
    axes[0].stackplot(
        dates,
        new_rolling,
        returning_rolling,
        continuing_rolling,
        labels=("new", "returning after >13 weeks", "continuing"),
        colors=("#42a5f5", "#ffb300", "#66bb6a"),
        alpha=0.85,
    )
    axes[0].set(title="Contributor flow through frozen Pallets default branches", ylabel="author-weeks / 13 weeks")
    axes[0].legend(frameon=False, ncol=3)

    complete_cohorts = [
        cohort
        for cohort in cohorts
        if cohort["eligible_for_52w_return"] == cohort["new_author_identifiers"]
    ]
    cohort_years = [c["cohort_year"] for c in complete_cohorts]
    cohort_sizes = [c["new_author_identifiers"] for c in complete_cohorts]
    return_rates = [100 * c["return_rate_52w"] for c in complete_cohorts]
    axes[1].bar(cohort_years, cohort_sizes, color="#90caf9", label="new author identifiers")
    rate_axis = axes[1].twinx()
    rate_axis.plot(cohort_years, return_rates, color="#c62828", marker="o", label="returned within 52 weeks")
    axes[1].set(ylabel="new identifiers")
    rate_axis.set(ylabel="52-week return rate (%)", ylim=(0, 100))
    axes[1].set_title("Arrival cohorts: reach and return are different")

    holdout_start = fit["split"]
    holdout_dates = dates[1:][holdout_start:]
    axes[2].plot(holdout_dates, fit["target"][holdout_start:].tolist(), color="black", label="observed")
    axes[2].plot(
        holdout_dates,
        fit["baseline_prediction"][holdout_start:].tolist(),
        color="#7e57c2",
        alpha=0.8,
        label="persistence only",
    )
    axes[2].plot(
        holdout_dates,
        fit["expanded_prediction"][holdout_start:].tolist(),
        color="#00838f",
        alpha=0.8,
        label="persistence + flow",
    )
    axes[2].set(xlabel="commit week (UTC)", ylabel="next-week active authors", title="Chronological KinoPulse ridge holdout")
    axes[2].legend(frameon=False, ncol=3)
    for axis in axes:
        axis.grid(alpha=0.2)
    fig.savefig(output_dir / "contributor_flow.png", dpi=180)
    plt.close(fig)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
