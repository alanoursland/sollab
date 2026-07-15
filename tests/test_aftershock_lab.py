import math
import unittest

import torch

from aftershock_lab import (
    DTYPE,
    FitResult,
    TRAIN_END_DAYS,
    _encode_p,
    fit_relaxation_model,
    integrate_omori,
    make_bins,
    omori_expected_counts,
    poisson_deviance,
)


class AftershockLabTests(unittest.TestCase):
    def setUp(self):
        self.background = 0.1
        self.edges = make_bins(30)
        self.theta = torch.tensor(
            [math.log(300.0), math.log(0.03), _encode_p(1.1)], dtype=DTYPE
        )
        self.observed = omori_expected_counts(
            self.theta, self.edges, self.background
        ).detach()

    def test_bins_contain_exact_training_boundary(self):
        self.assertTrue(torch.any(self.edges == TRAIN_END_DAYS))

    def test_kinopulse_fit_recovers_synthetic_omori_curve(self):
        training = self.edges[1:] <= TRAIN_END_DAYS
        fit = fit_relaxation_model(
            "omori", self.edges, self.observed, training, self.background
        )
        self.assertAlmostEqual(fit.parameters["p"], 1.1, delta=1e-4)
        self.assertAlmostEqual(fit.parameters["c_days"], 0.03, delta=1e-4)
        self.assertLess(fit.objective, 1e-10)

    def test_power_law_generalizes_better_than_exponential(self):
        training = self.edges[1:] <= TRAIN_END_DAYS
        holdout = ~training
        omori = fit_relaxation_model(
            "omori", self.edges, self.observed, training, self.background
        )
        exponential = fit_relaxation_model(
            "exponential", self.edges, self.observed, training, self.background
        )
        omori_score = poisson_deviance(
            omori.expected_counts[holdout], self.observed[holdout]
        )
        exponential_score = poisson_deviance(
            exponential.expected_counts[holdout], self.observed[holdout]
        )
        self.assertLess(omori_score, exponential_score * 1e-4)

    def test_kinopulse_integration_matches_closed_form_counts(self):
        expected = omori_expected_counts(self.theta, self.edges, self.background)
        fit = FitResult(
            name="omori",
            theta=self.theta,
            parameters={},
            expected_counts=expected,
            objective=0.0,
            iterations=0,
        )
        numerical = integrate_omori(fit, self.edges, self.background)
        closed_form = torch.cat(
            (torch.zeros(1, dtype=DTYPE), torch.cumsum(expected, dim=0))
        )
        self.assertLess(float((numerical - closed_form).abs().max()), 0.1)


if __name__ == "__main__":
    unittest.main()
