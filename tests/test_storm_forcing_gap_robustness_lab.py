import unittest

import torch

from storm_forcing_gap_robustness_lab import interpolate_short_gaps


class StormForcingGapRobustnessLabTests(unittest.TestCase):
    def test_short_interior_gap_is_linearly_interpolated(self):
        values = torch.tensor([0.0, 99.0, 99.0, 6.0], dtype=torch.float64)
        valid = torch.tensor([True, False, False, True])
        filled, filled_valid, gaps = interpolate_short_gaps(values, valid, 2)
        self.assertTrue(torch.equal(filled_valid, torch.ones(4, dtype=torch.bool)))
        self.assertTrue(torch.allclose(filled, torch.tensor([0.0, 2.0, 4.0, 6.0], dtype=torch.float64)))
        self.assertEqual(gaps[0]["hours"], 2)

    def test_long_or_boundary_gap_remains_invalid(self):
        values = torch.tensor([99.0, 0.0, 99.0, 99.0, 3.0], dtype=torch.float64)
        valid = torch.tensor([False, True, False, False, True])
        _, filled_valid, gaps = interpolate_short_gaps(values, valid, 1)
        self.assertTrue(torch.equal(filled_valid, valid))
        self.assertEqual(gaps, [])


if __name__ == "__main__":
    unittest.main()
