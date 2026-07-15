import math
import unittest

import torch

from aftershock_hierarchy_lab import (
    PopulationShape,
    fit_hierarchical_target,
    robust_population,
)
from aftershock_lab import DTYPE, FitResult, _encode_p, omori_expected_counts
from aftershock_transfer_lab import SequenceData, make_transfer_bins
from fetch_aftershock_benchmark import SEQUENCES


def synthetic_fit(c_days: float, exponent: float) -> FitResult:
    return FitResult(
        name="omori",
        theta=torch.zeros(3, dtype=DTYPE),
        parameters={"c_days": c_days, "p": exponent},
        expected_counts=torch.empty(0, dtype=DTYPE),
        objective=0.0,
        iterations=0,
    )


class AftershockHierarchyLabTests(unittest.TestCase):
    def setUp(self):
        self.edges = make_transfer_bins()
        self.calibration = self.edges[1:] <= 1.0
        self.population = PopulationShape(
            center=torch.tensor([math.log(0.1), _encode_p(1.0)], dtype=DTYPE),
            scale=torch.tensor([0.5, 0.5], dtype=DTYPE),
        )

    def test_robust_population_contains_pathological_individual_fit(self):
        fits = [
            synthetic_fit(0.1, 1.0),
            synthetic_fit(0.12, 1.1),
            synthetic_fit(1e-100, 2.0),
        ]
        population = robust_population(fits, [0, 1, 2])
        self.assertAlmostEqual(float(torch.exp(population.center[0])), 0.1)
        self.assertTrue(torch.all(torch.isfinite(population.scale)))
        self.assertTrue(torch.all(population.scale >= 0.35))

    def test_future_counts_cannot_change_hierarchical_fit(self):
        truth = torch.tensor(
            [math.log(50.0), math.log(0.2), _encode_p(1.2)], dtype=DTYPE
        )
        counts = omori_expected_counts(truth, self.edges)
        original = SequenceData(
            SEQUENCES[0],
            torch.empty(0, dtype=DTYPE),
            counts,
            0.0,
            "synthetic",
            0,
        )
        corrupted_counts = counts.clone()
        corrupted_counts[~self.calibration] = 1_000_000.0
        corrupted = SequenceData(
            SEQUENCES[0],
            torch.empty(0, dtype=DTYPE),
            corrupted_counts,
            0.0,
            "synthetic",
            0,
        )
        first = fit_hierarchical_target(
            original, self.edges, self.calibration, self.population, 4.0
        )
        second = fit_hierarchical_target(
            corrupted, self.edges, self.calibration, self.population, 4.0
        )
        self.assertTrue(torch.allclose(first.theta, second.theta))

    def test_stronger_pooling_keeps_shape_closer_to_population(self):
        truth = torch.tensor(
            [math.log(80.0), math.log(0.5), _encode_p(1.5)], dtype=DTYPE
        )
        sequence = SequenceData(
            SEQUENCES[0],
            torch.empty(0, dtype=DTYPE),
            omori_expected_counts(truth, self.edges),
            0.0,
            "synthetic",
            0,
        )
        weak = fit_hierarchical_target(
            sequence, self.edges, self.calibration, self.population, 0.25
        )
        strong = fit_hierarchical_target(
            sequence, self.edges, self.calibration, self.population, 16.0
        )
        weak_distance = torch.linalg.vector_norm(
            (weak.theta[1:] - self.population.center) / self.population.scale
        )
        strong_distance = torch.linalg.vector_norm(
            (strong.theta[1:] - self.population.center) / self.population.scale
        )
        self.assertLess(float(strong_distance), float(weak_distance))


if __name__ == "__main__":
    unittest.main()
