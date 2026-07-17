import unittest

from enso_wind_heat_lab import HeatRow, build_rows, fit_heat_model, predict_change, shift_month


class EnsoWindHeatLabTests(unittest.TestCase):
    def test_shift_month_crosses_year_boundary(self):
        self.assertEqual(shift_month((2020, 12), 1), (2021, 1))
        self.assertEqual(shift_month((2020, 1), -2), (2019, 11))

    def test_target_value_never_enters_features(self):
        keys = [(2000 + index // 12, index % 12 + 1) for index in range(48)]
        mei = {key: index * 0.1 for index, key in enumerate(keys)}
        heat = {key: index * 0.2 for index, key in enumerate(keys)}
        wind = {key: index * -0.3 for index, key in enumerate(keys)}
        original = build_rows(mei, heat, wind, "state_plus_wind")
        changed = dict(heat)
        changed[(2002, 6)] += 999.0
        replay = build_rows(mei, changed, wind, "state_plus_wind")
        target_original = next(row for row in original if (row.target_year, row.target_month) == (2002, 6))
        target_replay = next(row for row in replay if (row.target_year, row.target_month) == (2002, 6))
        self.assertEqual(target_original.features, target_replay.features)
        self.assertNotEqual(target_original.actual_next_heat, target_replay.actual_next_heat)

    def test_persistence_predicts_zero_change(self):
        row = HeatRow(2020, 1, 0.4, 0.7, (1.0,))
        model = fit_heat_model([row], (2020,), {"kind": "persistence"})
        self.assertEqual(predict_change(model, row), 0.0)


if __name__ == "__main__":
    unittest.main()
