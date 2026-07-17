import unittest

from fetch_omni_population import annual_url


class FetchOmniPopulationTests(unittest.TestCase):
    def test_annual_url_is_frozen_and_https(self):
        self.assertEqual(
            annual_url(2015),
            "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni/omni2_2015.dat",
        )

    def test_year_outside_cohort_is_rejected(self):
        with self.assertRaises(ValueError):
            annual_url(2026)


if __name__ == "__main__":
    unittest.main()
