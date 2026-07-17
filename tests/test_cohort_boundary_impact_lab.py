import unittest

from cohort_boundary_impact_lab import predictive_coverage


class CohortBoundaryImpactLabTests(unittest.TestCase):
    def test_predictive_coverage_counts_removed_miss(self):
        folds = [
            {"predictive_distribution": {"total_covered": True, "bin_coverage": 0.8}},
            {"predictive_distribution": {"total_covered": False, "bin_coverage": 0.6}},
        ]
        result = predictive_coverage(folds)
        self.assertEqual(result["covered"], 1)
        self.assertEqual(result["missed"], 1)
        self.assertEqual(result["coverage"], 0.5)
        self.assertAlmostEqual(result["mean_bin_coverage"], 0.7)


if __name__ == "__main__":
    unittest.main()
