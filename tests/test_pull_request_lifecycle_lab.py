import json
import math
import unittest
from datetime import datetime, timezone

import numpy as np

from pull_request_lifecycle_lab import (
    PullRequestSequence,
    TYPE_CLOSE,
    TYPE_MERGE,
    TYPE_RESPONSE,
    author_origin,
    build_sequence,
    interval_exposure,
    make_process,
    maximum_likelihood_rates,
    piecewise_statistics,
    sequence_log_likelihood,
    sufficient_statistics,
)


class PullRequestLifecycleLabTests(unittest.TestCase):
    def test_author_origin_separates_automation_without_retaining_login(self):
        self.assertEqual(author_origin("CONTRIBUTOR", "dependency[bot]"), "automation")
        self.assertEqual(author_origin("MEMBER", "maintainer"), "maintainer")
        self.assertEqual(author_origin("NONE", "person"), "external")

    def test_sequence_keeps_first_causal_maintainer_response_and_terminal(self):
        pull = {
            "number": 10,
            "created_at": "2024-01-01T00:00:00Z",
            "merged_at": "2024-01-03T00:00:00Z",
            "closed_at": "2024-01-03T00:00:00Z",
            "author_login": "author",
            "author_association": "NONE",
            "issue_comment_events": [
                {"created_at": "2024-01-01T06:00:00Z", "author_login": "author", "author_association": "NONE"},
                {"created_at": "2024-01-01T12:00:00Z", "author_login": "maintainer", "author_association": "MEMBER"},
                {"created_at": "2024-01-04T00:00:00Z", "author_login": "late", "author_association": "MEMBER"},
            ],
            "reviews": [],
        }
        sequence = build_sequence(
            "flask", pull, datetime(2025, 12, 31, tzinfo=timezone.utc)
        )
        self.assertEqual(sequence.event_types, (TYPE_RESPONSE, TYPE_MERGE))
        self.assertEqual(sequence.event_times, (0.5, 2.0))
        self.assertEqual(sequence.duration_days, 2.0)

    def test_post_cutoff_close_is_right_censored(self):
        pull = {
            "number": 11,
            "created_at": "2024-01-01T00:00:00Z",
            "merged_at": None,
            "closed_at": "2026-01-02T00:00:00Z",
            "author_login": "author",
            "author_association": "CONTRIBUTOR",
            "issue_comment_events": [],
            "reviews": [],
        }
        sequence = build_sequence(
            "quart", pull, datetime(2025, 1, 1, tzinfo=timezone.utc)
        )
        self.assertIsNone(sequence.terminal_type)
        self.assertEqual(sequence.event_types, ())
        self.assertEqual(sequence.duration_days, 366.0)

    def test_kinopulse_likelihood_matches_one_shot_absorbing_oracle(self):
        sequences = [
            PullRequestSequence("flask", 1, "external", 2.0, (0.5, 2.0), (TYPE_RESPONSE, TYPE_MERGE), TYPE_MERGE, 0.5),
            PullRequestSequence("quart", 2, "external", 3.0, (3.0,), (TYPE_CLOSE,), TYPE_CLOSE, None),
        ]
        counts, exposure = sufficient_statistics(sequences)
        np.testing.assert_allclose(counts, [1, 1, 1])
        np.testing.assert_allclose(exposure, [3.5, 5.0, 5.0])
        rates = maximum_likelihood_rates(sequences)
        package = sum(sequence_log_likelihood(make_process(), value, rates) for value in sequences)
        oracle = float(np.sum(counts * np.log(rates)) - np.sum(rates * exposure))
        self.assertTrue(math.isclose(package, oracle, abs_tol=1e-9))

    def test_piecewise_exposure_and_counts_respect_boundaries(self):
        np.testing.assert_allclose(interval_exposure(8.0, (0.0, 1.0, 7.0)), [1.0, 6.0, 1.0])
        sequence = PullRequestSequence(
            "flask", 1, "external", 8.0, (0.5, 8.0), (TYPE_RESPONSE, TYPE_CLOSE), TYPE_CLOSE, 0.5
        )
        counts, exposure = piecewise_statistics([sequence], (0.0, 1.0, 7.0))
        self.assertEqual(counts[0, TYPE_RESPONSE], 1)
        self.assertEqual(counts[2, TYPE_CLOSE], 1)
        np.testing.assert_allclose(exposure[:, TYPE_RESPONSE], [0.5, 0.0, 0.0])
        np.testing.assert_allclose(exposure[:, TYPE_MERGE], [1.0, 6.0, 1.0])

    def test_sequence_contract_is_identity_free(self):
        sequence = PullRequestSequence("flask", 1, "external", 1.0, (1.0,), (TYPE_MERGE,), TYPE_MERGE, None)
        serialized = json.dumps(sequence.__dict__)
        self.assertNotIn("login", serialized)
        self.assertNotIn("author_login", serialized)
        self.assertNotIn("reviewer_login", serialized)


if __name__ == "__main__":
    unittest.main()
