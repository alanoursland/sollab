import unittest

from fetch_pull_request_lifecycle_panel import compact_item, evenly_spaced_sample


class FetchPullRequestLifecyclePanelTests(unittest.TestCase):
    def test_evenly_spaced_sample_includes_population_endpoints(self):
        items = [{"number": number} for number in range(29)]
        sample = evenly_spaced_sample(items, 5)
        self.assertEqual([item["number"] for item in sample], [0, 7, 14, 21, 28])

    def test_compaction_preserves_terminal_and_activity_times(self):
        item = {
            "number": 7,
            "html_url": "https://example.test/7",
            "created_at": "2024-01-01T00:00:00Z",
            "closed_at": "2024-01-03T00:00:00Z",
            "state": "closed",
            "comments": 1,
            "user": {"login": "author"},
            "author_association": "NONE",
            "pull_request": {"merged_at": None, "draft": False},
        }
        reviews = [
            {
                "submitted_at": "2024-01-02T00:00:00Z",
                "state": "COMMENTED",
                "user": {"login": "reviewer"},
                "author_association": "MEMBER",
            }
        ]
        comments = [
            {
                "created_at": "2024-01-01T12:00:00Z",
                "user": {"login": "commenter"},
                "author_association": "MEMBER",
            }
        ]
        compact = compact_item(item, reviews, comments)
        self.assertIsNone(compact["merged_at"])
        self.assertEqual(compact["closed_at"], "2024-01-03T00:00:00Z")
        self.assertEqual(compact["reviews"][0]["submitted_at"], "2024-01-02T00:00:00Z")
        self.assertEqual(compact["issue_comment_events"][0]["created_at"], "2024-01-01T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
