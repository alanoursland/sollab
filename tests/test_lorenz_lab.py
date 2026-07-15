import unittest

import torch

from lorenz_lab import interpolate_trajectory, lorenz
from kinopulse.solvers.solve_functions import solve_ivp


class LorenzLabTests(unittest.TestCase):
    def test_vector_field_at_unit_state(self):
        derivative = lorenz(0.0, torch.ones(3))
        expected = torch.tensor([0.0, 26.0, -5.0 / 3.0])
        torch.testing.assert_close(derivative, expected)

    def test_resampling_honors_requested_grid(self):
        requested = torch.linspace(0.0, 0.2, 21)
        trajectory = solve_ivp(lorenz, (0.0, 0.2), torch.ones(3))
        sampled = interpolate_trajectory(trajectory, requested)
        self.assertEqual(sampled.shape, (21, 3))
        torch.testing.assert_close(sampled[0], torch.ones(3))


if __name__ == "__main__":
    unittest.main()
