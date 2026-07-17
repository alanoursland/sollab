import unittest
from datetime import datetime, timezone

from catalog_magnitude_support_lab import quantile, window_counts


class CatalogMagnitudeSupportLabTests(unittest.TestCase):
    def test_quantile_interpolates_endpoints_and_middle(self):
        values = [1.0, 3.0, 5.0]
        self.assertEqual(quantile(values, 0.0), 1.0)
        self.assertEqual(quantile(values, 0.5), 3.0)
        self.assertEqual(quantile(values, 1.0), 5.0)

    def test_window_counts_reapplies_magnitude_floor(self):
        rows = [
            {"id": "target", "time": "2020-01-01T00:00:00Z", "mag": "6.0"},
            {"id": "small", "time": "2020-01-01T12:00:00Z", "mag": "3.9"},
            {"id": "cal", "time": "2020-01-01T18:00:00Z", "mag": "4.0"},
            {"id": "eval", "time": "2020-01-03T00:00:00Z", "mag": "4.1"},
        ]
        origin = datetime(2020, 1, 1, tzinfo=timezone.utc)
        calibration, evaluation = window_counts(rows, origin, "target", 4.0)
        self.assertEqual(calibration, 1)
        self.assertEqual(evaluation, 1)


if __name__ == "__main__":
    unittest.main()
