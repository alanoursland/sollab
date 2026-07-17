import math
import unittest
from datetime import datetime, timedelta, timezone

from merge_topology_audit_lab import (
    TopologyCommit,
    cohort_return_rate,
    fit_observation_map,
    parse_topology_log,
    weekly_topology,
)


class MergeTopologyAuditLabTests(unittest.TestCase):
    def test_parser_preserves_topology_and_conservative_pr_hints(self):
        text = (
            "a\x1f2025-01-01T00:00:00+00:00\x1fdev@example.org\x1fDev\x1fp1 p2"
            "\x1fMerge pull request #12 from branch\x00"
            "b\x1f2025-01-02T00:00:00+00:00\x1fother@example.org\x1fOther\x1fa"
            "\x1fFix parser (#13)\x00"
        )
        commits = parse_topology_log("demo", text, {"a", "b"})
        self.assertTrue(commits[0].is_merge)
        self.assertTrue(commits[0].is_explicit_pr_merge)
        self.assertFalse(commits[0].has_pr_suffix)
        self.assertTrue(commits[1].has_pr_suffix)

    def test_weekly_views_preserve_empty_weeks_and_author_coverage(self):
        start = datetime(2025, 1, 6, tzinfo=timezone.utc)
        commits = [
            TopologyCommit("r", "a", start, "one", False, 1, "main", True),
            TopologyCommit("r", "b", start, "two", False, 1, "side", False),
            TopologyCommit("r", "c", start + timedelta(weeks=2), "one", False, 2, "merge", True),
        ]
        rows = weekly_topology(commits, start + timedelta(weeks=2))
        self.assertEqual([row["all_commits"] for row in rows], [2, 0, 1])
        self.assertEqual(rows[0]["first_parent_commits"], 1)
        self.assertEqual(rows[0]["all_authors"], 2)
        self.assertEqual(rows[2]["merge_commits"], 1)

    def test_return_rate_changes_when_side_history_is_removed(self):
        start = datetime(2015, 1, 5, tzinfo=timezone.utc)
        full = [
            TopologyCommit("r", "a", start, "one", False, 1, "main", True),
            TopologyCommit("r", "b", start + timedelta(weeks=4), "one", False, 1, "side", False),
        ]
        end = start + timedelta(weeks=60)
        full_rate = cohort_return_rate([commit.as_commit() for commit in full], end, 2015, 2015)
        first_rate = cohort_return_rate(
            [commit.as_commit() for commit in full if commit.first_parent], end, 2015, 2015
        )
        self.assertEqual(full_rate["return_rate_52w"], 1.0)
        self.assertEqual(first_rate["return_rate_52w"], 0.0)

    def test_observation_map_returns_finite_chronological_scores(self):
        weekly = [
            {
                "all_commits": 2 + index % 3,
                "first_parent_commits": 1 + index % 2,
                "merge_commits": index % 2,
                "single_parent_pr_suffix_commits": (index + 1) % 2,
            }
            for index in range(30)
        ]
        result = fit_observation_map(weekly)
        self.assertTrue(math.isfinite(result["ridge_holdout_rmse"]))
        self.assertGreater(result["split"], 1)


if __name__ == "__main__":
    unittest.main()
