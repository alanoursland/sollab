"""Freeze a bounded public pull-request and review panel without credentials."""

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
MERGED_START = "2024-01-01"
MERGED_END = "2024-12-31"
SAMPLE_SIZE = 10
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


def search_merged_pull_requests(repository: str) -> tuple[int, list[dict]]:
    query = (
        f"repo:{ORGANIZATION}/{repository} is:pr is:merged "
        f"merged:{MERGED_START}..{MERGED_END}"
    )
    base = "https://api.github.com/search/issues?" + urllib.parse.urlencode(
        {"q": query, "sort": "created", "order": "asc", "per_page": 100}
    )
    items = []
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


def fetch_reviews(pull_url: str) -> list[dict]:
    reviews = []
    page = 1
    while True:
        batch = request_json(f"{pull_url}/reviews?per_page=100&page={page}")
        reviews.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return reviews


def fetch_issue_comments(repository: str, number: int) -> list[dict]:
    comments = []
    page = 1
    base = f"https://api.github.com/repos/{ORGANIZATION}/{repository}/issues/{number}/comments"
    while True:
        batch = request_json(f"{base}?per_page=100&page={page}")
        comments.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return comments


def compact_issue_comments(comments: list[dict]) -> list[dict]:
    return [
        {
            "created_at": comment["created_at"],
            "author_login": comment["user"]["login"] if comment.get("user") else None,
            "author_association": comment["author_association"],
        }
        for comment in comments
    ]


def compact_pull_request(details: dict, reviews: list[dict], issue_comments: list[dict]) -> dict:
    return {
        "number": details["number"],
        "html_url": details["html_url"],
        "created_at": details["created_at"],
        "merged_at": details["merged_at"],
        "closed_at": details["closed_at"],
        "author_login": details["user"]["login"],
        "author_association": details["author_association"],
        "merged_by_login": details["merged_by"]["login"] if details.get("merged_by") else None,
        "merge_commit_sha": details["merge_commit_sha"],
        "commits": details["commits"],
        "comments": details["comments"],
        "review_comments": details["review_comments"],
        "additions": details["additions"],
        "deletions": details["deletions"],
        "changed_files": details["changed_files"],
        "draft": details["draft"],
        "issue_comment_events": compact_issue_comments(issue_comments),
        "reviews": [
            {
                "submitted_at": review["submitted_at"],
                "state": review["state"],
                "reviewer_login": review["user"]["login"] if review.get("user") else None,
                "author_association": review["author_association"],
            }
            for review in reviews
        ],
    }


def fetch_panel(output_path: Path = Path("data/open_source_community/pull_request_panel.json")) -> Path:
    repositories = []
    for repository in REPOSITORIES:
        total, search_items = search_merged_pull_requests(repository)
        sample = evenly_spaced_sample(search_items, SAMPLE_SIZE)
        pull_requests = []
        print(f"{repository}: sampling {len(sample)} of {total} merged 2024 pull requests", flush=True)
        for index, item in enumerate(sample, start=1):
            pull_url = item["pull_request"]["url"]
            print(f"  [{index:02d}/{len(sample):02d}] #{item['number']}", flush=True)
            details = request_json(pull_url)
            reviews = fetch_reviews(pull_url)
            issue_comments = (
                fetch_issue_comments(repository, details["number"]) if details["comments"] else []
            )
            pull_requests.append(compact_pull_request(details, reviews, issue_comments))
        repositories.append(
            {
                "name": repository,
                "search_total": total,
                "sample_size": len(sample),
                "sample_ranks_zero_based": [search_items.index(item) for item in sample],
                "pull_requests": pull_requests,
            }
        )

    payload = {
        "schema_version": 2,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "organization": ORGANIZATION,
        "repositories": repositories,
        "merged_window": [MERGED_START, MERGED_END],
        "selection_rule": (
            "all merged pull requests in the calendar window ordered by creation time, "
            f"then {SAMPLE_SIZE} evenly spaced ranks including endpoints per repository"
        ),
        "authentication": "none",
        "review_scope": (
            "formal pull-request reviews and issue comments; inline review-comment bodies are not fetched"
        ),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()
    print(f"Wrote {output_path} (sha256 {digest})")
    return output_path


def enrich_existing_issue_comments(
    path: Path = Path("data/open_source_community/pull_request_panel.json"),
) -> Path:
    payload = json.loads(path.read_text(encoding="utf-8"))
    for repository in payload["repositories"]:
        for pull_request in repository["pull_requests"]:
            if "issue_comment_events" in pull_request:
                continue
            comments = (
                fetch_issue_comments(repository["name"], pull_request["number"])
                if pull_request["comments"]
                else []
            )
            pull_request["issue_comment_events"] = compact_issue_comments(comments)
            if comments:
                print(f"{repository['name']} #{pull_request['number']}: {len(comments)} issue comments")
    payload["schema_version"] = 2
    payload["review_scope"] = (
        "formal pull-request reviews and issue comments; inline review-comment bodies are not fetched"
    )
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Updated {path} (sha256 {hashlib.sha256(path.read_bytes()).hexdigest()})")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--enrich-existing-issue-comments", action="store_true")
    args = parser.parse_args()
    if args.enrich_existing_issue_comments:
        enrich_existing_issue_comments()
    else:
        fetch_panel()
