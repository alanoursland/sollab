import unittest

from constraint_lab import simulate


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


if __name__ == "__main__":
    unittest.main()
