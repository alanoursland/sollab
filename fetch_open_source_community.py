"""Freeze a public GitHub organization snapshot and fetch its Git histories.

The downloaded material lives under ``data/`` and is intentionally ignored by
git.  No authentication is required or read from the environment.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ORGANIZATION = "pallets"
API_URL = f"https://api.github.com/orgs/{ORGANIZATION}/repos?type=public&per_page=100"
USER_AGENT = "sollab-open-source-community-research"


def fetch_public_repositories() -> list[dict]:
    repositories = []
    page = 1
    while True:
        request = urllib.request.Request(
            f"{API_URL}&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": USER_AGENT,
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("GitHub returned an unexpected repository payload")
        repositories.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return sorted((repo for repo in repositories if not repo["fork"]), key=lambda repo: repo["name"])


def repository_record(repo: dict) -> dict:
    """Keep the public fields needed to reproduce and audit the cohort."""
    return {
        "name": repo["name"],
        "html_url": repo["html_url"],
        "clone_url": repo["clone_url"],
        "default_branch": repo["default_branch"],
        "fork": repo["fork"],
        "archived": repo["archived"],
        "created_at": repo["created_at"],
        "updated_at": repo["updated_at"],
        "pushed_at": repo["pushed_at"],
        "size_kib": repo["size"],
        "stargazers_count": repo["stargazers_count"],
        "open_issues_count": repo["open_issues_count"],
    }


def run_git(arguments: list[str], cwd: Path | None = None) -> str:
    command = ["git"]
    if cwd is not None:
        command.extend(("-c", f"safe.directory={cwd.resolve().as_posix()}"))
    completed = subprocess.run(
        [*command, *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def clone_or_update(record: dict, repositories_dir: Path) -> dict:
    target = repositories_dir / f"{record['name']}.git"
    if target.exists():
        run_git(["fetch", "--prune", "origin"], cwd=target)
    else:
        run_git(["clone", "--bare", "--filter=blob:none", record["clone_url"], str(target)])

    default_ref = f"refs/heads/{record['default_branch']}"
    head = run_git(["rev-parse", default_ref], cwd=target)
    commit_count = int(run_git(["rev-list", "--count", default_ref], cwd=target))
    return {
        "name": record["name"],
        "path": str(target.as_posix()),
        "default_ref": default_ref,
        "head_commit": head,
        "commit_count": commit_count,
    }


def write_manifest(output_dir: Path, fetch_histories: bool = True) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    records = [repository_record(repo) for repo in fetch_public_repositories()]
    histories = []
    if fetch_histories:
        repositories_dir = output_dir / "repositories"
        repositories_dir.mkdir(exist_ok=True)
        for index, record in enumerate(records, start=1):
            print(f"[{index:02d}/{len(records):02d}] {record['name']}", flush=True)
            histories.append(clone_or_update(record, repositories_dir))

    payload = {
        "schema_version": 1,
        "organization": ORGANIZATION,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "api_url": API_URL,
        "selection_rule": "all public repositories owned by the organization, excluding forks only",
        "authentication": "none",
        "repositories": records,
        "histories": histories,
    }
    canonical = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    path = output_dir / "manifest.json"
    path.write_text(canonical, encoding="utf-8")
    # Hash the bytes on disk. Text newline translation differs by platform.
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    print(f"Wrote {path} (sha256 {digest})")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/open_source_community/pallets"),
    )
    parser.add_argument(
        "--metadata-only",
        action="store_true",
        help="write the API snapshot without cloning histories",
    )
    args = parser.parse_args()
    write_manifest(args.output_dir, fetch_histories=not args.metadata_only)


if __name__ == "__main__":
    main()
