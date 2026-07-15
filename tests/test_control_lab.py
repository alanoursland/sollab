import unittest

import torch

from control_lab import A, B, Q, R, design_controller
from kinopulse.control.linear.lqr import verify_closed_loop_stability, verify_riccati_solution
from kinopulse.control.linear.utils.controllability import is_controllable


class ControlLabTests(unittest.TestCase):
    def test_unstable_plant_is_controllable(self):
        controllable, rank = is_controllable(A, B)
        self.assertTrue(controllable)
        self.assertEqual(rank, 2)
        self.assertGreater(torch.linalg.eigvals(A).real.max().item(), 0.0)

    def test_lqr_stabilizes_and_satisfies_care(self):
        controller = design_controller()
        stable, poles = verify_closed_loop_stability(A, B, controller.K)
        valid, residual = verify_riccati_solution(A, B, Q, R, controller.P, tol=1e-7)
        self.assertTrue(stable)
        self.assertTrue(torch.all(poles.real < 0))
        self.assertTrue(valid, f"CARE residual was {residual}")


if __name__ == "__main__":
    unittest.main()
