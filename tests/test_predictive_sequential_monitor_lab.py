import math
import unittest

import torch

from aftershock_hierarchy_lab import PopulationShape
from aftershock_lab import DTYPE
from aftershock_transfer_lab import SequenceData, SequenceSpec
from predictive_sequential_monitor_lab import (
    sample_population_predictive_counts,
    threshold_from_predictive_streams,
)


class PredictiveSequentialMonitorLabTests(unittest.TestCase):
    def setUp(self):
        self.edges = torch.logspace(math.log10(1.0 / 24.0), math.log10(30.0), 31, dtype=DTYPE)
        self.calibration = self.edges[1:] <= 1.0
        self.evaluation = self.edges[:-1] >= 1.0
        self.population = PopulationShape(
            center=torch.tensor([math.log(0.1), 0.0], dtype=DTYPE),
            scale=torch.tensor([0.5, 0.35], dtype=DTYPE),
        )
        self.sequence = SequenceData(
            spec=SequenceSpec(
                "target",
                "target",
                "target",
                "2020-01-01T00:00:00Z",
                40.0,
                -120.0,
                6.0,
            ),
            times_days=torch.empty(0, dtype=DTYPE),
            counts=torch.full((30,), 5.0, dtype=DTYPE),
            background=0.2,
            sha256="synthetic",
            source_rows=0,
        )

    def test_future_counts_cannot_change_predictive_streams(self):
        first, first_ess = sample_population_predictive_counts(
            self.sequence,
            self.edges,
            self.calibration,
            self.evaluation,
            self.population,
            sample_count=32,
            seed=7,
            proposal_count=64,
        )
        changed = SequenceData(
            spec=self.sequence.spec,
            times_days=self.sequence.times_days,
            counts=self.sequence.counts.clone(),
            background=self.sequence.background,
            sha256=self.sequence.sha256,
            source_rows=self.sequence.source_rows,
        )
        changed.counts[self.evaluation] = 100000.0
        second, second_ess = sample_population_predictive_counts(
            changed,
            self.edges,
            self.calibration,
            self.evaluation,
            self.population,
            sample_count=32,
            seed=7,
            proposal_count=64,
        )
        self.assertTrue(torch.equal(first, second))
        self.assertEqual(first_ess, second_ess)

    def test_predictive_threshold_uses_complete_stream_maxima(self):
        expected = torch.full((12,), 2.0, dtype=DTYPE)
        counts = torch.poisson(
            expected.expand(99, -1), generator=torch.Generator().manual_seed(9)
        )
        threshold, maxima, rank = threshold_from_predictive_streams(
            counts, expected, false_alarm_rate=0.05
        )
        self.assertEqual(rank, math.ceil(100 * 0.95) - 1)
        self.assertEqual(threshold, float(maxima[rank]))


if __name__ == "__main__":
    unittest.main()
