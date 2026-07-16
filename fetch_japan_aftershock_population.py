"""Fetch a second untouched geographic aftershock cohort from USGS."""

from __future__ import annotations

from pathlib import Path

from fetch_external_aftershock_population import (
    COMMON_QUERY,
    ExternalCohort,
    fetch_cohort,
)


JAPAN_KURIL_2016_2025 = ExternalCohort(
    slug="japan_kuril_2016_2025",
    role=(
        "second geographically external Japan, Kuril, and adjacent northwest "
        "Pacific cohort; frozen before catalog outcomes were downloaded"
    ),
    query={
        **COMMON_QUERY,
        "starttime": "2016-01-01",
        "endtime": "2026-01-01",
        "minlatitude": "30",
        "maxlatitude": "50",
        "minlongitude": "125",
        "maxlongitude": "150",
    },
)


def main(root: Path = Path("data/aftershock_external")) -> None:
    fetch_cohort(JAPAN_KURIL_2016_2025, root / JAPAN_KURIL_2016_2025.slug)


if __name__ == "__main__":
    main()
