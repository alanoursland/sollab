import unittest

import torch

from aftershock_lab import DTYPE, poisson_deviance
from change_detector_lab import detector_alarms, poisson_deviance_contributions


class ChangeDetectorLabTests(unittest.TestCase):
    def test_deviance_contributions_match_existing_score(self):
        observed = torch.tensor([0.0, 2.0, 7.0], dtype=DTYPE)
        expected = torch.tensor([0.5, 3.0, 4.0], dtype=DTYPE)
        contributions = poisson_deviance_contributions(observed, expected)
        self.assertTrue(torch.all(contributions >= 0.0))
        self.assertAlmostEqual(
            float(contributions.sum()), poisson_deviance(expected, observed)
        )

    def test_stable_stream_has_no_window_alarm(self):
        self.assertEqual(
            detector_alarms([0.0] * 40, "window", 12, 3.0), []
        )


if __name__ == "__main__":
    unittest.main()
