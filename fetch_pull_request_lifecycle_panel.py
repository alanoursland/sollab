"""Freeze a fixed-creation-cohort pull-request lifecycle panel.

The source snapshot is intentionally ignored.  Tracked analyses derived from it
must not retain public account names.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ORGANIZATION = "pallets"
REPOSITORIES = ("flask", "quart")
CREATED_START = "2024-01-01"
CREATED_END = "2024-12-31"
OBSERVATION_END = "2025-12-31T23:59:59Z"
SAMPLE_SIZE = 15
USER_AGENT = "sollab-open-source-community-research"


def request_json(url: str):
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def search_created_pull_requests(repository: str) -> tuple[int, list[dict]]:
    query = (
        f"repo:{ORGANIZATION}/{repository} is:pr "
        f"created:{CREATED_START}..{CREATED_END}"
    )
    base = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
        {"q": query, "sort": "created", "order": "asc", "per_page": 100}
    )
    items: list[dict] = []
    total = None
    page = 1
    while True:
        payload = request_json(f"{base}&page={page}")
        if payload.get("incomplete_results"):
            raise RuntimeError(f"GitHub returned incomplete search results for {repository}")
        if total is None:
            total = int(payload["total_count"])
            if total > 1000:
                raise RuntimeError("GitHub Search's 1,000-result cap would truncate this cohort")
        batch = payload["items"]
        items.extend(batch)
        if len(items) >= total or len(batch) < 100:
            break
        page += 1
    if len(items) != total:
        raise RuntimeError(f"Expected {total} search results for {repository}, received {len(items)}")
    return total, sorted(items, key=lambda item: (item["created_at"], item["number"]))


def evenly_spaced_sample(items: list[dict], size: int) -> list[dict]:
    if size <= 0:
        raise ValueError("size must be positive")
    if len(items) <= size:
        return items.copy()
    if size == 1:
        return [items[len(items) // 2]]
    indices = [round(index * (len(items) - 1) / (size - 1)) for index in range(size)]
    if len(set(indices)) != len(indices):
        raise RuntimeError("Evenly spaced sample produced duplicate ranks")
    return [items[index] for index in indices]


def fetch_paginated(url: str) -> list[dict]:
    values: list[dict] = []
    page = 1
    separator = "&" if "?" in url else "?"
    while True:
        batch = request_json(f"{url}{separator}per_page=100&page={page}")
        values.extend(batch)
        if len(batch) < 100:
            return values
        page += 1


def compact_item(item: dict, reviews: list[dict], comments: list[dict]) -> dict:
    pull = item["pull_request"]
    return {
        "number": item["number"],
        "html_url": item["html_url"],
        "created_at": item["created_at"],
        "closed_at": item["closed_at"],
        "merged_at": pull.get("merged_at"),
        "state": item["state"],
        "draft": pull.get("draft", False),
        "author_login": item["user"]["login"] if item.get("user") else None,
        "author_association": item.get("author_association"),
        "issue_comment_events": [
            {
                "created_at": comment["created_at"],
                "author_login": comment["user"]["login"] if comment.get("user") else None,
                "author_association": comment.get("author_association"),
            }
            for comment in comments
        ],
        "reviews": [
            {
                "submitted_at": review["submitted_at"],
                "state": review["state"],
                "reviewer_login": review["user"]["login"] if review.get("user") else None,
                "author_association": review.get("author_association"),
            }
            for review in reviews
            if review.get("submitted_at")
        ],
    }


def fetch_panel(
    output_path: Path = Path("data/open_source_community/pull_request_lifecycle_panel.json"),
) -> Path:
    repositories = []
    for repository in REPOSITORIES:
        total, population = search_created_pull_requests(repository)
        sample = evenly_spaced_sample(population, SAMPLE_SIZE)
        pulls = []
        print(f"{repository}: sampling {len(sample)} of {total} PRs created in 2024", flush=True)
        for index, item in enumerate(sample, start=1):
            number = item["number"]
            print(f"  [{index:02d}/{len(sample):02d}] #{number}", flush=True)
            reviews = fetch_paginated(item["pull_request"]["url"] + "/reviews")
            comments = []
            if item.get("comments", 0):
                comments = fetch_paginated(
                    f"https://api.github.com/repos/{ORGANIZATION}/{repository}/issues/{number}/comments"
                )
            pulls.append(compact_item(item, reviews, comments))
        repositories.append(
            {
                "name": repository,
                "population_size": total,
                "sample_size": len(sample),
                "sample_ranks_zero_based": [population.index(item) for item in sample],
                "pull_requests": pulls,
            }
        )

    payload = {
        "schema_version": 1,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "organization": ORGANIZATION,
        "created_window": [CREATED_START, CREATED_END],
        "observation_end": OBSERVATION_END,
        "repositories": repositories,
        "selection_rule": (
            "all pull requests created in the calendar window ordered by creation time, "
            f"then {SAMPLE_SIZE} evenly spaced ranks including endpoints per repository"
        ),
        "authentication": "none",
        "activity_scope": "formal reviews and issue comments; inline review-comment bodies are not fetched",
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    print(f"Wrote {output_path} (sha256 {digest})")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("data/open_source_community/pull_request_lifecycle_panel.json"))
    args = parser.parse_args()
    fetch_panel(args.output)
