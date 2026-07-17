import tempfile
import unittest
from pathlib import Path

from magnitude_time_coupling_lab import (
    conditional_exchangeability_test,
    load_marked_events,
    sequence_mark_summary,
)


class MagnitudeTimeCouplingLabTests(unittest.TestCase):
    def test_loader_enforces_target_floor_finiteness_and_time_window(self):
        record = {
            "slug": "target",
            "event_id": "main",
            "time": "2020-01-31T00:00:00Z",
        }
        csv_text = "\n".join(
            [
                "time,latitude,longitude,depth,mag,magType,nst,gap,dmin,rms,net,id,updated,place,type,horizontalError,depthError,magError,magNst,status,locationSource,magSource",
                "2020-01-01T00:00:00Z,0,0,1,3.2,ml,,,,,us,control,,,,,,,,,,",
                "2020-01-31T00:00:00Z,0,0,1,6.0,mw,,,,,us,main,,,,,,,,,,",
                "2020-01-31T00:30:00Z,0,0,1,3.1,ml,,,,,us,too-early,,,,,,,,,,",
                "2020-01-31T02:00:00Z,0,0,1,2.6,ml,,,,,us,early,,,,,,,,,,",
                "2020-02-02T00:00:00Z,0,0,1,3.1,ml,,,,,us,late,,,,,,,,,,",
                "2020-02-03T00:00:00Z,0,0,1,2.4,ml,,,,,us,below-floor,,,,,,,,,,",
                "2020-02-04T00:00:00Z,0,0,1,nan,ml,,,,,us,nonfinite,,,,,,,,,,",
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "target.csv").write_text(csv_text, encoding="utf-8")
            times, magnitudes = load_marked_events(Path(directory), record)
        self.assertEqual(len(times), 2)
        self.assertEqual(magnitudes, [2.6, 3.1])

    def test_equal_mark_fractions_are_neutral(self):
        summary = sequence_mark_summary(
            "neutral",
            "neutral",
            [0.1, 0.2, 2.0, 3.0],
            [3.2, 2.7, 3.3, 2.8],
            3.0,
        )
        self.assertAlmostEqual(summary["early_enrichment_z"], 0.0)
        self.assertAlmostEqual(summary["late_to_early_odds_ratio"], 1.0)
        self.assertAlmostEqual(summary["late_minus_early_fraction"], 0.0)

    def test_late_enrichment_has_negative_early_z_and_large_odds_ratio(self):
        summary = sequence_mark_summary(
            "late",
            "late",
            [0.1, 0.2, 0.3, 2.0, 3.0, 4.0],
            [2.5, 2.6, 2.7, 3.1, 3.2, 3.3],
            3.0,
        )
        self.assertLess(summary["early_enrichment_z"], 0.0)
        self.assertGreater(summary["late_to_early_odds_ratio"], 1.0)
        self.assertGreater(summary["late_minus_early_fraction"], 0.0)

    def test_conditional_test_is_seed_reproducible(self):
        summaries = [
            sequence_mark_summary(
                str(index),
                str(index),
                [0.1, 0.2, 0.3, 2.0, 3.0, 4.0],
                magnitudes,
                3.0,
            )
            for index, magnitudes in enumerate(
                (
                    [2.5, 2.6, 2.7, 3.1, 3.2, 3.3],
                    [3.1, 2.6, 2.7, 3.2, 2.8, 3.3],
                )
            )
        ]
        first = conditional_exchangeability_test(summaries, samples=512, seed=9)
        second = conditional_exchangeability_test(summaries, samples=512, seed=9)
        self.assertEqual(first, second)
        self.assertGreater(first["heterogeneity_monte_carlo_p"], 0.0)
        self.assertLessEqual(first["heterogeneity_monte_carlo_p"], 1.0)

    def test_degenerate_all_high_sequence_is_visible_but_ineligible(self):
        summary = sequence_mark_summary(
            "all-high",
            "all-high",
            [0.1, 0.2, 2.0, 3.0],
            [3.2, 3.3, 3.4, 3.5],
            3.0,
        )
        self.assertFalse(summary["eligible_for_conditional_test"])
        self.assertIsNone(summary["early_enrichment_z"])
        self.assertEqual(summary["high_total"], 4)


if __name__ == "__main__":
    unittest.main()
