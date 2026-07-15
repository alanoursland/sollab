"""Download the public NASA OMNI files used by the space-weather exhibit."""

from __future__ import annotations

import urllib.request
from pathlib import Path


BASE_URL = "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni"
FILES = ("omni2_2015.dat", "omni2.text")


def main(destination: Path = Path("data/omni")) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = destination / name
        print(f"Downloading {BASE_URL}/{name}")
        urllib.request.urlretrieve(f"{BASE_URL}/{name}", target)
        print(f"Wrote {target} ({target.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
