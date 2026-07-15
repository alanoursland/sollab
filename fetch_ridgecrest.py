"""Download the public USGS catalog used by the aftershock experiment."""

from __future__ import annotations

import urllib.parse
import urllib.request
from pathlib import Path


BASE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
QUERY = {
    "format": "csv",
    "starttime": "2019-06-06T03:19:53.040Z",
    "endtime": "2019-08-05T03:19:53.040Z",
    "latitude": "35.7695",
    "longitude": "-117.5993",
    "maxradiuskm": "100",
    "minmagnitude": "2.5",
    "eventtype": "earthquake",
    "orderby": "time-asc",
}


def source_url() -> str:
    return f"{BASE_URL}?{urllib.parse.urlencode(QUERY)}"


def main(destination: Path = Path("data/ridgecrest_aftershocks.csv")) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    url = source_url()
    print(f"Downloading {url}")
    request = urllib.request.Request(url, headers={"User-Agent": "KinoPulse-Playground/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    destination.write_bytes(payload)
    print(f"Wrote {destination} ({destination.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
