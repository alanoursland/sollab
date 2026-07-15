import math
import unittest

import torch

from aftershock_excitation_lab import (
    DTYPE,
    TRAIN_END_DAYS,
    _encode_alpha,
    decode_excitation,
    excitation_expected_counts,
    make_conditional_bins,
)


class AftershockExcitationLabTests(unittest.TestCase):
    def test_bins_have_exact_training_boundary(self):
        edges = make_conditional_bins()
        self.assertEqual(float(edges[56]), TRAIN_END_DAYS)
        self.assertEqual(len(edges), 56 + 92 + 1)

    def test_event_only_affects_bins_starting_after_it(self):
        edges = torch.tensor([1.0, 2.0, 3.0], dtype=DTYPE)
        theta = torch.tensor([0.0, 0.0], dtype=DTYPE)
        empty = torch.empty(0, dtype=DTYPE)
        baseline = excitation_expected_counts(
            theta,
            edges,
            empty,
            empty,
            offset=0.1,
            exponent=1.1,
            background=0.0,
            magnitude_weighted=False,
        )
        with_event = excitation_expected_counts(
            theta,
            edges,
            torch.tensor([1.5], dtype=DTYPE),
            torch.tensor([3.0], dtype=DTYPE),
            offset=0.1,
            exponent=1.1,
            background=0.0,
            magnitude_weighted=False,
        )
        self.assertAlmostEqual(float(with_event[0]), float(baseline[0]))
        self.assertGreater(float(with_event[1]), float(baseline[1]))

    def test_larger_prior_event_has_more_conditional_weight(self):
        edges = torch.tensor([1.0, 2.0], dtype=DTYPE)
        theta = torch.tensor(
            [0.0, 0.0, _encode_alpha(2.0)], dtype=DTYPE
        )
        time = torch.tensor([0.5], dtype=DTYPE)
        low = excitation_expected_counts(
            theta,
            edges,
            time,
            torch.tensor([2.5], dtype=DTYPE),
            offset=0.1,
            exponent=1.1,
            background=0.0,
            magnitude_weighted=True,
        )
        high = excitation_expected_counts(
            theta,
            edges,
            time,
            torch.tensor([4.5], dtype=DTYPE),
            offset=0.1,
            exponent=1.1,
            background=0.0,
            magnitude_weighted=True,
        )
        self.assertGreater(float(high[0]), float(low[0]) * 10.0)

    def test_magnitude_blind_parameterization_needs_only_two_values(self):
        primary, secondary, alpha = decode_excitation(
            torch.tensor([math.log(2.0), math.log(0.5)], dtype=DTYPE),
            magnitude_weighted=False,
        )
        self.assertAlmostEqual(float(primary), 2.0)
        self.assertAlmostEqual(float(secondary), 0.5)
        self.assertEqual(float(alpha), 0.0)


if __name__ == "__main__":
    unittest.main()
