"""Freeze NOAA WRIT's active CORe version of the tropical wind index."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


WRIT_ENDPOINT = "https://psl.noaa.gov/cgi-bin/data/atmoswrit/timeseries.proc.pl"
DOCUMENTATION_URL = "https://psl.noaa.gov/data/coreinfo.html"
DATASET_URL = "https://psl.noaa.gov/data/gridded/data.corepublic.html"
USER_AGENT = "sollab-enso-core-wind-bridge"
QUERY = {
    "justGotBACKed": "0",
    "dataset1": "CORe",
    "dataset2": "none",
    "var": "Zonal Wind",
    "level": "850mb",
    "fyear": "1950",
    "fyear2": "2026",
    "season": "0",
    "fmonth": "0",
    "fmonth2": "6",
    "type": "1",
    "climo1yr1": "1981",
    "climo1yr2": "2010",
    "detrend": "0",
    "xlat1": "-5",
    "xlat2": "5",
    "xlon1": "140",
    "xlon2": "190",
    "maskx": "0",
    "map": "0",
    "smooth": "0",
    "runmean": "1",
    "Submit": "Create Plot",
}


def parse_core_csv(text: str) -> list[dict[str, int | float | None]]:
    reader = csv.reader(io.StringIO(text))
    rows = []
    for row in reader:
        if len(row) < 2:
            continue
        try:
            year, month, day = (int(part) for part in row[0].strip().split("-"))
            value = float(row[1])
        except ValueError:
            continue
        if day != 1:
            raise ValueError(f"unexpected monthly timestamp {row[0]!r}")
        rows.append({"year": year, "month": month, "value": None if value <= -90 else value})
    if not rows:
        raise ValueError("CORe CSV contains no monthly records")
    return rows


def extract_csv_url(html: str) -> str:
    match = re.search(r'href=["\'](?P<path>/tmp/[^"\']+\.csv)["\']', html, flags=re.IGNORECASE)
    if match is None:
        raise ValueError("NOAA WRIT response contains no generated CSV link")
    return urllib.parse.urljoin(WRIT_ENDPOINT, match.group("path"))


def _download(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def fetch(
    data_path: Path = Path("data/enso/core_uwnd850_140190.csv"),
    manifest_path: Path = Path("data/enso/core_wind850_manifest.json"),
) -> Path:
    query_url = f"{WRIT_ENDPOINT}?{urllib.parse.urlencode(QUERY)}"
    result_html = _download(query_url).decode("utf-8", errors="replace")
    csv_url = extract_csv_url(result_html)
    raw = _download(csv_url)
    text = raw.decode("utf-8-sig")
    expected_header = "NOAA CORe Zonal Wind (m/s) -5S-5N;140E-190E"
    if expected_header not in text.splitlines()[0]:
        raise ValueError("NOAA WRIT returned an unexpected CORe variable or region")
    records = parse_core_csv(text)
    valid = [record for record in records if record["value"] is not None]
    if not valid:
        raise ValueError("CORe response contains no valid values")

    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    manifest = {
        "schema_version": 1,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "query_url": query_url,
        "documentation_url": DOCUMENTATION_URL,
        "dataset_url": DATASET_URL,
        "data_path": data_path.as_posix(),
        "sha256": digest,
        "bytes": len(raw),
        "interpretation": "monthly CORe 850 mb zonal-wind anomaly, 5S-5N and 140E-170W, 1981-2010 climatology, m/s",
        "first_valid": [valid[0]["year"], valid[0]["month"]],
        "last_valid": [valid[-1]["year"], valid[-1]["month"]],
        "valid_values": len(valid),
        "missing_slots": len(records) - len(valid),
        "temporary_csv_url_recorded": False,
        "archive_role": "active CORe continuation candidate; values must be bridged against R1 before model use",
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {data_path} (sha256 {digest})")
    print(f"Wrote {manifest_path}")
    return manifest_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("data/enso/core_uwnd850_140190.csv"))
    parser.add_argument("--manifest", type=Path, default=Path("data/enso/core_wind850_manifest.json"))
    arguments = parser.parse_args()
    fetch(arguments.data, arguments.manifest)
