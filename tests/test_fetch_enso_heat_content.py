import unittest

from fetch_meiv2 import parse_psl_monthly


class FetchEnsoHeatContentTests(unittest.TestCase):
    def test_generic_parser_accepts_heat_content_values(self):
        text = """1979 1979
1979 -0.12 -0.04 0.11 0.20 0.34 0.30 0.18 0.02 -0.09 -0.14 -99.9 -0.18
-99.99
"""
        records = parse_psl_monthly(text)
        self.assertEqual(records[0], {"year": 1979, "month": 1, "value": -0.12})
        self.assertIsNone(records[-2]["value"])
        self.assertEqual(records[-1], {"year": 1979, "month": 12, "value": -0.18})


if __name__ == "__main__":
    unittest.main()
