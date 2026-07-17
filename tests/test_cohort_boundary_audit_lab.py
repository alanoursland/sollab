import unittest

from cohort_boundary_audit_lab import summarize_audits


def audit(records):
    failures = sum(not record["passes_boundary_free_priority"] for record in records)
    return {
        "summary": {
            "selected_targets": len(records),
            "fails_boundary_free_priority": failures,
        },
        "records": records,
    }


class CohortBoundaryAuditLabTests(unittest.TestCase):
    def test_summary_preserves_failure_cohort_and_neighbor(self):
        audits = {
            "development": audit(
                [
                    {"event_id": "ok", "passes_boundary_free_priority": True},
                    {
                        "event_id": "bad",
                        "passes_boundary_free_priority": False,
                        "higher_priority_neighbor": {
                            "event_id": "prior",
                            "inside_original_rectangle": False,
                            "inside_target_catalog_radius": True,
                        },
                    },
                ]
            ),
            "external": audit(
                [{"event_id": "quiet", "passes_boundary_free_priority": True}]
            ),
        }
        result = summarize_audits(audits)
        self.assertEqual(result["selected_targets"], 3)
        self.assertEqual(result["fails_boundary_free_priority"], 1)
        self.assertEqual(result["failures_by_cohort"]["development"], 1)
        self.assertEqual(result["failed_targets"][0]["neighbor_event_id"], "prior")
        self.assertTrue(
            result["failed_targets"][0]["neighbor_inside_target_catalog_radius"]
        )


if __name__ == "__main__":
    unittest.main()
