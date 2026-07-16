"""Fetch temporally and geographically external USGS aftershock cohorts.

Selection rules intentionally match ``fetch_aftershock_population.py``.  The
2026 temporal cohort is evaluated first; the Alaska/Gulf cohort is a separately
labelled geographic fallback when the temporal screen contains no usable
sequence.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from fetch_aftershock_benchmark import BASE_URL, source_url
from fetch_aftershock_population import (
    MAX_TIME_DAYS,
    MIN_CALIBRATION_EVENTS,
    MIN_EVALUATION_EVENTS,
    MIN_TIME_DAYS,
    OVERLAP_DAYS,
    OVERLAP_KM,
    CALIBRATION_END_DAYS,
    Candidate,
    catalog_counts,
    download,
    independent_candidates,
    parse_candidates,
    sequence_spec,
)


@dataclass(frozen=True)
class ExternalCohort:
    slug: str
    role: str
    query: dict[str, str]

    @property
    def candidate_url(self) -> str:
        return f"{BASE_URL}?{urllib.parse.urlencode(self.query)}"


COMMON_QUERY = {
    "format": "geojson",
    "minmagnitude": "5.8",
    "eventtype": "earthquake",
    "orderby": "time-asc",
    "limit": "20000",
}

TEMPORAL_2026 = ExternalCohort(
    slug="temporal_2026",
    role=(
        "temporally unseen western North America cohort; exact end date leaves "
        "at least 30 days of follow-up at protocol freeze"
    ),
    query={
        **COMMON_QUERY,
        "starttime": "2026-01-01",
        "endtime": "2026-06-15",
        "minlatitude": "30",
        "maxlatitude": "50",
        "minlongitude": "-130",
        "maxlongitude": "-100",
    },
)

ALASKA_2010_2025 = ExternalCohort(
    slug="alaska_2010_2025",
    role=(
        "geographically external Alaska, Aleutian, Gulf of Alaska, and adjacent "
        "north Pacific North America sector"
    ),
    query={
        **COMMON_QUERY,
        "starttime": "2010-01-01",
        "endtime": "2026-01-01",
        "minlatitude": "50",
        "maxlatitude": "72",
        "minlongitude": "-180",
        "maxlongitude": "-130",
    },
)

COHORTS = (TEMPORAL_2026, ALASKA_2010_2025)


def console_safe(value: str, encoding: str | None = None) -> str:
    """Escape unsupported place-name characters without changing source data."""
    target_encoding = encoding or sys.stdout.encoding or "utf-8"
    return value.encode(target_encoding, errors="backslashreplace").decode(
        target_encoding
    )


def fetch_cohort(cohort: ExternalCohort, destination: Path) -> dict:
    destination.mkdir(parents=True, exist_ok=True)
    query = cohort.candidate_url
    print(f"Downloading {cohort.slug} candidate catalog: {query}")
    candidate_payload = download(query)
    candidates = parse_candidates(candidate_payload)
    independent, overlap_rejections = independent_candidates(candidates)
    records = []
    selected_count = 0
    for index, candidate in enumerate(independent, start=1):
        spec = sequence_spec(candidate)
        url = source_url(spec)
        print(
            f"[{cohort.slug} {index}/{len(independent)}] "
            f"{console_safe(spec.name)}"
        )
        payload = download(url)
        counts = catalog_counts(payload, candidate)
        reasons = []
        if counts["calibration_events"] < MIN_CALIBRATION_EVENTS:
            reasons.append(
                f"fewer than {MIN_CALIBRATION_EVENTS} calibration events"
            )
        if counts["evaluation_events"] < MIN_EVALUATION_EVENTS:
            reasons.append(
                f"fewer than {MIN_EVALUATION_EVENTS} evaluation events"
            )
        selected = not reasons
        if selected:
            (destination / f"{spec.slug}.csv").write_bytes(payload)
            selected_count += 1
        records.append(
            {
                **asdict(candidate),
                "slug": spec.slug,
                "name": spec.name,
                **counts,
                "selected": selected,
                "rejection_reason": "; ".join(reasons) or None,
                "catalog_url": url,
                "catalog_sha256": hashlib.sha256(payload).hexdigest(),
            }
        )

    for candidate in candidates:
        if candidate.event_id not in overlap_rejections:
            continue
        records.append(
            {
                **asdict(candidate),
                "slug": sequence_spec(candidate).slug,
                "name": sequence_spec(candidate).name,
                "selected": False,
                "rejection_reason": overlap_rejections[candidate.event_id],
            }
        )
    records.sort(key=lambda item: item["time"])
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "cohort": cohort.slug,
        "role": cohort.role,
        "candidate_url": query,
        "candidate_sha256": hashlib.sha256(candidate_payload).hexdigest(),
        "policy": {
            "overlap_days": OVERLAP_DAYS,
            "overlap_km": OVERLAP_KM,
            "catalog_radius_km": 100,
            "catalog_minimum_magnitude": 2.5,
            "minimum_calibration_events": MIN_CALIBRATION_EVENTS,
            "minimum_evaluation_events": MIN_EVALUATION_EVENTS,
            "calibration_window_days": [MIN_TIME_DAYS, CALIBRATION_END_DAYS],
            "evaluation_window_days": [CALIBRATION_END_DAYS, MAX_TIME_DAYS],
        },
        "candidate_count": len(candidates),
        "independent_candidate_count": len(independent),
        "selected_count": selected_count,
        "records": records,
    }
    target = destination / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(
        f"{cohort.slug}: selected {selected_count}/{len(candidates)} raw "
        f"candidates; wrote {target}"
    )
    return manifest


def main(root: Path = Path("data/aftershock_external")) -> None:
    for cohort in COHORTS:
        fetch_cohort(cohort, root / cohort.slug)


if __name__ == "__main__":
    main()
