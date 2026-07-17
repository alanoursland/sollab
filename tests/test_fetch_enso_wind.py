import unittest

from fetch_meiv2 import parse_psl_monthly


class FetchEnsoWindTests(unittest.TestCase):
    def test_parser_treats_wind_archive_sentinel_as_missing(self):
        text = """2025 2025
2025 -4.1 -3.8 -5.6 -2.9 -2.6 -1.3 -2.6 -2.2 -2.3 -3.7 -2.4 -9999
-9999
"""
        records = parse_psl_monthly(text)
        self.assertEqual(records[0]["value"], -4.1)
        self.assertIsNone(records[-1]["value"])


if __name__ == "__main__":
    unittest.main()
