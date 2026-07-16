import copy
import unittest

from external_uncertainty_lab import (
    apply_interval_calibration,
    conservative_quantile,
    evaluate_intervals,
    fit_interval_calibration,
)


def fold(event_id, observed, lower, median, upper, time="2019-01-01"):
    return {
        "event_id": event_id,
        "name": event_id,
        "time": time,
        "evaluation_events": observed,
        "predictive_distribution": {
            "total_p10": lower,
            "total_median": median,
            "total_p90": upper,
        },
    }


class ExternalUncertaintyLabTests(unittest.TestCase):
    def test_conservative_quantile_uses_n_plus_one_rank(self):
        value, rank = conservative_quantile(list(range(23)), 0.8)
        self.assertEqual(rank, 20)
        self.assertEqual(value, 19)

    def test_calibration_only_expands_source_interval(self):
        calibration_folds = [
            fold(str(index), observed, 8.0, 10.0, 12.0)
            for index, observed in enumerate(
                [4, 6, 8, 9, 10, 11, 12, 14, 16, 20, 7, 13]
            )
        ]
        target = fold("target", 10.0, 8.0, 10.0, 12.0)
        calibration = fit_interval_calibration(
            calibration_folds, alpha=0.2, asymmetric=True
        )
        lower, upper = apply_interval_calibration(target, calibration)
        self.assertLessEqual(lower, 8.0)
        self.assertGreaterEqual(upper, 12.0)

    def test_future_outcome_cannot_change_fitted_calibration(self):
        calibration_folds = [
            fold(str(index), float(index + 5), 5.0, 10.0, 15.0)
            for index in range(12)
        ]
        future = fold("future", 10.0, 8.0, 10.0, 12.0, "2022-01-01")
        first = fit_interval_calibration(
            calibration_folds, alpha=0.2, asymmetric=False
        )
        changed = copy.deepcopy(future)
        changed["evaluation_events"] = 100000.0
        second = fit_interval_calibration(
            calibration_folds, alpha=0.2, asymmetric=False
        )
        self.assertEqual(first, second)
        self.assertNotEqual(
            evaluate_intervals([future], first)["coverage"],
            evaluate_intervals([changed], first)["coverage"],
        )


if __name__ == "__main__":
    unittest.main()
