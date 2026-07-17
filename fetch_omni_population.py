"""Download and freeze complete annual NASA OMNI2 files for 2010--2025."""

from __future__ import annotations

import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


BASE_URL = "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni"
YEARS = tuple(range(2010, 2026))


def annual_url(year: int) -> str:
    if year not in YEARS:
        raise ValueError(f"year must be in the frozen cohort {YEARS[0]}--{YEARS[-1]}")
    return f"{BASE_URL}/omni2_{year}.dat"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch_population(destination: Path = Path("data/omni_population")) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    records = []
    for index, year in enumerate(YEARS, start=1):
        url = annual_url(year)
        target = destination / f"omni2_{year}.dat"
        if target.exists():
            print(f"[{index:02d}/{len(YEARS):02d}] Reusing {target}", flush=True)
        else:
            print(f"[{index:02d}/{len(YEARS):02d}] Downloading {url}", flush=True)
            urllib.request.urlretrieve(url, target)
        records.append(
            {
                "year": year,
                "url": url,
                "path": target.as_posix(),
                "bytes": target.stat().st_size,
                "sha256": sha256(target),
            }
        )
    manifest = {
        "schema_version": 1,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "selection_rule": "every complete annual OMNI2 hourly file from 2010 through 2025 inclusive",
        "base_url": BASE_URL,
        "records": records,
    }
    path = destination / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {path} (sha256 {sha256(path)})")
    return path


if __name__ == "__main__":
    fetch_population()
