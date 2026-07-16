import unittest

from online_uncertainty_lab import (
    available_history_indices,
    prequential_forecasts,
)


def fold(event_id, time, observed=10.0):
    return {
        "event_id": event_id,
        "name": event_id,
        "time": time,
        "evaluation_events": observed,
        "predictive_distribution": {
            "total_p10": 8.0,
            "total_median": 10.0,
            "total_p90": 12.0,
        },
    }


class OnlineUncertaintyLabTests(unittest.TestCase):
    def test_outcome_maturity_embargo_excludes_recent_sequence(self):
        folds = [
            fold("old", "2020-01-01T00:00:00Z"),
            fold("recent", "2020-03-15T00:00:00Z"),
            fold("target", "2020-04-01T00:00:00Z"),
        ]
        self.assertEqual(available_history_indices(folds, 2), [0])

    def test_rolling_history_never_contains_target_or_future(self):
        folds = [
            fold(str(index), f"{2000 + index:04d}-01-01T00:00:00Z", index + 10.0)
            for index in range(16)
        ]
        result = prequential_forecasts(
            folds, mode="rolling", minimum_history=4, rolling_window=3
        )
        order = {item["event_id"]: index for index, item in enumerate(folds)}
        for row in result["rows"]:
            self.assertEqual(row["used_history_count"], 3)
            self.assertTrue(
                all(order[event_id] < order[row["event_id"]] for event_id in row["used_event_ids"])
            )

    def test_changing_future_outcome_cannot_change_earlier_forecast(self):
        folds = [
            fold(str(index), f"{2000 + index:04d}-01-01T00:00:00Z", index + 10.0)
            for index in range(16)
        ]
        first = prequential_forecasts(
            folds, mode="expanding", minimum_history=4
        )
        folds[-1]["evaluation_events"] = 100000.0
        second = prequential_forecasts(
            folds, mode="expanding", minimum_history=4
        )
        self.assertEqual(first["rows"][-2], second["rows"][-2])
        self.assertEqual(
            (first["rows"][-1]["lower"], first["rows"][-1]["upper"]),
            (second["rows"][-1]["lower"], second["rows"][-1]["upper"]),
        )


if __name__ == "__main__":
    unittest.main()
