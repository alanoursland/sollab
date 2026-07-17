import unittest

from fetch_pull_request_panel import evenly_spaced_sample


class FetchPullRequestPanelTests(unittest.TestCase):
    def test_evenly_spaced_sample_includes_endpoints_and_is_stable(self):
        items = [{"number": number} for number in range(19)]
        sample = evenly_spaced_sample(items, 5)
        self.assertEqual([item["number"] for item in sample], [0, 4, 9, 14, 18])

    def test_small_population_is_not_duplicated(self):
        items = [{"number": number} for number in range(3)]
        self.assertEqual(evenly_spaced_sample(items, 10), items)

    def test_nonpositive_sample_size_is_rejected(self):
        with self.assertRaises(ValueError):
            evenly_spaced_sample([{"number": 1}], 0)


if __name__ == "__main__":
    unittest.main()
