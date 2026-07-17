import unittest

import numpy as np

from stochastic_uncertainty_lab import (
    analytical_stochastic_oracle,
    ensemble_oracle,
    monte_carlo_oracle,
)


class StochasticUncertaintyLabTests(unittest.TestCase):
    def test_diffusion_covariance_and_supplied_noise_match_linear_algebra(self):
        result = analytical_stochastic_oracle()
        np.testing.assert_allclose(result["aleatoric_covariance"], result["expected_covariance"], atol=1e-14)
        np.testing.assert_allclose(result["applied_noise"], result["expected_applied_noise"], atol=1e-14)
        self.assertEqual(result["epistemic_variance"], [0.0, 0.0])

    def test_ensemble_mean_and_population_variance_are_exact(self):
        result = ensemble_oracle()
        np.testing.assert_allclose(result["mean"], result["expected_mean"], atol=1e-14)
        np.testing.assert_allclose(
            result["epistemic_variance"], result["expected_epistemic_variance"], atol=1e-14
        )
        np.testing.assert_allclose(result["aleatoric_covariance"], np.zeros((2, 2)), atol=0.0)

    def test_seeded_one_step_samples_converge_to_declared_moments(self):
        result, _ = monte_carlo_oracle()
        self.assertLess(result["mean_error_l2"], 1.0e-3)
        self.assertLess(result["covariance_error_frobenius"], 1.0e-4)


if __name__ == "__main__":
    unittest.main()
