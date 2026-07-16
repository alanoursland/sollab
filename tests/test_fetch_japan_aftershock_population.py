import unittest

from fetch_external_aftershock_population import ALASKA_2010_2025
from fetch_japan_aftershock_population import JAPAN_KURIL_2016_2025


class JapanAftershockPopulationFetchTests(unittest.TestCase):
    def test_protocol_fields_match_first_external_geography(self):
        protocol_fields = (
            "format",
            "minmagnitude",
            "eventtype",
            "orderby",
            "limit",
        )
        for field in protocol_fields:
            self.assertEqual(
                JAPAN_KURIL_2016_2025.query[field],
                ALASKA_2010_2025.query[field],
            )

    def test_bounds_and_dates_are_frozen(self):
        self.assertEqual(
            {
                key: JAPAN_KURIL_2016_2025.query[key]
                for key in (
                    "starttime",
                    "endtime",
                    "minlatitude",
                    "maxlatitude",
                    "minlongitude",
                    "maxlongitude",
                )
            },
            {
                "starttime": "2016-01-01",
                "endtime": "2026-01-01",
                "minlatitude": "30",
                "maxlatitude": "50",
                "minlongitude": "125",
                "maxlongitude": "150",
            },
        )

    def test_candidate_url_is_stable(self):
        self.assertIn("minmagnitude=5.8", JAPAN_KURIL_2016_2025.candidate_url)
        self.assertIn("minlongitude=125", JAPAN_KURIL_2016_2025.candidate_url)
        self.assertIn("maxlongitude=150", JAPAN_KURIL_2016_2025.candidate_url)


if __name__ == "__main__":
    unittest.main()
