import unittest

import torch

from constraint_lab import DTYPE, make_system, pendulum_constraint, simulate
from kinopulse.core.state import EuclideanSpace, State
from kinopulse.solvers.config import SolverConfig
from kinopulse.solvers.dae import ConstraintProjector, analyze_consistent_initialization


class ConstraintLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trajectory, cls.circle, cls.tangency, cls.energy, cls.initialization = simulate(
            project=True, steps=200
        )

    def test_initial_guess_is_projected_consistently(self):
        self.assertTrue(self.initialization.is_consistent)
        self.assertLess(self.initialization.max_violation, 1e-10)
        self.assertGreater(self.initialization.correction_norm, 0.01)

    def test_projection_controls_both_constraints(self):
        self.assertLess(self.circle.max().item(), 1e-6)
        self.assertLess(self.tangency.max().item(), 1e-6)

    def test_plural_constraints_hook_initializes_consistently(self):
        system = make_system()
        del system.constraint
        system.constraints = pendulum_constraint
        guess = State(
            torch.tensor([0.7, -0.7, 0.2, 0.1], dtype=DTYPE), EuclideanSpace(4)
        )
        _, result = analyze_consistent_initialization(system, guess)
        self.assertEqual(result.method, "newton")
        self.assertLess(result.max_violation, 1e-10)

    @unittest.expectedFailure
    def test_plural_constraints_hook_projects(self):
        system = make_system()
        del system.constraint
        system.constraints = pendulum_constraint
        guess = State(
            torch.tensor([0.7, -0.7, 0.2, 0.1], dtype=DTYPE), EuclideanSpace(4)
        )
        projected = ConstraintProjector(system, SolverConfig(dtype=DTYPE)).project(
            0.0, guess
        )
        violation = pendulum_constraint(0.0, projected).abs().max().item()
        self.assertLess(violation, 1e-10)


if __name__ == "__main__":
    unittest.main()
