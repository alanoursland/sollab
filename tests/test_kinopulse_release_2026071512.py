import math
import unittest

import torch

from kinopulse_release_lab import run_release_validation


class KinoPulseRelease2026071512Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = run_release_validation()

    def test_count_objectives_match_analytical_oracles(self):
        counts = self.evidence["count_objectives"]
        self.assertLess(counts["log_likelihood_absolute_error"], 1e-14)
        self.assertLess(counts["deviance_residual_identity_error"], 1e-14)
        self.assertEqual(
            counts["zero_count_deviance_contribution"],
            counts["expected_zero_count_limit"],
        )
        self.assertTrue(counts["gradient_is_finite"])

    def test_expected_count_integrators_are_exact_for_linear_rate(self):
        integration = self.evidence["expected_count_integration"]
        self.assertLess(integration["maximum_absolute_error"], 1e-14)
        self.assertAlmostEqual(
            integration["scale_gradient"],
            integration["expected_scale_gradient"],
            places=14,
        )

    def test_homogeneous_point_process_matches_closed_form_and_replays(self):
        process = self.evidence["homogeneous_point_process"]
        self.assertLess(process["absolute_error"], 1e-14)
        self.assertLess(process["maximum_expected_count_error"], 1e-14)
        self.assertTrue(process["batch_matches_scalar"])
        self.assertTrue(process["simulation_reproducible"])

    @unittest.expectedFailure
    def test_history_dependent_compensator_includes_left_boundary_event(self):
        process = self.evidence["history_dependent_point_process"]
        self.assertLess(process["absolute_error"], 1e-12)

    def test_rich_least_squares_result_and_residual_accounting(self):
        fit = self.evidence["least_squares"]
        self.assertTrue(fit["converged"])
        self.assertEqual(fit["jacobian_rank"], 2)
        self.assertTrue(fit["has_covariance"])
        self.assertLess(math.dist(fit["parameters"], [1.5, -0.25]), 1e-10)
        contributions = fit["objective_contributions"]
        self.assertEqual(set(contributions), {"observations", "weak_prior"})
        self.assertAlmostEqual(
            sum(block["objective"] for block in contributions.values()),
            fit["objective"],
            places=14,
        )

    def test_multistart_preserves_failed_candidate_and_selects_best(self):
        multistart = self.evidence["multistart"]
        self.assertEqual(multistart["candidate_count"], 3)
        self.assertEqual(multistart["failed_candidate_indices"], [0])
        self.assertIn(multistart["best_index"], [1, 2])
        self.assertLess(math.dist(multistart["best_parameters"], [2.0, -1.0]), 1e-10)

    def test_singular_covariance_policy_is_explicit(self):
        covariance = self.evidence["singular_covariance"]
        self.assertEqual(covariance["rank"], 1)
        self.assertTrue(covariance["used_pseudoinverse"])
        self.assertTrue(covariance["covariance_is_finite"])


if __name__ == "__main__":
    unittest.main()
