import unittest

import torch

from aftershock_lab import DTYPE
from external_sequential_monitor_lab import (
    _binary_summary,
    first_alarm_record,
)


class ExternalSequentialMonitorLabTests(unittest.TestCase):
    def test_first_alarm_is_preserved_when_later_counts_change(self):
        expected = torch.full((12,), 5.0, dtype=DTYPE)
        observed = expected.clone()
        observed[3:8] = 20.0
        starts = torch.arange(12, dtype=DTYPE)
        ends = starts + 1.0
        first = first_alarm_record(observed, expected, 10.0, starts, ends)
        changed = observed.clone()
        changed[10:] = 1000.0
        second = first_alarm_record(changed, expected, 10.0, starts, ends)
        self.assertIsNotNone(first["first_alarm_bin"])
        self.assertEqual(first["first_alarm_bin"], second["first_alarm_bin"])
        self.assertEqual(first["estimated_change_bin"], second["estimated_change_bin"])

    def test_binary_summary_counts_rejected_successes(self):
        records = [
            {"event_id": "caught", "miss": True, "first_alarm_bin": 5},
            {"event_id": "rejected_success", "miss": False, "first_alarm_bin": 4},
            {"event_id": "quiet_success", "miss": False, "first_alarm_bin": None},
            {"event_id": "quiet_miss", "miss": True, "first_alarm_bin": None},
        ]
        result = _binary_summary(records, "miss")
        self.assertEqual(result["positive_alarmed"], 1)
        self.assertEqual(result["negative_alarmed"], 1)
        self.assertEqual(result["alarm_precision"], 0.5)
        self.assertEqual(result["quiet_negative_fraction"], 0.5)


if __name__ == "__main__":
    unittest.main()
