import unittest

from fetch_external_aftershock_population import (
    ALASKA_2010_2025,
    COHORTS,
    TEMPORAL_2026,
    console_safe,
)


class ExternalAftershockPopulationFetchTests(unittest.TestCase):
    def test_console_safe_escapes_unrepresentable_place_name(self):
        rendered = console_safe("Notoō", "cp1252")
        self.assertEqual(rendered, "Noto\\u014d")

    def test_cohort_names_and_queries_are_frozen(self):
        self.assertEqual(
            [cohort.slug for cohort in COHORTS],
            ["temporal_2026", "alaska_2010_2025"],
        )
        self.assertEqual(TEMPORAL_2026.query["endtime"], "2026-06-15")
        self.assertEqual(ALASKA_2010_2025.query["endtime"], "2026-01-01")

    def test_protocol_defining_query_fields_match(self):
        for field in ("format", "minmagnitude", "eventtype", "orderby", "limit"):
            self.assertEqual(
                TEMPORAL_2026.query[field], ALASKA_2010_2025.query[field]
            )

    def test_geographic_fallback_does_not_extend_temporal_claim(self):
        self.assertIn("temporally unseen", TEMPORAL_2026.role)
        self.assertIn("geographically external", ALASKA_2010_2025.role)
        self.assertNotEqual(
            TEMPORAL_2026.query["starttime"],
            ALASKA_2010_2025.query["starttime"],
        )


if __name__ == "__main__":
    unittest.main()
