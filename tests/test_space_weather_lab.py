import unittest

import torch

from space_weather_lab import OmniData, fit_models, parse_omni_lines


class SpaceWeatherLabTests(unittest.TestCase):
    def test_parser_maps_columns_and_fill_values(self):
        valid = [0.0] * 55
        valid[0:3] = [2015, 1, 0]
        valid[16], valid[24], valid[28], valid[35], valid[40] = -5, 450, 2, 2.25, -40
        missing = valid.copy()
        missing[16] = 999.9
        data = parse_omni_lines((" ".join(map(str, valid)), " ".join(map(str, missing))))
        self.assertEqual(data.bz_gsm[0].item(), -5)
        self.assertEqual(data.dst[0].item(), -40)
        self.assertTrue(data.valid[0])
        self.assertFalse(data.valid[1])

    def test_forced_linear_law_is_recovered(self):
        n = 240
        generator = torch.Generator().manual_seed(4)
        electric = torch.rand(n, generator=generator, dtype=torch.float64) * 3
        pressure = 2 + torch.randn(n, generator=generator, dtype=torch.float64) * 0.1
        dst = torch.zeros(n, dtype=torch.float64)
        for index in range(n - 1):
            dst[index + 1] = dst[index] - 0.08 * dst[index] - 1.7 * electric[index]
        hours = torch.arange(n, dtype=torch.float64) % 24
        days = 1 + torch.arange(n, dtype=torch.float64) // 24
        data = OmniData(
            torch.full((n,), 2015.0), days, hours, -electric, torch.full((n,), 450.0),
            pressure, electric, dst, torch.ones(n, dtype=torch.bool)
        )
        continuous, _, prepared = fit_models(data)
        _, held, _, design, target, _, _ = prepared
        prediction = design @ continuous
        self.assertLess(torch.sqrt(torch.mean((prediction[~held] - target[~held]) ** 2)).item(), 0.02)


if __name__ == "__main__":
    unittest.main()
