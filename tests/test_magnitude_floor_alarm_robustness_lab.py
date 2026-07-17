import tempfile
import unittest
from pathlib import Path

import torch

from aftershock_transfer_lab import SequenceData
from fetch_aftershock_benchmark import SequenceSpec
from magnitude_floor_alarm_robustness_lab import (
    event_support,
    load_sequence_at_floor,
    repeat_summary,
    summarize_floor,
)


class MagnitudeFloorAlarmRobustnessLabTests(unittest.TestCase):
    def test_loader_reapplies_floor_to_control_and_forecast_windows(self):
        spec = SequenceSpec(
            slug="target",
            name="target",
            event_id="main",
            time="2020-01-31T00:00:00Z",
            latitude=0.0,
            longitude=0.0,
            magnitude=6.0,
        )
        csv_text = "\n".join(
            [
                "time,latitude,longitude,depth,mag,magType,nst,gap,dmin,rms,net,id,updated,place,type,horizontalError,depthError,magError,magNst,status,locationSource,magSource",
                "2020-01-01T00:00:00Z,0,0,1,3.2,ml,,,,,us,control,,,,,,,,,,",
                "2020-01-31T00:00:00Z,0,0,1,6.0,mw,,,,,us,main,,,,,,,,,,",
                "2020-01-31T12:00:00Z,0,0,1,2.9,ml,,,,,us,low,,,,,,,,,,",
                "2020-01-31T14:00:00Z,0,0,1,nan,ml,,,,,us,nonfinite,,,,,,,,,,",
                "2020-01-31T18:00:00Z,0,0,1,3.1,ml,,,,,us,kept,,,,,,,,,,",
                "2020-02-02T00:00:00Z,0,0,1,3.5,ml,,,,,us,later,,,,,,,,,,",
            ]
        )
        edges = torch.tensor([1.0 / 24.0, 1.0, 3.0], dtype=torch.float64)
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "target.csv").write_text(csv_text, encoding="utf-8")
            sequence = load_sequence_at_floor(spec, edges, Path(directory), 3.0)
        self.assertEqual(sequence.counts.tolist(), [1.0, 1.0])
        self.assertAlmostEqual(sequence.background, 1.0 / 28.0)

    def test_event_support_enforces_both_windows(self):
        sequence = SequenceData(
            spec=None,
            times_days=torch.tensor([], dtype=torch.float64),
            counts=torch.tensor([15.0, 14.0], dtype=torch.float64),
            background=0.0,
            sha256="",
            source_rows=0,
        )
        support = event_support(
            sequence,
            torch.tensor([True, False]),
            torch.tensor([False, True]),
        )
        self.assertFalse(support["eligible"])
        self.assertEqual(support["calibration_events"], 15)
        self.assertEqual(support["evaluation_events"], 14)

    def test_repeat_summary_distinguishes_majority_from_unanimity(self):
        repeats = [
            {
                "alarm": alarm,
                "first_alarm_day": 2.0 if alarm else None,
                "threshold": threshold,
                "direction": "lower" if alarm else None,
                "proposal_effective_sample_size": 100.0,
            }
            for alarm, threshold in zip((True, True, True, False), (9.0, 10.0, 11.0, 12.0))
        ]
        summary = repeat_summary(repeats)
        self.assertTrue(summary["majority_alarm"])
        self.assertFalse(summary["unanimous_alarm"])
        self.assertEqual(summary["alarm_fraction"], 0.75)
        self.assertEqual(summary["threshold_median"], 10.5)

    def test_floor_summary_lists_reference_alarms_only_when_eligible(self):
        records = [
            {
                "event_id": "us10004x1w",
                "unanimous_alarm": True,
                "majority_alarm": True,
            },
            {
                "event_id": "quiet",
                "unanimous_alarm": False,
                "majority_alarm": False,
            },
        ]
        summary = summarize_floor(records)
        self.assertEqual(summary["eligible_external_sequences"], 2)
        self.assertEqual(summary["unanimous_alarm_event_ids"], ["us10004x1w"])
        self.assertEqual(
            summary["eligible_reference_alarm_event_ids"], ["us10004x1w"]
        )


if __name__ == "__main__":
    unittest.main()
