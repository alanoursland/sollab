import tempfile
import unittest
from pathlib import Path

import torch

from export_lab import EXAMPLE_INPUT, EXAMPLE_STATE, export_model


class ExportLabTests(unittest.TestCase):
    def test_saved_script_artifact_matches_lti_one_step(self):
        with tempfile.TemporaryDirectory(dir=".") as directory:
            path = Path(directory) / "controlled_lti.pt"
            model, artifact = export_model(path, validation_cases=8)
            loaded = torch.jit.load(str(path))
            actual_state, actual_output = loaded(EXAMPLE_STATE, EXAMPLE_INPUT)
            expected_state = model.step_tensor(0, EXAMPLE_STATE, EXAMPLE_INPUT)
            expected_output = model.output_tensor(0, EXAMPLE_STATE, EXAMPLE_INPUT)

            self.assertEqual(artifact.artifact_record.requested_mode, "script")
            self.assertEqual(artifact.artifact_record.actual_mode, "script")
            self.assertTrue(artifact.validation.passed)
            torch.testing.assert_close(actual_state, expected_state, rtol=0, atol=0)
            torch.testing.assert_close(actual_output, expected_output, rtol=0, atol=0)


if __name__ == "__main__":
    unittest.main()
