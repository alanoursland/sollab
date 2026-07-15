import unittest

from diffusion_lab import solve_resolution


class DiffusionLabTests(unittest.TestCase):
    def test_heat_solution_matches_analytical_mode(self):
        _, _, _, error, _ = solve_resolution(51)
        self.assertLess(error, 3e-5)

    def test_diffusion_reduces_variance_monotonically(self):
        _, _, _, _, trajectory = solve_resolution(51)
        variances = [field.data.var().item() for field in trajectory.fields]
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(variances, variances[1:])))


if __name__ == "__main__":
    unittest.main()
