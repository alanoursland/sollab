"""Freeze NOAA PSL's public equatorial Pacific heat-content index."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from fetch_meiv2 import parse_psl_monthly


DATA_URL = "https://psl.noaa.gov/data/correlation/heatcentra.data"
DOCUMENTATION_URL = "https://psl.noaa.gov/data/timeseries/month/DS/HEATCENTRA/"
SOURCE_DATA_URL = "https://psl.noaa.gov/data/gridded/data.godas.html"
USER_AGENT = "sollab-enso-recharge-research"


def fetch(
    data_path: Path = Path("data/enso/heatcentra.data"),
    manifest_path: Path = Path("data/enso/heatcentra_manifest.json"),
) -> Path:
    request = urllib.request.Request(
        DATA_URL,
        headers={"User-Agent": USER_AGENT, "Accept": "text/plain"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    records = parse_psl_monthly(raw.decode("ascii"))
    valid = [record for record in records if record["value"] is not None]
    if not valid:
        raise ValueError("heat-content response contains no valid values")

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
        "interpretation": "equatorial upper-300m mean temperature anomaly, 160E-80W, 1981-2010 climatology, degrees C",
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
    parser.add_argument("--data", type=Path, default=Path("data/enso/heatcentra.data"))
    parser.add_argument("--manifest", type=Path, default=Path("data/enso/heatcentra_manifest.json"))
    arguments = parser.parse_args()
    fetch(arguments.data, arguments.manifest)
