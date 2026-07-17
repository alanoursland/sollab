import unittest

import numpy as np

from enso_recharge_lab import (
    coupled_features,
    fit_coupled_model,
    forecast_coupled,
    state_matrix,
)


def synthetic_states(start=1998, stop=2008):
    mei = {}
    heat = {}
    state = np.array([0.2, 0.5])
    transition = np.array([[0.8, 0.25], [-0.15, 0.9]])
    for year in range(start, stop + 1):
        for month in range(1, 13):
            state = transition @ state
            mei[(year, month)] = float(state[0])
            heat[(year, month)] = float(state[1])
    return mei, heat


class EnsoRechargeLabTests(unittest.TestCase):
    def test_delayed_features_include_both_previous_states(self):
        features = coupled_features("delayed_recharge", (1.0, 2.0), (3.0, 4.0), 1)
        self.assertEqual(features[:5], [1.0, 1.0, 2.0, 3.0, 4.0])

    def test_coupled_forecast_is_recursive(self):
        mei, heat = synthetic_states()
        model = fit_coupled_model(mei, heat, range(1999, 2005), {"kind": "recharge", "alpha": 0.001})
        original = forecast_coupled(model, mei, heat, 2006)
        changed = dict(mei)
        for month in range(1, 13):
            changed[(2006, month)] = 999.0
        replay = forecast_coupled(model, changed, heat, 2006)
        self.assertTrue(np.allclose(original, replay))

    def test_state_matrix_has_two_by_two_shape(self):
        mei, heat = synthetic_states()
        model = fit_coupled_model(mei, heat, range(1999, 2005), {"kind": "recharge", "alpha": 0.01})
        self.assertEqual(state_matrix(model).shape, (2, 2))


if __name__ == "__main__":
    unittest.main()
