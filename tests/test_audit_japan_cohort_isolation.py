import unittest

from audit_japan_cohort_isolation import stronger_neighbor
from fetch_aftershock_population import Candidate


def candidate(event_id, time, magnitude, latitude=30.1, longitude=140.0):
    return Candidate(event_id, time, latitude, longitude, 10.0, magnitude, event_id)


class JapanCohortIsolationAuditTests(unittest.TestCase):
    def test_equal_magnitude_earlier_neighbor_has_priority(self):
        target = candidate("target", "2023-10-06T00:00:00.000Z", 6.1)
        earlier = candidate("earlier", "2023-10-05T00:00:00.000Z", 6.1, 29.9)
        self.assertEqual(stronger_neighbor(target, [target, earlier]), earlier)

    def test_later_equal_magnitude_does_not_displace_target(self):
        target = candidate("target", "2023-10-06T00:00:00.000Z", 6.1)
        later = candidate("later", "2023-10-07T00:00:00.000Z", 6.1)
        self.assertIsNone(stronger_neighbor(target, [target, later]))

    def test_later_larger_event_has_priority(self):
        target = candidate("target", "2023-10-06T00:00:00.000Z", 6.1)
        later = candidate("later", "2023-10-07T00:00:00.000Z", 6.2)
        self.assertEqual(stronger_neighbor(target, [target, later]), later)


if __name__ == "__main__":
    unittest.main()
