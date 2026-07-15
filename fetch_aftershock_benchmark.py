"""Download independent USGS catalogs for aftershock transfer experiments."""

from __future__ import annotations

import hashlib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"


@dataclass(frozen=True)
class SequenceSpec:
    slug: str
    name: str
    event_id: str
    time: str
    latitude: float
    longitude: float
    magnitude: float

    @property
    def origin(self) -> datetime:
        return datetime.fromisoformat(self.time.replace("Z", "+00:00"))


SEQUENCES = (
    SequenceSpec(
        "eureka_2010",
        "Eureka 2010",
        "nc71338066",
        "2010-01-10T00:27:39.320Z",
        40.652,
        -124.6925,
        6.5,
    ),
    SequenceSpec(
        "el_mayor_2010",
        "El Mayor 2010",
        "ci14607652",
        "2010-04-04T22:40:42.360Z",
        32.2861667,
        -115.2953333,
        7.2,
    ),
    SequenceSpec(
        "ridgecrest_2019",
        "Ridgecrest 2019",
        "ci38457511",
        "2019-07-06T03:19:53.040Z",
        35.7695,
        -117.5993333,
        7.1,
    ),
    SequenceSpec(
        "monte_cristo_2020",
        "Monte Cristo 2020",
        "nn00725272",
        "2020-05-15T11:03:27.176Z",
        38.1689,
        -117.8497,
        6.5,
    ),
    SequenceSpec(
        "lone_pine_2020",
        "Lone Pine 2020",
        "ci39493944",
        "2020-06-24T17:40:49.240Z",
        36.4468333,
        -117.9751667,
        5.8,
    ),
    SequenceSpec(
        "antelope_2021",
        "Antelope Valley 2021",
        "nc73584926",
        "2021-07-08T22:49:48.110Z",
        38.5075,
        -119.4998333,
        6.0,
    ),
    SequenceSpec(
        "petrolia_2021",
        "Petrolia 2021",
        "nc73666231",
        "2021-12-20T20:10:31.310Z",
        40.3901667,
        -124.298,
        6.2,
    ),
    SequenceSpec(
        "ferndale_2022",
        "Ferndale 2022",
        "nc73821036",
        "2022-12-20T10:34:24.770Z",
        40.525,
        -124.423,
        6.4,
    ),
)


def source_url(sequence: SequenceSpec) -> str:
    start = sequence.origin - timedelta(days=30)
    end = sequence.origin + timedelta(days=30)
    query = {
        "format": "csv",
        "starttime": start.isoformat(),
        "endtime": end.isoformat(),
        "latitude": str(sequence.latitude),
        "longitude": str(sequence.longitude),
        "maxradiuskm": "100",
        "minmagnitude": "2.5",
        "eventtype": "earthquake",
        "orderby": "time-asc",
    }
    return f"{BASE_URL}?{urllib.parse.urlencode(query)}"


def main(destination: Path = Path("data/aftershock_benchmark")) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for sequence in SEQUENCES:
        url = source_url(sequence)
        print(f"Downloading {sequence.name}: {url}")
        request = urllib.request.Request(
            url, headers={"User-Agent": "KinoPulse-Playground/1.0"}
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read()
        target = destination / f"{sequence.slug}.csv"
        target.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        print(
            f"Wrote {target} ({target.stat().st_size:,} bytes, SHA256 {digest})"
        )


if __name__ == "__main__":
    main()
