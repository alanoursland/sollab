"""Build a reproducible, model-blind USGS aftershock population.

The screen deliberately uses only catalog geometry, timing, and event counts.
No fitted-model score participates in deciding which sequences survive.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from fetch_aftershock_benchmark import BASE_URL, SequenceSpec, source_url


CANDIDATE_QUERY = {
    "format": "geojson",
    "starttime": "2010-01-01",
    "endtime": "2026-01-01",
    "minlatitude": "30",
    "maxlatitude": "50",
    "minlongitude": "-130",
    "maxlongitude": "-100",
    "minmagnitude": "5.8",
    "eventtype": "earthquake",
    "orderby": "time-asc",
    "limit": "20000",
}
OVERLAP_DAYS = 45.0
OVERLAP_KM = 150.0
MIN_CALIBRATION_EVENTS = 15
MIN_EVALUATION_EVENTS = 15
MIN_TIME_DAYS = 1.0 / 24.0
CALIBRATION_END_DAYS = 1.0
MAX_TIME_DAYS = 30.0


@dataclass(frozen=True)
class Candidate:
    event_id: str
    time: str
    latitude: float
    longitude: float
    depth_km: float
    magnitude: float
    place: str

    @property
    def origin(self) -> datetime:
        return datetime.fromisoformat(self.time.replace("Z", "+00:00"))


def candidate_url() -> str:
    return f"{BASE_URL}?{urllib.parse.urlencode(CANDIDATE_QUERY)}"


def great_circle_km(first: Candidate, second: Candidate) -> float:
    radius_km = 6371.0088
    lat1, lat2 = map(math.radians, (first.latitude, second.latitude))
    delta_lat = lat2 - lat1
    delta_lon = math.radians(second.longitude - first.longitude)
    haversine = (
        math.sin(delta_lat / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    return 2.0 * radius_km * math.asin(math.sqrt(haversine))


def independent_candidates(
    candidates: list[Candidate],
) -> tuple[list[Candidate], dict[str, str]]:
    """Keep the largest event in every overlapping space-time neighborhood."""
    retained: list[Candidate] = []
    rejected: dict[str, str] = {}
    ranked = sorted(candidates, key=lambda item: (-item.magnitude, item.origin))
    for candidate in ranked:
        conflicts = [
            selected
            for selected in retained
            if abs((candidate.origin - selected.origin).total_seconds())
            <= OVERLAP_DAYS * 86400.0
            and great_circle_km(candidate, selected) <= OVERLAP_KM
        ]
        if conflicts:
            winner = min(
                conflicts,
                key=lambda item: (
                    abs((candidate.origin - item.origin).total_seconds()),
                    -item.magnitude,
                ),
            )
            rejected[candidate.event_id] = (
                f"overlaps {winner.event_id} (M{winner.magnitude:.2f}) within "
                f"{OVERLAP_DAYS:g} days and {OVERLAP_KM:g} km"
            )
        else:
            retained.append(candidate)
    return sorted(retained, key=lambda item: item.origin), rejected


def parse_candidates(payload: bytes) -> list[Candidate]:
    document = json.loads(payload)
    candidates = []
    for feature in document["features"]:
        properties = feature["properties"]
        longitude, latitude, depth = feature["geometry"]["coordinates"]
        timestamp = datetime.fromtimestamp(
            properties["time"] / 1000.0, timezone.utc
        ).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        candidates.append(
            Candidate(
                event_id=feature["id"],
                time=timestamp,
                latitude=latitude,
                longitude=longitude,
                depth_km=depth,
                magnitude=properties["mag"],
                place=properties["place"],
            )
        )
    return candidates


def sequence_spec(candidate: Candidate) -> SequenceSpec:
    label = re.sub(r"[^a-z0-9]+", "_", candidate.place.lower()).strip("_")
    slug = f"{candidate.origin.year}_{candidate.event_id}_{label[:36]}"
    return SequenceSpec(
        slug=slug,
        name=f"{candidate.origin.year} {candidate.place}",
        event_id=candidate.event_id,
        time=candidate.time,
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        magnitude=candidate.magnitude,
    )


def catalog_counts(payload: bytes, candidate: Candidate) -> dict[str, int]:
    rows = list(csv.DictReader(payload.decode("utf-8").splitlines()))
    calibration = evaluation = control = 0
    for row in rows:
        if row["id"] == candidate.event_id:
            continue
        event_time = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        days = (event_time - candidate.origin).total_seconds() / 86400.0
        control += -30.0 <= days < -2.0
        calibration += MIN_TIME_DAYS <= days <= CALIBRATION_END_DAYS
        evaluation += CALIBRATION_END_DAYS < days <= MAX_TIME_DAYS
    return {
        "source_rows": len(rows),
        "control_events": control,
        "calibration_events": calibration,
        "evaluation_events": evaluation,
    }


def download(url: str) -> bytes:
    request = urllib.request.Request(
        url, headers={"User-Agent": "KinoPulse-Playground/1.0"}
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()


def main(destination: Path = Path("data/aftershock_population")) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    query = candidate_url()
    print(f"Downloading candidate catalog: {query}")
    candidate_payload = download(query)
    candidates = parse_candidates(candidate_payload)
    independent, overlap_rejections = independent_candidates(candidates)
    records = []
    selected_count = 0
    for index, candidate in enumerate(independent, start=1):
        spec = sequence_spec(candidate)
        url = source_url(spec)
        print(f"[{index}/{len(independent)}] {spec.name}")
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
        "candidate_url": query,
        "candidate_sha256": hashlib.sha256(candidate_payload).hexdigest(),
        "policy": {
            "overlap_days": OVERLAP_DAYS,
            "overlap_km": OVERLAP_KM,
            "minimum_calibration_events": MIN_CALIBRATION_EVENTS,
            "minimum_evaluation_events": MIN_EVALUATION_EVENTS,
            "calibration_window_days": [MIN_TIME_DAYS, CALIBRATION_END_DAYS],
            "evaluation_window_days": [CALIBRATION_END_DAYS, MAX_TIME_DAYS],
        },
        "candidate_count": len(candidates),
        "selected_count": selected_count,
        "records": records,
    }
    target = destination / "manifest.json"
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Selected {selected_count}/{len(candidates)} candidates; wrote {target}")


if __name__ == "__main__":
    main()
