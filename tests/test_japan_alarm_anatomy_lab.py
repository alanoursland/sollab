import unittest

from japan_alarm_anatomy_lab import select_checkpoints, zero_success_upper_bound


class JapanAlarmAnatomyLabTests(unittest.TestCase):
    def test_zero_success_bound_has_exact_zero_event_probability(self):
        bound = zero_success_upper_bound(100, alpha=0.05)
        self.assertAlmostEqual((1.0 - bound) ** 100, 0.05)

    def test_checkpoint_selection_never_looks_past_declared_day(self):
        rows = [
            {"bin": 0, "end_day": 3.0},
            {"bin": 1, "end_day": 7.0},
            {"bin": 2, "end_day": 15.0},
            {"bin": 3, "end_day": 30.0},
        ]
        selected = select_checkpoints(rows)
        self.assertTrue(
            all(row["end_day"] <= row["checkpoint_day"] + 1e-9 for row in selected)
        )
        self.assertEqual(len({row["bin"] for row in selected}), len(selected))


if __name__ == "__main__":
    unittest.main()
