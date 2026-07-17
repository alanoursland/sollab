"""Freeze NOAA PSL's public MEI.v2 index with provenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


DATA_URL = "https://psl.noaa.gov/enso/mei/data/meiv2.data"
DOCUMENTATION_URL = "https://psl.noaa.gov/data/timeseries/month/DS/MEIV2/"
USER_AGENT = "sollab-enso-dynamics-research"
MISSING_MAXIMUM = -90.0


def parse_psl_monthly(text: str) -> list[dict]:
    """Parse NOAA PSL's standard annual-row monthly time-series format."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2:
        raise ValueError("MEI.v2 response is too short")
    coverage = lines[0].split()
    if len(coverage) != 2 or not all(value.lstrip("-").isdigit() for value in coverage):
        raise ValueError("first line must contain start and end years")
    start_year, end_year = map(int, coverage)
    records = []
    for line in lines[1:]:
        fields = line.split()
        if len(fields) != 13 or not fields[0].lstrip("-").isdigit():
            continue
        year = int(fields[0])
        if not start_year <= year <= end_year:
            raise ValueError(f"year {year} lies outside declared coverage")
        for month, raw in enumerate(fields[1:], start=1):
            value = float(raw)
            records.append(
                {
                    "year": year,
                    "month": month,
                    "value": None if value <= MISSING_MAXIMUM else value,
                }
            )
    expected_years = set(range(start_year, end_year + 1))
    observed_years = {record["year"] for record in records}
    if observed_years != expected_years:
        raise ValueError("MEI.v2 year rows do not match declared coverage")
    if len(records) != 12 * len(expected_years):
        raise ValueError("each MEI.v2 year must provide twelve slots")
    return records


def parse_meiv2(text: str) -> list[dict]:
    """Backward-compatible, domain-named wrapper for the generic PSL parser."""
    return parse_psl_monthly(text)


def fetch(
    data_path: Path = Path("data/enso/meiv2.data"),
    manifest_path: Path = Path("data/enso/manifest.json"),
) -> Path:
    request = urllib.request.Request(
        DATA_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    text = raw.decode("ascii")
    records = parse_meiv2(text)
    valid = [record for record in records if record["value"] is not None]
    if not valid:
        raise ValueError("MEI.v2 response contains no valid values")

    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema_version": 1,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_url": DATA_URL,
        "documentation_url": DOCUMENTATION_URL,
        "data_path": data_path.as_posix(),
        "sha256": digest,
        "bytes": len(raw),
        "interpretation": "standardized MEI.v2; overlapping bimonthly values stored in monthly slots",
        "first_valid": [valid[0]["year"], valid[0]["month"]],
        "last_valid": [valid[-1]["year"], valid[-1]["month"]],
        "valid_values": len(valid),
        "missing_slots": len(records) - len(valid),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {data_path} (sha256 {digest})")
    print(f"Wrote {manifest_path}")
    return manifest_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/enso/meiv2.data"))
    parser.add_argument("--manifest", type=Path, default=Path("data/enso/manifest.json"))
    arguments = parser.parse_args()
    fetch(arguments.data, arguments.manifest)
