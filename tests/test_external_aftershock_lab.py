import unittest

import torch

from aftershock_hierarchy_lab import PopulationShape
from aftershock_lab import DTYPE
from aftershock_transfer_lab import SequenceData, make_transfer_bins
from external_aftershock_lab import aggregate_folds, fit_frozen_target
from fetch_aftershock_benchmark import SequenceSpec


class ExternalAftershockLabTests(unittest.TestCase):
    def test_aggregate_counts_each_sequence_win_once(self):
        folds = [
            {
                "models": {
                    "frozen_hierarchy": {"poisson_deviance": 1.0},
                    "robust_pool": {"poisson_deviance": 2.0},
                    "target_day1": {"poisson_deviance": 3.0},
                }
            },
            {
                "models": {
                    "frozen_hierarchy": {"poisson_deviance": 4.0},
                    "robust_pool": {"poisson_deviance": 2.0},
                    "target_day1": {"poisson_deviance": 3.0},
                }
            },
        ]
        aggregate = aggregate_folds(folds)
        self.assertEqual(aggregate["frozen_hierarchy"]["sequence_wins"], 1)
        self.assertEqual(aggregate["robust_pool"]["sequence_wins"], 1)
        self.assertEqual(aggregate["target_day1"]["sequence_wins"], 0)

    def test_future_counts_cannot_change_frozen_target_fit(self):
        edges = make_transfer_bins()
        calibration = edges[1:] <= 1.0
        counts = torch.full((len(edges) - 1,), 8.0, dtype=DTYPE)
        spec = SequenceSpec(
            "synthetic", "Synthetic", "synthetic", "2020-01-01T00:00:00Z",
            60.0, -150.0, 6.5,
        )
        original = SequenceData(
            spec, torch.empty(0, dtype=DTYPE), counts, 0.1, "", 0
        )
        changed_counts = counts.clone()
        changed_counts[~calibration] = 10000.0
        changed = SequenceData(
            spec, torch.empty(0, dtype=DTYPE), changed_counts, 0.1, "", 0
        )
        population = PopulationShape(
            center=torch.tensor([-2.0, 0.0], dtype=DTYPE),
            scale=torch.tensor([0.5, 0.5], dtype=DTYPE),
        )
        first = fit_frozen_target(original, edges, calibration, population, 4.0)
        second = fit_frozen_target(changed, edges, calibration, population, 4.0)
        self.assertTrue(torch.equal(first.expected_counts, second.expected_counts))


if __name__ == "__main__":
    unittest.main()
