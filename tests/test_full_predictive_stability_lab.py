import unittest

from full_predictive_stability_lab import decision, outcome_summary


def target(event_id, alarms, raw_miss, rolling_miss=None, original=False):
    return {
        "event_id": event_id,
        "repeat_alarm_count": alarms,
        "repeat_count": 4,
        "original_alarm": original,
        "raw_interval_miss": raw_miss,
        "rolling_interval_miss": rolling_miss,
    }


class FullPredictiveStabilityLabTests(unittest.TestCase):
    def test_consensus_rules_are_nested(self):
        item = target("x", 3, True)
        self.assertTrue(decision(item, "any_repeat"))
        self.assertTrue(decision(item, "majority"))
        self.assertFalse(decision(item, "unanimous"))

    def test_outcome_summary_accounts_for_rejected_covered_forecasts(self):
        items = [
            target("caught", 4, True),
            target("false", 4, False),
            target("quiet_miss", 0, True),
            target("quiet_covered", 0, False),
        ]
        result = outcome_summary(items, "raw_interval_miss", "unanimous")
        self.assertEqual(result["misses_alarmed"], 1)
        self.assertEqual(result["covered_alarmed"], 1)
        self.assertEqual(result["alarm_precision"], 0.5)
        self.assertEqual(result["quiet_coverage"], 0.5)


if __name__ == "__main__":
    unittest.main()
