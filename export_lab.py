"""Export and reload a controlled discrete LTI model with TorchScript."""

from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path

import torch

from kinopulse.export import (
    DiscreteStateSpaceExportAdapter,
    ExportFormat,
    create_default_export_manager,
)
from kinopulse.identification.state_space import DiscreteLTISystem


DTYPE = torch.float32
EXAMPLE_STATE = torch.tensor([0.4, -0.3], dtype=DTYPE)
EXAMPLE_INPUT = torch.tensor([0.7], dtype=DTYPE)


def make_model() -> DiscreteLTISystem:
    return DiscreteLTISystem(
        A=torch.tensor([[0.92, 0.08], [0.0, 0.85]], dtype=DTYPE),
        B=torch.tensor([[0.10], [0.25]], dtype=DTYPE),
        C=torch.tensor([[1.0, -0.2]], dtype=DTYPE),
        D=torch.tensor([[0.05]], dtype=DTYPE),
        name="controlled_lti_export_lab",
    )


def export_model(output_path: Path, validation_cases: int = 32):
    model = make_model()
    adapter = DiscreteStateSpaceExportAdapter(
        model,
        name="controlled_lti_export_lab",
        example_state=EXAMPLE_STATE,
        example_input=EXAMPLE_INPUT,
    )
    artifact = create_default_export_manager().export(
        adapter,
        ExportFormat.TORCHSCRIPT,
        output_path=output_path,
        validate=True,
        mode="script",
        strict_mode=True,
        validation_cases=validation_cases,
        validation_seed=20260715,
    )
    return model, artifact


def main(output_dir: Path = Path("artifacts")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "controlled_lti_one_step.pt"
    model, artifact = export_model(output_path)
    loaded = torch.jit.load(str(output_path))

    expected = (
        model.step_tensor(0, EXAMPLE_STATE, EXAMPLE_INPUT),
        model.output_tensor(0, EXAMPLE_STATE, EXAMPLE_INPUT),
    )
    actual = loaded(EXAMPLE_STATE, EXAMPLE_INPUT)
    errors = [
        float((observed - reference).abs().max())
        for observed, reference in zip(actual, expected)
    ]
    record = artifact.artifact_record
    report = {
        "experiment": "controlled discrete LTI one-step TorchScript export",
        "kinopulse_version": importlib.metadata.version("kinopulse"),
        "requested_mode": record.requested_mode,
        "actual_mode": record.actual_mode,
        "fallback_status": record.fallback_status.value,
        "fallback_reason": record.fallback_reason,
        "validated_saved_artifact": record.validation.witnesses.get(
            "saved_and_reloaded"
        ),
        "validation_passed": artifact.validation.passed,
        "validation_cases": artifact.validation.test_cases,
        "validation_max_error": artifact.validation.max_error,
        "loaded_example_max_errors": errors,
        "artifact_bytes": output_path.stat().st_size,
        "expected_next_state": expected[0].tolist(),
        "expected_output": expected[1].tolist(),
    }
    (output_dir / "export_analysis.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
