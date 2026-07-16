import copy
import unittest

from abstention_audit_lab import audited_forecasts, forecast_inputs, target_decision


def fold(
    event_id,
    magnitude=6.0,
    depth=10.0,
    background=0.2,
    day1=20,
    time="2020-01-01T00:00:00Z",
):
    return {
        "event_id": event_id,
        "name": event_id,
        "time": time,
        "magnitude": magnitude,
        "depth_km": depth,
        "background_rate_per_day": background,
        "calibration_events": day1,
        "evaluation_events": 100,
        "models": {
            "frozen_hierarchy": {"predicted_total": 100.0},
            "robust_pool": {"predicted_total": 80.0},
            "target_day1": {"predicted_total": 120.0},
        },
        "predictive_distribution": {
            "total_p10": 60.0,
            "total_median": 100.0,
            "total_p90": 150.0,
        },
    }


def forecast(width=4.0):
    return {"multiplicative_width": width}


class AbstentionAuditLabTests(unittest.TestCase):
    def setUp(self):
        self.history = [
            fold(
                str(index),
                magnitude=5.8 + 0.1 * (index % 5),
                depth=5.0 + index,
                background=0.1 + 0.02 * index,
                day1=10 + index,
            )
            for index in range(12)
        ]
        self.target = fold("target", magnitude=6.1, depth=14, background=0.24, day1=19)

    def test_target_outcome_cannot_change_decision(self):
        first = target_decision(self.target, self.history, forecast())
        changed = copy.deepcopy(self.target)
        changed["evaluation_events"] = 1000000
        second = target_decision(changed, self.history, forecast())
        self.assertEqual(first, second)

    def test_future_object_is_not_an_input_to_decision(self):
        first = target_decision(self.target, self.history, forecast())
        future = fold("future", magnitude=9.0, day1=100000)
        _ = forecast_inputs(future)
        second = target_decision(self.target, self.history, forecast())
        self.assertEqual(first, second)

    def test_consensus_threshold_depends_only_on_history(self):
        first = target_decision(self.target, self.history, forecast())
        changed = copy.deepcopy(self.target)
        changed["models"]["target_day1"]["predicted_total"] = 10000.0
        second = target_decision(changed, self.history, forecast())
        self.assertEqual(first["consensus_threshold"], second["consensus_threshold"])
        self.assertGreater(
            second["forecast_disagreement"], first["forecast_disagreement"]
        )

    def test_combined_gate_requires_every_component(self):
        decision = target_decision(self.target, self.history, forecast(width=20.0))
        self.assertFalse(decision["policy_issue"]["sharpness_cap"])
        self.assertFalse(decision["policy_issue"]["combined"])

    def test_end_to_end_replay_excludes_immature_history(self):
        folds = [
            fold(str(index), time=f"{2000 + index:04d}-01-01T00:00:00Z")
            for index in range(12)
        ]
        folds.extend(
            [
                fold("recent", time="2020-03-15T00:00:00Z"),
                fold("target", time="2020-04-01T00:00:00Z"),
            ]
        )
        target_row = next(
            row for row in audited_forecasts(folds) if row["event_id"] == "target"
        )
        self.assertNotIn("recent", target_row["history_event_ids"])
        self.assertEqual(target_row["history_count"], 12)

    def test_changing_future_outcome_preserves_earlier_audit_row(self):
        folds = [
            fold(str(index), time=f"{2000 + index:04d}-01-01T00:00:00Z")
            for index in range(14)
        ]
        first = audited_forecasts(folds)
        changed = copy.deepcopy(folds)
        changed[-1]["evaluation_events"] = 1000000
        second = audited_forecasts(changed)
        self.assertEqual(first[-2], second[-2])
        self.assertEqual(
            first[-1]["policy_issue"], second[-1]["policy_issue"]
        )


if __name__ == "__main__":
    unittest.main()
