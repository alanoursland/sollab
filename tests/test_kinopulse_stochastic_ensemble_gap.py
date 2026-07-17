import unittest

import torch

from kinopulse.neural.vector_fields import EnsembleNeuralVectorField, NeuralStochasticVectorField

from stochastic_uncertainty_lab import ConstantNetwork, DTYPE


class KinoPulseStochasticEnsembleGapTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_stochastic_ensemble_preserves_mean_member_aleatoric_covariance(self):
        first = NeuralStochasticVectorField(2, 2, dtype=DTYPE)
        first.drift_net = ConstantNetwork([1.0, 2.0])
        first.diffusion_net = ConstantNetwork([1.0, 0.0, 0.0, 2.0])

        second = NeuralStochasticVectorField(2, 2, dtype=DTYPE)
        second.drift_net = ConstantNetwork([3.0, 0.0])
        second.diffusion_net = ConstantNetwork([0.5, 0.0, 0.0, 0.5])

        result = EnsembleNeuralVectorField([first, second]).predict_distribution(
            torch.tensor(0.0), torch.zeros(2, dtype=DTYPE)
        )
        expected_aleatoric = torch.tensor(
            [[0.625, 0.0], [0.0, 2.125]], dtype=DTYPE
        )
        self.assertTrue(torch.allclose(result.mean, torch.tensor([2.0, 1.0], dtype=DTYPE)))
        self.assertTrue(torch.allclose(result.epistemic_variance, torch.tensor([1.0, 1.0], dtype=DTYPE)))
        self.assertTrue(torch.allclose(result.aleatoric_covariance, expected_aleatoric))


if __name__ == "__main__":
    unittest.main()
