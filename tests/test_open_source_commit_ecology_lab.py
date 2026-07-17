import math
import unittest
from datetime import datetime, timedelta, timezone

from open_source_commit_ecology_lab import (
    Commit,
    canonical_author,
    parse_git_log,
    persistence_trace,
    summarize_weekly,
)


class OpenSourceCommitEcologyLabTests(unittest.TestCase):
    def test_noreply_variants_canonicalize_to_same_github_identity(self):
        self.assertEqual(
            canonical_author("123+Example@users.noreply.github.com", "Example"),
            canonical_author("example@users.noreply.github.com", "Different Name"),
        )

    def test_git_log_parser_marks_bots_without_exporting_raw_identity(self):
        text = (
            "abc\x1f2026-01-01T00:00:00+00:00\x1fdev@example.org\x1fDev\x00"
            "def\x1f2026-01-02T00:00:00+00:00\x1f41898282+github-actions[bot]@users.noreply.github.com"
            "\x1fgithub-actions[bot]\x00"
        )
        commits = parse_git_log("demo", text)
        self.assertEqual(len(commits), 2)
        self.assertFalse(commits[0].is_bot)
        self.assertTrue(commits[1].is_bot)
        self.assertNotIn("Dev", commits[0].author)

    def test_weekly_summary_preserves_empty_weeks_and_trailing_identity_union(self):
        start = datetime(2026, 1, 5, tzinfo=timezone.utc)
        commits = [
            Commit("a", "1", start, "one", False),
            Commit("b", "2", start + timedelta(days=1), "two", False),
            Commit("a", "3", start + timedelta(days=15), "one", False),
            Commit("a", "4", start + timedelta(days=15), "robot", True),
        ]
        states = summarize_weekly(commits, start + timedelta(days=21))
        self.assertEqual([state.commits for state in states], [2, 0, 1, 0])
        self.assertEqual(states[2].bot_commits, 1)
        self.assertEqual(states[2].trailing_13w_contributors, 2)
        self.assertEqual(states[2].new_contributors, 0)

    def test_persistence_trace_returns_finite_online_slopes(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        commits = [
            Commit("demo", str(index), start + timedelta(days=7 * index), "one", False)
            for index in range(30)
        ]
        states = summarize_weekly(commits, start + timedelta(days=7 * 30))
        slopes = persistence_trace(states)
        self.assertEqual(len(slopes), len(states))
        self.assertTrue(math.isnan(slopes[0]))
        self.assertTrue(all(math.isfinite(value) for value in slopes[1:]))


if __name__ == "__main__":
    unittest.main()
