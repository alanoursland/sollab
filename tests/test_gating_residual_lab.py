import unittest

from kinopulse.neural.gating import GatingPolicy

from gating_residual_lab import (
    IdentityLogits,
    chatter_scenario,
    replay_gate,
    residual_oracles,
    straight_through_oracle,
)


class GatingResidualLabTests(unittest.TestCase):
    def test_hysteresis_and_dwell_remove_chatter_but_keep_real_transitions(self):
        margins, truth = chatter_scenario()
        result = replay_gate(
            GatingPolicy(
                IdentityLogits(),
                2,
                mode="hard",
                hysteresis=0.25,
                min_dwell_steps=2,
            ),
            margins,
            truth,
        )
        self.assertEqual(result["switch_count"], 2)
        self.assertEqual(result["selected"], truth)
        self.assertEqual(result["expert_output_mse"], 0.0)

    def test_hard_forward_is_exact_while_gate_gradient_is_nonzero(self):
        result = straight_through_oracle()
        self.assertEqual(result["weights"], [[1.0, 0.0]])
        self.assertEqual(result["forward_value"], 2.0)
        self.assertGreater(result["gradient_norm"], 0.0)
        self.assertAlmostEqual(result["gradient_sum"], 0.0, places=12)

    def test_structured_residuals_match_closed_form_composition(self):
        result = residual_oracles()
        self.assertEqual(result["multiplicative_actual"], result["multiplicative_expected"])
        self.assertEqual(result["gate_value"], 0.5)
        self.assertEqual(result["gated_actual"], result["gated_expected"])


if __name__ == "__main__":
    unittest.main()
