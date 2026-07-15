import csv
import io
import unittest

from fetch_aftershock_population import (
    Candidate,
    catalog_counts,
    great_circle_km,
    independent_candidates,
    sequence_spec,
)


def candidate(event_id, time, latitude=40.0, longitude=-120.0, magnitude=6.0):
    return Candidate(
        event_id,
        time,
        latitude,
        longitude,
        10.0,
        magnitude,
        "10 km W of Test Place",
    )


class AftershockPopulationFetchTests(unittest.TestCase):
    def test_great_circle_distance(self):
        first = candidate("a", "2020-01-01T00:00:00.000Z", longitude=-120.0)
        second = candidate("b", "2020-01-01T00:00:00.000Z", longitude=-119.0)
        self.assertAlmostEqual(great_circle_km(first, second), 85.18, places=1)

    def test_largest_overlapping_event_survives(self):
        smaller = candidate("small", "2020-01-01T00:00:00.000Z", magnitude=6.0)
        larger = candidate("large", "2020-01-02T00:00:00.000Z", magnitude=7.0)
        distant = candidate(
            "distant", "2020-01-02T00:00:00.000Z", longitude=-110.0
        )
        selected, rejected = independent_candidates([smaller, larger, distant])
        self.assertEqual({item.event_id for item in selected}, {"large", "distant"})
        self.assertIn("large", rejected["small"])

    def test_catalog_windows_exclude_mainshock(self):
        mainshock = candidate("main", "2020-01-01T00:00:00.000Z")
        rows = [
            ("2019-12-10T00:00:00.000Z", "control"),
            ("2020-01-01T00:00:00.000Z", "main"),
            ("2020-01-01T12:00:00.000Z", "early"),
            ("2020-01-03T00:00:00.000Z", "late"),
        ]
        stream = io.StringIO()
        writer = csv.DictWriter(stream, fieldnames=["time", "id"])
        writer.writeheader()
        for time, event_id in rows:
            writer.writerow({"time": time, "id": event_id})
        counts = catalog_counts(stream.getvalue().encode(), mainshock)
        self.assertEqual(counts["control_events"], 1)
        self.assertEqual(counts["calibration_events"], 1)
        self.assertEqual(counts["evaluation_events"], 1)

    def test_slug_is_stable_and_safe(self):
        item = candidate("us123", "2020-01-01T00:00:00.000Z")
        self.assertEqual(
            sequence_spec(item).slug, "2020_us123_10_km_w_of_test_place"
        )


if __name__ == "__main__":
    unittest.main()
