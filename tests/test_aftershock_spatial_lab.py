import unittest

import torch

from aftershock_lab import DTYPE
from aftershock_spatial_lab import (
    SPATIAL_REGIONS,
    _encode_sigma,
    _encode_tau,
    _logit,
    binned_region_counts,
    state_allocation_probabilities,
)


class AftershockSpatialLabTests(unittest.TestCase):
    def test_region_counts_preserve_time_and_region_membership(self):
        counts = binned_region_counts(
            torch.tensor([0.5, 1.5, 1.7], dtype=DTYPE),
            torch.tensor([0, 1, 4]),
            torch.tensor([0.0, 1.0, 2.0], dtype=DTYPE),
        )
        expected = torch.zeros((2, SPATIAL_REGIONS), dtype=DTYPE)
        expected[0, 0] = 1.0
        expected[1, 1] = 1.0
        expected[1, 4] = 1.0
        self.assertTrue(torch.equal(counts, expected))

    def test_spatial_probabilities_are_normalized_without_history(self):
        theta = torch.tensor(
            [_logit(0.5), 0.0, _encode_sigma(8.0), _encode_tau(0.2)],
            dtype=DTYPE,
        )
        probabilities = state_allocation_probabilities(
            theta,
            torch.tensor([1.0, 2.0], dtype=DTYPE),
            torch.empty(0, dtype=DTYPE),
            torch.empty(0, dtype=DTYPE),
            torch.empty(0, dtype=DTYPE),
            torch.linspace(-20.0, 20.0, SPATIAL_REGIONS, dtype=DTYPE),
            torch.full((SPATIAL_REGIONS,), 1.0 / SPATIAL_REGIONS, dtype=DTYPE),
        )
        self.assertAlmostEqual(float(probabilities.sum()), 1.0)

    def test_future_event_cannot_affect_current_region_allocation(self):
        base = torch.full(
            (SPATIAL_REGIONS,), 1.0 / SPATIAL_REGIONS, dtype=DTYPE
        )
        theta = torch.tensor(
            [_logit(0.8), 0.0, _encode_sigma(3.0), _encode_tau(0.5)],
            dtype=DTYPE,
        )
        probabilities = state_allocation_probabilities(
            theta,
            torch.tensor([1.0, 2.0, 3.0], dtype=DTYPE),
            torch.tensor([1.5], dtype=DTYPE),
            torch.tensor([3.0], dtype=DTYPE),
            torch.tensor([20.0], dtype=DTYPE),
            torch.linspace(-20.0, 20.0, SPATIAL_REGIONS, dtype=DTYPE),
            base,
        )
        self.assertTrue(torch.allclose(probabilities[0], base))
        self.assertGreater(float(probabilities[1, -1]), float(base[-1]))
        self.assertAlmostEqual(float(probabilities[1].sum()), 1.0)


if __name__ == "__main__":
    unittest.main()
