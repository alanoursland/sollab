import unittest

from fetch_meiv2 import parse_meiv2


class FetchMeiv2Tests(unittest.TestCase):
    def test_parser_preserves_months_and_missing_slots(self):
        text = """2020 2021
2020  0.1 0.2 0.3 0.4 0.5 0.6 0.7 0.8 0.9 1.0 1.1 1.2
2021  1.3 1.4 -999.0 1.6 1.7 1.8 1.9 2.0 2.1 2.2 2.3 2.4
-999.0
"""
        records = parse_meiv2(text)
        self.assertEqual(len(records), 24)
        self.assertEqual(records[0], {"year": 2020, "month": 1, "value": 0.1})
        self.assertIsNone(records[14]["value"])
        self.assertEqual(records[-1], {"year": 2021, "month": 12, "value": 2.4})

    def test_parser_rejects_missing_year_rows(self):
        text = """2020 2021
2020  0 0 0 0 0 0 0 0 0 0 0 0
"""
        with self.assertRaises(ValueError):
            parse_meiv2(text)


if __name__ == "__main__":
    unittest.main()
