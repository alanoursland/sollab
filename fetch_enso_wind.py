"""Freeze NOAA PSL's western tropical Pacific 850 mb zonal-wind index."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fetch_meiv2 import parse_psl_monthly


DATA_URL = "https://psl.noaa.gov/data/correlation/uwnd.850.140190.data"
DOCUMENTATION_URL = "https://psl.noaa.gov/enso/dashboard.lanina.html"
SOURCE_DATA_URL = "https://psl.noaa.gov/data/gridded/data.ncep.reanalysis.html"
USER_AGENT = "sollab-enso-wind-heat-research"


def fetch(
    data_path: Path = Path("data/enso/uwnd.850.140190.data"),
    manifest_path: Path = Path("data/enso/wind850_manifest.json"),
) -> Path:
    request = urllib.request.Request(DATA_URL, headers={"User-Agent": USER_AGENT, "Accept": "text/plain"})
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    records = parse_psl_monthly(raw.decode("ascii"))
    valid = [record for record in records if record["value"] is not None]
    if not valid:
        raise ValueError("wind response contains no valid values")

    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema_version": 1,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "data_url": DATA_URL,
        "documentation_url": DOCUMENTATION_URL,
        "source_data_url": SOURCE_DATA_URL,
        "data_path": data_path.as_posix(),
        "sha256": digest,
        "bytes": len(raw),
        "interpretation": "monthly 850 mb zonal-wind anomaly, 5S-5N and 140E-170W, 1981-2010 climatology, m/s",
        "first_valid": [valid[0]["year"], valid[0]["month"]],
        "last_valid": [valid[-1]["year"], valid[-1]["month"]],
        "valid_values": len(valid),
        "missing_slots": len(records) - len(valid),
        "archive_boundary": "NCEP/NCAR Reanalysis 1 production ended in 2026; the frozen index is not a continuing live forcing feed.",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {data_path} (sha256 {digest})")
    print(f"Wrote {manifest_path}")
    return manifest_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/enso/uwnd.850.140190.data"))
    parser.add_argument("--manifest", type=Path, default=Path("data/enso/wind850_manifest.json"))
    arguments = parser.parse_args()
    fetch(arguments.data, arguments.manifest)
