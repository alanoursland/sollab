import unittest

import torch

from pitchfork_lab import analyze, pitchfork


class PitchforkLabTests(unittest.TestCase):
    def test_normal_form_equilibria(self):
        params = {"mu": torch.tensor(0.25)}
        for equilibrium in (-0.5, 0.0, 0.5):
            derivative = pitchfork(0.0, torch.tensor([equilibrium]), params)
            torch.testing.assert_close(derivative, torch.zeros(1))

    def test_sweep_tracks_central_branch_stability_crossing(self):
        mu, sweep, _ = analyze(samples=21)
        self.assertTrue(sweep.continuation_successful)
        eigenvalues = sweep.eigenvalue_tracking[:, 0].real
        torch.testing.assert_close(eigenvalues, mu, atol=1e-7, rtol=1e-7)


if __name__ == "__main__":
    unittest.main()
