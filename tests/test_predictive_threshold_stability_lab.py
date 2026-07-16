import unittest

from predictive_threshold_stability_lab import (
    coefficient_of_variation,
    summarize_target,
)


class PredictiveThresholdStabilityLabTests(unittest.TestCase):
    def test_zero_variability_has_zero_coefficient(self):
        self.assertEqual(coefficient_of_variation([4.0, 4.0, 4.0]), 0.0)

    def test_mixed_repeat_classification_is_explicitly_unstable(self):
        target = {
            "event_id": "us10004x1w",
            "name": "synthetic",
            "predictive_threshold": 10.0,
            "predictive_alarm": True,
        }
        repeats = [
            {
                "threshold": threshold,
                "proposal_effective_sample_size": 100.0,
                "alarm": alarm,
                "first_alarm_day": 5.0 if alarm else None,
            }
            for threshold, alarm in ((8.0, True), (12.0, False), (9.0, True))
        ]
        result = summarize_target(target, repeats)
        self.assertEqual(result["repeat_alarm_count"], 2)
        self.assertFalse(result["classification_stable"])
        self.assertFalse(result["classification_matches_original_in_every_repeat"])


if __name__ == "__main__":
    unittest.main()
