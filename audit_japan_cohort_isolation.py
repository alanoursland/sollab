"""Audit selected Japan/Kuril targets for rectangular cohort-edge leakage."""

from __future__ import annotations

import hashlib
import json
import urllib.parse
from dataclasses import asdict
from datetime import timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from fetch_aftershock_benchmark import BASE_URL
from fetch_aftershock_population import (
    OVERLAP_DAYS,
    OVERLAP_KM,
    Candidate,
    download,
    great_circle_km,
    parse_candidates,
)


MANIFEST = Path("data/aftershock_external/japan_kuril_2016_2025/manifest.json")
OUTPUT = Path("artifacts/japan_cohort_isolation_audit.json")
PLOT = Path("artifacts/japan_cohort_isolation_audit.png")


def priority_key(candidate: Candidate) -> tuple[float, object]:
    """Match the population screen: larger magnitude, then earlier origin."""
    return -candidate.magnitude, candidate.origin


def stronger_neighbor(target: Candidate, neighbors: list[Candidate]) -> Candidate | None:
    """Return the highest-priority local event that would precede the target."""
    eligible = [
        neighbor
        for neighbor in neighbors
        if neighbor.event_id != target.event_id
        and abs((neighbor.origin - target.origin).total_seconds())
        <= OVERLAP_DAYS * 86400.0
        and great_circle_km(target, neighbor) <= OVERLAP_KM
        and priority_key(neighbor) < priority_key(target)
    ]
    return min(eligible, key=priority_key) if eligible else None


def neighborhood_url(target: Candidate) -> str:
    start = target.origin - timedelta(days=OVERLAP_DAYS)
    end = target.origin + timedelta(days=OVERLAP_DAYS)
    query = {
        "format": "geojson",
        "starttime": start.isoformat(),
        "endtime": end.isoformat(),
        "latitude": f"{target.latitude:.8g}",
        "longitude": f"{target.longitude:.8g}",
        "maxradiuskm": f"{OVERLAP_KM:g}",
        "minmagnitude": "5.8",
        "eventtype": "earthquake",
        "orderby": "time-asc",
        "limit": "20000",
    }
    return f"{BASE_URL}?{urllib.parse.urlencode(query)}"


def inside_rectangle(candidate: Candidate, bounds: dict[str, float]) -> bool:
    return (
        bounds["minlatitude"] <= candidate.latitude <= bounds["maxlatitude"]
        and bounds["minlongitude"] <= candidate.longitude <= bounds["maxlongitude"]
    )


def audit_isolation(manifest_path: Path = MANIFEST) -> dict:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    cohort = manifest.get("cohort", manifest_path.parent.name)
    candidate_query = urllib.parse.parse_qs(
        urllib.parse.urlparse(manifest["candidate_url"]).query
    )
    bounds = {
        key: float(candidate_query[key][0])
        for key in ("minlatitude", "maxlatitude", "minlongitude", "maxlongitude")
    }
    selected = [record for record in manifest["records"] if record["selected"]]
    catalog_radius_km = float(manifest.get("policy", {}).get("catalog_radius_km", 100.0))
    records = []
    for index, record in enumerate(selected, start=1):
        target = Candidate(
            event_id=record["event_id"],
            time=record["time"],
            latitude=record["latitude"],
            longitude=record["longitude"],
            depth_km=record["depth_km"],
            magnitude=record["magnitude"],
            place=record["place"],
        )
        url = neighborhood_url(target)
        print(f"[{index}/{len(selected)}] {target.event_id} boundary-free neighborhood")
        payload = download(url)
        neighbors = parse_candidates(payload)
        stronger = stronger_neighbor(target, neighbors)
        records.append(
            {
                "event_id": target.event_id,
                "name": record["name"],
                "time": target.time,
                "magnitude": target.magnitude,
                "latitude": target.latitude,
                "longitude": target.longitude,
                "neighborhood_url": url,
                "neighborhood_sha256": hashlib.sha256(payload).hexdigest(),
                "neighborhood_candidate_count": len(neighbors),
                "passes_boundary_free_priority": stronger is None,
                "higher_priority_neighbor": (
                    None
                    if stronger is None
                    else {
                        **asdict(stronger),
                        "distance_km": great_circle_km(target, stronger),
                        "inside_target_catalog_radius": (
                            great_circle_km(target, stronger) <= catalog_radius_km
                        ),
                        "time_difference_days": (
                            stronger.origin - target.origin
                        ).total_seconds()
                        / 86400.0,
                        "inside_original_rectangle": inside_rectangle(stronger, bounds),
                    }
                ),
            }
        )
    failures = [record for record in records if not record["passes_boundary_free_priority"]]
    return {
        "experiment": f"boundary-free isolation audit of selected {cohort} targets",
        "cohort": cohort,
        "claim_boundary": (
            "post-selection protocol audit; it diagnoses rectangular candidate-query "
            "edge leakage and does not redefine the original frozen cohort"
        ),
        "source_candidate_sha256": manifest["candidate_sha256"],
        "original_bounds": bounds,
        "audit_policy": {
            "radius_km": OVERLAP_KM,
            "window_days_before_and_after": OVERLAP_DAYS,
            "minimum_magnitude": 5.8,
            "priority": "larger magnitude, then earlier origin",
            "rectangle_clipping": False,
            "target_catalog_radius_km": catalog_radius_km,
        },
        "summary": {
            "selected_targets": len(records),
            "passes_boundary_free_priority": len(records) - len(failures),
            "fails_boundary_free_priority": len(failures),
            "failed_event_ids": [record["event_id"] for record in failures],
            "failures_caused_by_outside_rectangle_neighbor": sum(
                not record["higher_priority_neighbor"]["inside_original_rectangle"]
                for record in failures
            ),
            "failures_with_neighbor_inside_target_catalog_radius": sum(
                record["higher_priority_neighbor"]["inside_target_catalog_radius"]
                for record in failures
            ),
        },
        "records": records,
    }


def plot_isolation_audit(report: dict, output_path: Path = PLOT) -> None:
    records = report["records"]
    failure = next(
        record for record in records if not record["passes_boundary_free_priority"]
    )
    neighbor = failure["higher_priority_neighbor"]
    bounds = report["original_bounds"]
    fig, (cohort_axis, detail_axis) = plt.subplots(
        1, 2, figsize=(13, 5.5), constrained_layout=True
    )
    fig.patch.set_facecolor("white")

    cohort_axis.scatter(
        [record["longitude"] for record in records],
        [record["latitude"] for record in records],
        color=[
            "#0984e3" if record["passes_boundary_free_priority"] else "#d63031"
            for record in records
        ],
        s=55,
    )
    cohort_axis.axhline(bounds["minlatitude"], color="#2d3436", linestyle="--")
    cohort_axis.set(
        xlim=(bounds["minlongitude"], bounds["maxlongitude"]),
        ylim=(bounds["minlatitude"] - 1.0, bounds["maxlatitude"]),
        xlabel="longitude (degrees E)",
        ylabel="latitude (degrees N)",
        title="Selected targets and the rectangular south edge",
    )
    cohort_axis.scatter([], [], color="#0984e3", label="passes boundary-free audit")
    cohort_axis.scatter([], [], color="#d63031", label="fails audit")
    cohort_axis.legend(frameon=False)
    cohort_axis.grid(alpha=0.2)

    detail_axis.scatter(
        [failure["longitude"]],
        [failure["latitude"]],
        s=110,
        color="#d63031",
        label=f"selected {failure['event_id']} M{failure['magnitude']}",
        zorder=3,
    )
    detail_axis.scatter(
        [neighbor["longitude"]],
        [neighbor["latitude"]],
        s=110,
        marker="^",
        color="#6c5ce7",
        label=f"earlier {neighbor['event_id']} M{neighbor['magnitude']}",
        zorder=3,
    )
    detail_axis.plot(
        [failure["longitude"], neighbor["longitude"]],
        [failure["latitude"], neighbor["latitude"]],
        color="#636e72",
        linestyle=":",
    )
    detail_axis.axhline(
        bounds["minlatitude"], color="#2d3436", linestyle="--", label="candidate boundary"
    )
    detail_axis.text(
        0.03,
        0.04,
        f"{abs(neighbor['time_difference_days']):.2f} days earlier\n"
        f"{neighbor['distance_km']:.1f} km away",
        transform=detail_axis.transAxes,
        bbox={"facecolor": "white", "alpha": 0.85, "edgecolor": "#b2bec3"},
    )
    detail_axis.set(
        xlim=(139.6, 140.3),
        ylim=(29.65, 30.3),
        xlabel="longitude (degrees E)",
        ylabel="latitude (degrees N)",
        title="The sole alarm is a cohort-edge leak",
    )
    detail_axis.legend(frameon=False, fontsize=8)
    detail_axis.grid(alpha=0.2)
    fig.suptitle("Boundary-free isolation audit of the Japan/Kuril transfer cohort")
    fig.savefig(output_path, dpi=180, facecolor="white")
    plt.close(fig)


def main(output_path: Path = OUTPUT, plot_path: Path = PLOT) -> None:
    report = audit_isolation()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    plot_isolation_audit(report, plot_path)
    print(json.dumps(report["summary"], indent=2))
    for record in report["records"]:
        if record["passes_boundary_free_priority"]:
            continue
        neighbor = record["higher_priority_neighbor"]
        print(
            record["event_id"],
            "loses to",
            neighbor["event_id"],
            f"M{neighbor['magnitude']}",
            f"{neighbor['time_difference_days']:.2f} days",
            f"{neighbor['distance_km']:.1f} km",
            f"inside_rectangle={neighbor['inside_original_rectangle']}",
        )


if __name__ == "__main__":
    main()
