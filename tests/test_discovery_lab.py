import unittest
import re

from discovery_lab import discover


class DiscoveryLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.system = discover()

    def test_recovers_exact_lorenz_sparsity(self):
        self.assertEqual(int((self.system.coefficients.abs() > 1e-6).sum()), 7)
        active = self.system.get_active_terms()
        self.assertEqual([len(active[i]) for i in range(3)], [2, 3, 2])

    def test_recovered_coefficients_are_close(self):
        rows = {name: index for index, name in enumerate(self.system.feature_names)}
        expected = {
            ("x0", 0): -10.0,
            ("x1", 0): 10.0,
            ("x0", 1): 28.0,
            ("x1", 1): -1.0,
            ("x0*x2", 1): -1.0,
            ("x2", 2): -8.0 / 3.0,
            ("x0*x1", 2): 1.0,
        }
        for (feature, output), value in expected.items():
            self.assertAlmostEqual(
                self.system.coefficients[rows[feature], output].item(), value, delta=0.03
            )

    def test_default_equation_format_is_decimal(self):
        equations = self.system.get_equations(state_names=["x", "y", "z"])
        self.assertIn("-9.997*x0", equations)
        self.assertIsNone(re.search(r"\d+/\d+", equations))


if __name__ == "__main__":
    unittest.main()
