import unittest

from magnitude_provenance_stratification_lab import (
    build_stratum_summaries,
    provenance_composition,
    stratum_key,
)


class MagnitudeProvenanceStratificationLabTests(unittest.TestCase):
    def setUp(self):
        self.event = {
            "event_id": "target",
            "name": "target",
            "time_days": 0.5,
            "magnitude": 3.2,
            "network": "ak",
            "magnitude_type": "ml",
        }

    def test_stratum_keys_are_explicit_and_nested(self):
        self.assertEqual(stratum_key(self.event, "sequence"), ("target",))
        self.assertEqual(
            stratum_key(self.event, "sequence_network"), ("target", "ak")
        )
        self.assertEqual(
            stratum_key(self.event, "sequence_magnitude_type"), ("target", "ml")
        )
        self.assertEqual(
            stratum_key(self.event, "sequence_network_magnitude_type"),
            ("target", "ak", "ml"),
        )

    def test_network_stratification_preserves_parent_identity(self):
        events = [
            {**self.event, "time_days": 0.5, "magnitude": 3.2, "network": "ak"},
            {**self.event, "time_days": 2.0, "magnitude": 2.8, "network": "ak"},
            {**self.event, "time_days": 0.6, "magnitude": 2.7, "network": "us"},
            {**self.event, "time_days": 3.0, "magnitude": 3.1, "network": "us"},
        ]
        summaries = build_stratum_summaries(events, 3.0, "sequence_network")
        self.assertEqual(len(summaries), 2)
        self.assertEqual({item["parent_event_id"] for item in summaries}, {"target"})
        self.assertEqual({item["network"] for item in summaries}, {"ak", "us"})

    def test_composition_total_variation_detects_complete_shift(self):
        events = [
            {**self.event, "time_days": 0.5, "network": "early"},
            {**self.event, "time_days": 2.0, "network": "late"},
        ]
        composition = provenance_composition(events, "network")
        self.assertAlmostEqual(composition["total_variation_distance"], 1.0)
        self.assertEqual(composition["early_total"], 1)
        self.assertEqual(composition["late_total"], 1)

    def test_unknown_scheme_is_rejected(self):
        with self.assertRaises(ValueError):
            stratum_key(self.event, "unknown")


if __name__ == "__main__":
    unittest.main()
