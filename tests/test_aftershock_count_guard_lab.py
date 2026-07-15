import unittest

import torch

from aftershock_count_guard_lab import choose_count_space_blend
from aftershock_hierarchy_lab import shape_vector
from aftershock_lab import DTYPE, FitResult, _encode_p, omori_expected_counts
from aftershock_transfer_lab import SequenceData, make_transfer_bins
from fetch_aftershock_benchmark import SEQUENCES


class AftershockCountGuardLabTests(unittest.TestCase):
    def test_tied_corrections_choose_zero_metadata_trust(self):
        edges = make_transfer_bins()
        calibration = edges[1:] <= 1.0
        evaluation = edges[:-1] >= 1.0
        truth = torch.tensor(
            [torch.log(torch.tensor(50.0)), torch.log(torch.tensor(0.1)), _encode_p(1.0)],
            dtype=DTYPE,
        )
        counts = omori_expected_counts(truth, edges)
        sequences = [
            SequenceData(
                SEQUENCES[index],
                torch.empty(0, dtype=DTYPE),
                counts,
                0.0,
                "synthetic",
                0,
            )
            for index in range(5)
        ]
        fits = [
            FitResult(
                "omori",
                truth,
                {"c_days": 0.1, "p": 1.0},
                counts,
                0.0,
                0,
            )
            for _ in sequences
        ]
        targets = torch.stack([shape_vector(fit) for fit in fits])
        blend, scores = choose_count_space_blend(
            list(range(5)),
            sequences,
            torch.zeros((5, 1), dtype=DTYPE),
            targets,
            fits,
            edges,
            calibration,
            evaluation,
            pooling_strength=4.0,
            ridge_strength=10.0,
        )
        self.assertEqual(blend, 0.0)
        self.assertEqual(set(scores), {"0.0", "0.25", "0.5", "0.75", "1.0"})


if __name__ == "__main__":
    unittest.main()
