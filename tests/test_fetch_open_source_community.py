import io
import json
import unittest
from unittest.mock import patch

from fetch_open_source_community import fetch_public_repositories


class FetchOpenSourceCommunityTests(unittest.TestCase):
    def test_repository_listing_is_paginated_and_forks_are_excluded(self):
        first_page = [{"name": f"repo-{index:03d}", "fork": False} for index in range(100)]
        second_page = [
            {"name": "last", "fork": False},
            {"name": "upstream-fork", "fork": True},
        ]
        responses = [
            io.BytesIO(json.dumps(first_page).encode("utf-8")),
            io.BytesIO(json.dumps(second_page).encode("utf-8")),
        ]
        with patch("urllib.request.urlopen", side_effect=responses) as urlopen:
            repositories = fetch_public_repositories()
        self.assertEqual(len(repositories), 101)
        self.assertNotIn("upstream-fork", {repo["name"] for repo in repositories})
        self.assertIn("page=1", urlopen.call_args_list[0].args[0].full_url)
        self.assertIn("page=2", urlopen.call_args_list[1].args[0].full_url)


if __name__ == "__main__":
    unittest.main()
