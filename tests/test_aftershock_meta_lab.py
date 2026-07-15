import unittest

import torch

from aftershock_meta_lab import (
    choose_guarded_configuration,
    early_features,
    ridge_predict,
)
from aftershock_lab import DTYPE, FitResult
from aftershock_transfer_lab import SequenceData, make_transfer_bins
from fetch_aftershock_benchmark import SEQUENCES


class AftershockMetaLabTests(unittest.TestCase):
    def test_ridge_predict_learns_a_linear_mapping(self):
        features = torch.tensor(
            [[-2.0], [-1.0], [0.0], [1.0], [2.0]], dtype=DTYPE
        )
        targets = torch.cat((2.0 * features + 3.0, -features + 1.0), dim=1)
        prediction = ridge_predict(
            features, targets, torch.tensor([0.5], dtype=DTYPE), 1e-8
        )
        self.assertTrue(
            torch.allclose(prediction, torch.tensor([4.0, 0.5], dtype=DTYPE), atol=1e-6)
        )

    def test_future_events_cannot_change_early_features(self):
        edges = make_transfer_bins()
        base_times = torch.tensor([0.1, 0.2, 0.5, -10.0], dtype=DTYPE)
        record = {"magnitude": 6.5, "depth_km": 10.0}

        def sequence(times):
            return SequenceData(
                SEQUENCES[0],
                times,
                torch.zeros(len(edges) - 1, dtype=DTYPE),
                0.25,
                "synthetic",
                len(times),
            )

        original = early_features(sequence(base_times), record)
        future = early_features(
            sequence(torch.cat((base_times, torch.tensor([2.0, 10.0], dtype=DTYPE)))),
            record,
        )
        self.assertTrue(torch.equal(original, future))

    def test_guard_can_select_zero_trust_for_uninformative_features(self):
        features = torch.zeros((5, 1), dtype=DTYPE)
        targets = torch.tensor(
            [[0.0, 0.0], [0.1, 0.1], [-0.1, -0.1], [0.05, 0.05], [4.0, -4.0]],
            dtype=DTYPE,
        )
        fits = [
            FitResult(
                "synthetic",
                torch.empty(0),
                {
                    "c_days": float(torch.exp(target[0])),
                    "p": float(0.3 + 1.7 * torch.sigmoid(target[1])),
                },
                torch.empty(0),
                0.0,
                0,
            )
            for target in targets
        ]
        _, blend, _ = choose_guarded_configuration(
            features, targets, fits, list(range(len(features)))
        )
        self.assertEqual(blend, 0.0)


if __name__ == "__main__":
    unittest.main()
