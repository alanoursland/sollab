import unittest

from batched_bouncing_lab import run


class BatchedBouncingLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run()

    def test_physical_first_impacts_and_restitution_match_theory(self):
        for sample in self.result["physical_diagnostics"]:
            self.assertLess(sample["first_impact_absolute_error"], 1e-6)
            if sample["mean_post_impact_velocity_ratio"] is not None:
                self.assertLess(
                    abs(
                        sample["mean_post_impact_velocity_ratio"]
                        - sample["expected_velocity_ratio"]
                    ),
                    1e-6,
                )

    def test_serial_and_concurrent_batches_are_bit_exact(self):
        self.assertTrue(self.result["serial_vs_concurrent"]["all_equal"])

    def test_ragged_padding_and_caller_isolation_are_explicit(self):
        ragged = self.result["ragged_batch"]
        self.assertEqual(ragged["lengths"], ragged["valid_counts"])
        self.assertTrue(ragged["padding_is_nan"])
        self.assertEqual(self.result["caller_isolation"]["mode_sequence"], ["flight"])
        self.assertEqual(self.result["caller_isolation"]["transition_times"], [])

    def test_synchronization_and_partial_failures_retain_diagnostics(self):
        self.assertTrue(self.result["synchronization"]["matching_verified"])
        self.assertEqual(self.result["synchronization"]["divergence"]["sample_index"], 1)
        failure = self.result["partial_failure"]
        self.assertEqual(failure["failed_indices"], [1])
        self.assertEqual(failure["result_statuses"], ["completed", None, "completed"])
        self.assertEqual(failure["exception_types"], [None, "RuntimeError", None])


if __name__ == "__main__":
    unittest.main()
