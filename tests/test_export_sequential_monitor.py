import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import torch

from export_sequential_monitor import export_monitor
from poisson_regime_monitor import SequentialPoissonRegimeMonitor, tail_scale_scan


class SequentialMonitorExportTests(unittest.TestCase):
    def test_eager_module_matches_batched_reference_at_current_prefix(self):
        observed = torch.tensor([5.0, 5.0, 5.0, 15.0, 15.0, 15.0, 15.0, 15.0])
        expected = torch.full_like(observed, 5.0)
        module = SequentialPoissonRegimeMonitor()
        output = module(observed, expected, torch.tensor(10.0))
        statistics, splits = tail_scale_scan(observed, expected)
        torch.testing.assert_close(output.statistic, statistics[-1])
        self.assertEqual(int(output.split_index), int(splits[-1]))
        self.assertEqual(int(output.direction), 1)
        self.assertTrue(bool(output.alarm))

    def test_strict_script_export_reloads_with_named_output(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            output_path = Path(directory) / "monitor.pt"
            eager, loaded, artifact, provenance = export_monitor(
                output_path, validation_cases=8
            )
            observed = torch.tensor([4.0, 4.0, 4.0, 1.0, 1.0, 1.0, 1.0])
            expected = torch.full_like(observed, 4.0)
            threshold = torch.tensor(5.0)
            reference = eager(observed, expected, threshold)
            actual = loaded(observed, expected, threshold)
            for reference_value, actual_value in zip(reference, actual):
                torch.testing.assert_close(actual_value, reference_value, rtol=0, atol=0)
            self.assertEqual(artifact.artifact_record.requested_mode, "script")
            self.assertEqual(artifact.artifact_record.actual_mode, "script")
            self.assertTrue(artifact.validation.passed)
            self.assertEqual(provenance["fallback_status"], "none")

    def test_committed_artifact_matches_provenance_digest(self):
        artifact_path = Path("models/sequential_poisson_regime_monitor.pt")
        provenance_path = Path(
            "models/sequential_poisson_regime_monitor.provenance.json"
        )
        self.assertTrue(artifact_path.exists())
        self.assertTrue(provenance_path.exists())
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
        digest = hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        self.assertEqual(digest, provenance["artifact_sha256"])
        loaded = torch.jit.load(str(artifact_path))
        output = loaded(
            torch.tensor([3.0, 3.0, 3.0, 9.0, 9.0, 9.0]),
            torch.full((6,), 3.0),
            torch.tensor(5.0),
        )
        self.assertEqual(int(output.split_index), 3)


if __name__ == "__main__":
    unittest.main()
