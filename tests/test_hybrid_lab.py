import unittest
import warnings

from hybrid_lab import GRAVITY, RESTITUTION, simulate, theoretical_accumulation_time


class HybridLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = simulate(horizon=3.0)

    def test_first_impact_is_localized(self):
        expected = (2.0 / GRAVITY) ** 0.5
        observed = self.result.transitions[0]["time"]
        self.assertAlmostEqual(observed, expected, delta=2e-5)

    def test_reset_obeys_restitution_law(self):
        for transition in self.result.transitions:
            before = transition["x_minus"]
            after = transition["x_plus"]
            self.assertAlmostEqual(after[0].item(), 0.0, delta=1e-12)
            self.assertAlmostEqual(after[1].item(), -RESTITUTION * before[1].item(), delta=1e-12)

    def test_geometric_zeno_detection_stops_before_accumulation(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = simulate(
                horizon=4.2,
                zeno_time_window=0.01,
                zeno_action="stop",
            )
        self.assertTrue(result.zeno_detected)
        self.assertIn("Geometrically decreasing dwell times", result.zeno_reason)
        self.assertLess(float(result.t[-1]), theoretical_accumulation_time())


if __name__ == "__main__":
    unittest.main()
