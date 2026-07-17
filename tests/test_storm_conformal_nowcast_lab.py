import math
import unittest

import torch

from kinopulse.validation import SplitConformalIntervalCalibrator
from storm_conformal_nowcast_lab import (
    calibration_thresholds,
    causal_forward_fill,
)


class StormConformalNowcastLabTests(unittest.TestCase):
    def test_causal_fill_never_backfills_from_future(self):
        values = torch.tensor([1.0, 999.0, 999.0, 4.0], dtype=torch.float64)
        valid = torch.tensor([True, False, False, True])
        filled, filled_valid, ages = causal_forward_fill(values, valid, maximum_age_hours=1)
        self.assertEqual(float(filled[1]), 1.0)
        self.assertTrue(bool(filled_valid[1]))
        self.assertFalse(bool(filled_valid[2]))
        self.assertEqual(int(ages[2]), -1)
        self.assertEqual(float(filled[3]), 4.0)

    def test_zero_age_policy_preserves_only_observed_values(self):
        values = torch.tensor([2.0, 999.0, 3.0], dtype=torch.float64)
        valid = torch.tensor([True, False, True])
        _, filled_valid, ages = causal_forward_fill(values, valid, maximum_age_hours=0)
        self.assertTrue(torch.equal(filled_valid, valid))
        self.assertEqual(ages.tolist(), [0, -1, 0])

    def test_calibration_thresholds_use_conservative_order_statistics(self):
        thresholds = calibration_thresholds([5.0, 1.0, 4.0, 2.0, 3.0])
        self.assertEqual(thresholds, {"median": 3.0, "eighty_percent": 4.0, "maximum": 5.0})

    def test_five_group_eighty_percent_radius_is_largest_score(self):
        scores = [4.0, 1.0, 3.0, 2.0, 5.0]
        result = SplitConformalIntervalCalibrator(
            coverage=0.8,
            mode="joint",
            group_ids=list("abcde"),
        ).fit(lower=[0.0] * 5, upper=[0.0] * 5, observed=scores)
        self.assertTrue(result.supported)
        self.assertEqual(result.joint_rank, 5)
        self.assertTrue(math.isclose(result.joint_correction, 5.0))


if __name__ == "__main__":
    unittest.main()
