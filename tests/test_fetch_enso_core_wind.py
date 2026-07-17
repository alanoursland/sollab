import unittest

from fetch_enso_core_wind import extract_csv_url, parse_core_csv


class FetchEnsoCoreWindTests(unittest.TestCase):
    def test_parser_preserves_months_and_rejects_missing_sentinel(self):
        rows = parse_core_csv(
            "Date, NOAA CORe Zonal Wind (m/s) -5S-5N;140E-190E\n"
            "2026-05-01, -0.138\n"
            "2026-06-01, 4.103\n"
            "2026-07-01,-9999.000\n"
        )
        self.assertEqual(rows[0], {"year": 2026, "month": 5, "value": -0.138})
        self.assertEqual(rows[-1], {"year": 2026, "month": 7, "value": None})

    def test_generated_csv_link_is_promoted_to_absolute_https(self):
        html = '<a href="/tmp/file1abc.csv">CSV</a>'
        self.assertEqual(extract_csv_url(html), "https://psl.noaa.gov/tmp/file1abc.csv")


if __name__ == "__main__":
    unittest.main()
