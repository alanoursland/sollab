import math
import unittest

from pull_request_collaboration_lab import (
    causal_formal_reviews,
    causal_issue_comment_responses,
    integration_class,
    point_process_diagnostic,
)
from merge_topology_audit_lab import TopologyCommit
from datetime import datetime, timezone


class PullRequestCollaborationLabTests(unittest.TestCase):
    def test_causal_reviews_exclude_self_bot_and_post_merge_events(self):
        pull = {
            "created_at": "2024-01-01T00:00:00Z",
            "merged_at": "2024-01-03T00:00:00Z",
            "author_login": "author",
            "reviews": [
                {"reviewer_login": "reviewer", "submitted_at": "2024-01-02T00:00:00Z", "state": "APPROVED"},
                {"reviewer_login": "author", "submitted_at": "2024-01-02T01:00:00Z", "state": "COMMENTED"},
                {"reviewer_login": "ci[bot]", "submitted_at": "2024-01-02T02:00:00Z", "state": "COMMENTED"},
                {"reviewer_login": "late", "submitted_at": "2024-01-04T00:00:00Z", "state": "COMMENTED"},
            ],
        }
        reviews = causal_formal_reviews(pull)
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["hours"], 24.0)

    def test_integration_class_uses_frozen_commit_parents(self):
        commit = TopologyCommit(
            "repo", "abc", datetime(2024, 1, 1, tzinfo=timezone.utc), "author", False, 2, "merge", True
        )
        self.assertEqual(integration_class("abc", {"abc": commit}), "merge_commit")
        self.assertEqual(integration_class("missing", {"abc": commit}), "merge_sha_not_reachable")

    def test_issue_responses_exclude_author_and_post_merge_comments(self):
        pull = {
            "created_at": "2024-01-01T00:00:00Z",
            "merged_at": "2024-01-03T00:00:00Z",
            "author_login": "author",
            "issue_comment_events": [
                {"author_login": "maintainer", "created_at": "2024-01-01T12:00:00Z"},
                {"author_login": "author", "created_at": "2024-01-01T13:00:00Z"},
                {"author_login": "late", "created_at": "2024-01-04T00:00:00Z"},
            ],
        }
        responses = causal_issue_comment_responses(pull)
        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["hours"], 12.0)

    def test_homogeneous_diagnostic_handles_zero_review_streams(self):
        result = point_process_diagnostic([[2.0], [], [1.0, 3.0]], [4.0, 5.0, 6.0])
        self.assertEqual(result["total_events"], 3)
        self.assertTrue(math.isfinite(result["log_likelihood_at_mle"]))
        self.assertAlmostEqual(result["observed_zero_event_fraction"], 1 / 3)


if __name__ == "__main__":
    unittest.main()
