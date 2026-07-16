import unittest

from japan_transfer_lab import summarize_transfer


def fold(event_id, alarms, miss, cv=0.1):
    return {
        "event_id": event_id,
        "repeat_alarm_count": alarms,
        "repeat_count": 4,
        "raw_interval_miss": miss,
        "threshold_coefficient_of_variation": cv,
        "predictive_distribution": {"bin_coverage": 0.8},
    }


class JapanTransferLabTests(unittest.TestCase):
    def test_unanimity_is_primary_summary(self):
        result = summarize_transfer(
            [fold("caught", 4, True), fold("partial", 3, True), fold("quiet", 0, False)]
        )
        unanimous = result["unanimous_against_raw_intervals"]
        self.assertEqual(unanimous["alarmed"], 1)
        self.assertEqual(unanimous["misses_alarmed"], 1)
        self.assertEqual(unanimous["covered_alarmed"], 0)
        self.assertEqual(result["repeat_alarm_frequency_counts"]["3"], 1)

    def test_coverage_counts_every_fold(self):
        result = summarize_transfer([fold("a", 0, False), fold("b", 0, True)])
        self.assertEqual(result["raw_total_intervals_covered"], 1)
        self.assertEqual(result["raw_total_interval_coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
