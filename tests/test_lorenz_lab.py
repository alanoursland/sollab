import unittest

import torch

from lorenz_lab import lorenz
from kinopulse.solvers.solve_functions import solve_ivp


class LorenzLabTests(unittest.TestCase):
    def test_vector_field_at_unit_state(self):
        derivative = lorenz(0.0, torch.ones(3))
        expected = torch.tensor([0.0, 26.0, -5.0 / 3.0])
        torch.testing.assert_close(derivative, expected)

    def test_solve_ivp_honors_requested_grid(self):
        requested = torch.linspace(0.0, 0.2, 21)
        span = (float(requested[0]), float(requested[-1]))
        trajectory = solve_ivp(lorenz, span, torch.ones(3), t_eval=requested)
        self.assertEqual(trajectory.states.shape, (21, 3))
        torch.testing.assert_close(trajectory.times, requested, rtol=0, atol=0)
        torch.testing.assert_close(trajectory.states[0], torch.ones(3))


if __name__ == "__main__":
    unittest.main()
