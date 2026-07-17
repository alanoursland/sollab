import unittest

import torch

from kinopulse.solvers.opt.least_squares import RidgeSolver


class KinoPulseRidgeMultioutputGapTests(unittest.TestCase):
    @unittest.expectedFailure
    def test_matrix_target_returns_matrix_solution_and_scalar_objective(self):
        A = torch.tensor([[1.0, 0.0], [1.0, 1.0], [1.0, 2.0]], dtype=torch.float64)
        target = torch.tensor([[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]], dtype=torch.float64)
        lambda_ = 0.1
        result = RidgeSolver(lambda_=lambda_).solve(A, target)
        expected = torch.linalg.solve(
            A.T @ A + lambda_ * torch.eye(A.shape[1], dtype=A.dtype),
            A.T @ target,
        )
        self.assertTrue(torch.allclose(result.x, expected))
        self.assertAlmostEqual(result.objective, 0.5 * float(torch.sum((A @ result.x - target) ** 2)))


if __name__ == "__main__":
    unittest.main()
