import unittest

from diffusion_lab import probe_stability_warning, solve_resolution


class DiffusionLabTests(unittest.TestCase):
    def test_heat_solution_matches_analytical_mode(self):
        _, _, _, error, _ = solve_resolution(51)
        self.assertLess(error, 3e-5)

    def test_diffusion_reduces_variance_monotonically(self):
        _, _, _, _, trajectory = solve_resolution(51)
        variances = [field.data.var().item() for field in trajectory.fields]
        self.assertTrue(all(b <= a + 1e-12 for a, b in zip(variances, variances[1:])))

    def test_unsafe_explicit_timestep_emits_warning(self):
        messages = probe_stability_warning()
        self.assertEqual(len(messages), 1)
        self.assertIn("exceeds the estimated diffusion stability limit", messages[0])


if __name__ == "__main__":
    unittest.main()
