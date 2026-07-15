import math
import unittest

import torch

from aftershock_lab import DTYPE
from sequential_regime_lab import monte_carlo_threshold, tail_scale_scan


class SequentialRegimeLabTests(unittest.TestCase):
    def test_tail_scan_localizes_persistent_rate_change(self):
        expected = torch.full((18,), 10.0, dtype=DTYPE)
        counts = expected.clone()
        counts[8:] = 30.0
        statistics, splits = tail_scale_scan(counts, expected)
        self.assertGreater(float(statistics[-1]), 50.0)
        self.assertEqual(int(splits[-1]), 8)

    def test_batch_and_single_scan_agree(self):
        expected = torch.full((12,), 3.0, dtype=DTYPE)
        counts = torch.stack((expected, 2.0 * expected))
        batch_statistics, batch_splits = tail_scale_scan(counts, expected)
        single_statistics, single_splits = tail_scale_scan(counts[1], expected)
        self.assertTrue(torch.equal(batch_statistics[1], single_statistics))
        self.assertTrue(torch.equal(batch_splits[1], single_splits))

    def test_monte_carlo_threshold_uses_conservative_order_statistic(self):
        expected = torch.full((12,), 2.0, dtype=DTYPE)
        sample_count = 99
        threshold, maxima = monte_carlo_threshold(
            expected,
            false_alarm_rate=0.05,
            sample_count=sample_count,
            generator=torch.Generator().manual_seed(7),
        )
        rank = math.ceil((sample_count + 1) * 0.95) - 1
        self.assertEqual(threshold, float(maxima[rank]))


if __name__ == "__main__":
    unittest.main()
