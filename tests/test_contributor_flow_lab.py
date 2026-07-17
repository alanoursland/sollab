import unittest
from datetime import datetime, timedelta, timezone

from contributor_flow_lab import classify_contributor_flow, fit_flow_models, newcomer_cohorts
from open_source_commit_ecology_lab import Commit


class ContributorFlowLabTests(unittest.TestCase):
    def test_new_continuing_and_returning_categories_are_exclusive(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        commits = [
            Commit("repo", "1", start, "a", False),
            Commit("repo", "2", start + timedelta(weeks=1), "a", False),
            Commit("repo", "3", start + timedelta(weeks=15), "a", False),
            Commit("repo", "4", start + timedelta(weeks=15), "b", False),
        ]
        flows = classify_contributor_flow(commits, start + timedelta(weeks=15), dormancy_weeks=13)
        self.assertEqual((flows[0].new, flows[0].continuing, flows[0].returning), (1, 0, 0))
        self.assertEqual((flows[1].new, flows[1].continuing, flows[1].returning), (0, 1, 0))
        self.assertEqual((flows[15].new, flows[15].continuing, flows[15].returning), (1, 0, 1))
        self.assertEqual(flows[15].active, 2)

    def test_newcomer_return_rate_uses_only_eligible_cohorts(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        commits = [
            Commit("repo", "1", start, "returns", False),
            Commit("repo", "2", start + timedelta(weeks=10), "returns", False),
            Commit("repo", "3", start, "one-shot", False),
            Commit("repo", "4", start + timedelta(weeks=60), "too-new", False),
        ]
        cohorts = newcomer_cohorts(commits, start + timedelta(weeks=65))
        cohort_2024 = next(cohort for cohort in cohorts if cohort["cohort_year"] == 2024)
        self.assertEqual(cohort_2024["eligible_for_52w_return"], 2)
        self.assertEqual(cohort_2024["return_rate_52w"], 0.5)

    def test_flow_model_returns_chronological_holdout_scores(self):
        start = datetime(2024, 1, 1, tzinfo=timezone.utc)
        commits = []
        for index in range(40):
            commits.append(Commit("repo", str(index), start + timedelta(weeks=index), "steady", False))
            if index % 5 == 0:
                commits.append(Commit("repo", f"new-{index}", start + timedelta(weeks=index), f"n{index}", False))
        flows = classify_contributor_flow(commits, start + timedelta(weeks=39))
        result = fit_flow_models(flows)
        self.assertGreater(result["split"], 1)
        self.assertGreaterEqual(result["baseline_holdout_rmse"], 0.0)
        self.assertGreaterEqual(result["expanded_holdout_rmse"], 0.0)


if __name__ == "__main__":
    unittest.main()
