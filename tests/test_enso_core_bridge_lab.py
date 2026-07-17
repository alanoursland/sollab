import unittest

from enso_core_bridge_lab import BridgeModel, fit_bridge, transform_wind


class EnsoCoreBridgeLabTests(unittest.TestCase):
    def setUp(self):
        self.core = {(2000, month): float(month) for month in range(1, 13)}
        self.r1 = {key: 1.5 + 0.8 * value for key, value in self.core.items()}

    def test_identity_bridge_does_not_touch_values(self):
        model = fit_bridge(self.core, self.r1, (2000,), {"kind": "identity"})
        self.assertEqual(transform_wind(self.core, model), self.core)

    def test_affine_bridge_recovers_known_instrument_mapping(self):
        model = fit_bridge(self.core, self.r1, (2000,), {"kind": "affine", "alpha": 0.0})
        self.assertAlmostEqual(model.intercept, 1.5, places=10)
        self.assertAlmostEqual(model.slope, 0.8, places=10)

    def test_bridge_model_is_a_scalar_observation_transform(self):
        model = BridgeModel("affine", 0.1, -0.25, 1.2)
        self.assertAlmostEqual(model.predict(2.0), 2.15)


if __name__ == "__main__":
    unittest.main()
