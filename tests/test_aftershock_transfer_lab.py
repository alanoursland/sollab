import math
import unittest

import torch

from aftershock_lab import DTYPE, _encode_p
from aftershock_transfer_lab import (
    CALIBRATION_END_DAYS,
    SequenceData,
    calibrate_amplitude,
    fit_shared_shape,
    make_transfer_bins,
    shared_expected_counts,
)
from fetch_aftershock_benchmark import SEQUENCES


class AftershockTransferLabTests(unittest.TestCase):
    def setUp(self):
        self.edges = make_transfer_bins()
        self.calibration = self.edges[1:] <= CALIBRATION_END_DAYS

    def test_bins_contain_exact_calibration_boundary(self):
        self.assertEqual(float(self.edges[12]), CALIBRATION_END_DAYS)

    def test_shared_kinopulse_fit_recovers_synthetic_shape(self):
        amplitudes = [20.0, 80.0, 250.0]
        theta = torch.tensor(
            [
                *torch.log(torch.tensor(amplitudes, dtype=DTYPE)).tolist(),
                torch.log(torch.tensor(0.1, dtype=DTYPE)),
                _encode_p(1.0),
            ],
            dtype=DTYPE,
        )
        backgrounds = torch.zeros(3, dtype=DTYPE)
        expected = shared_expected_counts(
            theta, self.edges, backgrounds, "omori"
        )
        sequences = [
            SequenceData(
                spec=SEQUENCES[index],
                times_days=torch.empty(0, dtype=DTYPE),
                counts=expected[index],
                background=0.0,
                sha256="synthetic",
                source_rows=0,
            )
            for index in range(3)
        ]
        fit = fit_shared_shape(sequences, self.edges, "omori")
        self.assertAlmostEqual(fit.parameters["c_days"], 0.1, delta=1e-5)
        self.assertAlmostEqual(fit.parameters["p"], 1.0, delta=1e-5)

    def test_amplitude_calibration_ignores_future_counts(self):
        shape = {"c_days": 0.1, "p": 1.0}
        theta = torch.tensor(
            [math.log(50.0), math.log(0.1), _encode_p(1.0)],
            dtype=DTYPE,
        )
        expected = shared_expected_counts(
            theta,
            self.edges,
            torch.zeros(1, dtype=DTYPE),
            "omori",
        )[0]
        corrupted = expected.clone()
        corrupted[~self.calibration] = 1_000_000.0
        amplitude, _ = calibrate_amplitude(
            corrupted,
            self.edges,
            self.calibration,
            0.0,
            "omori",
            shape,
        )
        self.assertAlmostEqual(amplitude, 50.0, delta=1e-5)


if __name__ == "__main__":
    unittest.main()
