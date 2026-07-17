import math
import unittest

import numpy as np

from enso_oscillator_lab import (
    ScalarForecastModel,
    actual_year,
    fit_model,
    forecast_year,
    paired_year_comparison,
    previous_month,
    regime_key,
)


def synthetic_observations(start=1998, stop=2005):
    values = {}
    for year in range(start, stop + 1):
        for month in range(1, 13):
            index = (year - start) * 12 + month
            values[(year, month)] = math.sin(index * 2 * math.pi / 30) + 0.1 * math.cos(month * 2 * math.pi / 12)
    return values


class EnsoOscillatorLabTests(unittest.TestCase):
    def test_previous_month_crosses_year_boundary(self):
        self.assertEqual(previous_month(2020, 1), (2019, 12))
        self.assertEqual(previous_month(2020, 1, 2), (2019, 11))

    def test_persistence_forecast_is_recursive_and_constant(self):
        observations = synthetic_observations()
        forecast = forecast_year(ScalarForecastModel("persistence"), observations, 2002)
        self.assertTrue(np.allclose(forecast, observations[(2001, 12)]))

    def test_fit_does_not_use_out_of_group_future_targets(self):
        observations = synthetic_observations()
        model_a = fit_model(observations, (1999, 2000, 2001), {"kind": "delayed_oscillator", "alpha": 0.1})
        changed = dict(observations)
        for month in range(1, 13):
            changed[(2004, month)] += 1000.0
        model_b = fit_model(changed, (1999, 2000, 2001), {"kind": "delayed_oscillator", "alpha": 0.1})
        self.assertTrue(np.allclose(model_a.coefficients["all"], model_b.coefficients["all"]))

    def test_actual_year_preserves_month_order(self):
        observations = synthetic_observations()
        expected = [observations[(2001, month)] for month in range(1, 13)]
        self.assertTrue(np.allclose(actual_year(observations, 2001), expected))

    def test_threshold_regimes_have_strict_boundaries(self):
        self.assertEqual(regime_key(-0.51, 0.5), "cold")
        self.assertEqual(regime_key(-0.5, 0.5), "neutral")
        self.assertEqual(regime_key(0.5, 0.5), "neutral")
        self.assertEqual(regime_key(0.51, 0.5), "warm")

    def test_paired_comparison_counts_years_not_months(self):
        observed = [[0.0] * 12, [0.0] * 12]
        challenger = {"forecast": [[0.0] * 12, [2.0] * 12], "actual": observed, "rmse": math.sqrt(2.0)}
        reference = {"forecast": [[1.0] * 12, [3.0] * 12], "actual": observed, "rmse": math.sqrt(5.0)}
        result = paired_year_comparison(challenger, reference, bootstrap_samples=100)
        self.assertEqual(result["years"], 2)
        self.assertEqual(result["challenger_wins"], 2)
        self.assertEqual(result["exact_paired_sign_randomization_one_sided_p"], 0.25)


if __name__ == "__main__":
    unittest.main()
