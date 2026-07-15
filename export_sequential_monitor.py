"""Export and validate the reusable sequential Poisson regime monitor."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
from pathlib import Path

import torch

from kinopulse.export import (
    ExportFormat,
    TorchModuleExportAdapter,
    create_default_export_manager,
)
from kinopulse.export.adapters import ExportValidationCase

from poisson_regime_monitor import SequentialPoissonRegimeMonitor


class SequentialMonitorExportAdapter(TorchModuleExportAdapter):
    """Supply domain-valid count streams instead of arbitrary random tensors."""

    def validation_cases(self):
        cases = []
        module = self.to_torch_module()
        for dtype in (torch.float32, torch.float64):
            for length in (6, 8, 12, 24):
                expected_counts = torch.linspace(2.0, 8.0, length, dtype=dtype)
                base = torch.round(expected_counts)
                split = 3
                patterns = (
                    (base, 5.0),
                    (
                        torch.cat((base[:split], 2.0 * base[split:])),
                        10.0,
                    ),
                    (
                        torch.cat((base[:split], 0.25 * base[split:])),
                        10.0,
                    ),
                    (
                        torch.cat((base[:split], torch.zeros_like(base[split:]))),
                        15.0,
                    ),
                )
                for observed, threshold_value in patterns:
                    threshold = torch.tensor(threshold_value, dtype=dtype)
                    inputs = (observed, expected_counts, threshold)
                    with torch.no_grad():
                        expected_output = module(*inputs)
                    cases.append(ExportValidationCase(inputs, expected_output))
        return tuple(cases)


def make_adapter() -> SequentialMonitorExportAdapter:
    module = SequentialPoissonRegimeMonitor()
    expected = torch.linspace(2.0, 8.0, 12)
    observed = torch.round(expected)
    threshold = torch.tensor(10.0)
    return SequentialMonitorExportAdapter(
        module=module,
        name="sequential_poisson_regime_monitor",
        inputs=(observed, expected, threshold),
        metadata_overrides={
            "system_type": "statistical_forecast_monitor",
            "state_dim": 0,
            "input_dim": 3,
            "output_dim": 5,
        },
    )


def export_monitor(
    output_path: Path,
    provenance_path: Path | None = None,
    validation_cases: int = 32,
):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    adapter = make_adapter()
    artifact = create_default_export_manager().export(
        adapter,
        ExportFormat.TORCHSCRIPT,
        output_path=output_path,
        validate=True,
        mode="script",
        strict_mode=True,
        validation_cases=validation_cases,
        tolerance=0.0,
        rtol=0.0,
        atol=0.0,
    )
    loaded = torch.jit.load(str(output_path))
    source_path = Path(__file__).with_name("poisson_regime_monitor.py")
    payload = output_path.read_bytes()
    record = artifact.artifact_record
    provenance = {
        "artifact": output_path.name,
        "purpose": "monitor persistent multiplicative departures from a supplied Poisson count forecast",
        "not_a_forecast": True,
        "contains_trained_earthquake_parameters": False,
        "kinopulse_version": importlib.metadata.version("kinopulse"),
        "torch_version": torch.__version__,
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
        "artifact_bytes": len(payload),
        "artifact_sha256": hashlib.sha256(payload).hexdigest(),
        "source": source_path.name,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "min_prechange_bins": 3,
        "min_postchange_bins": 3,
        "input_contract": [
            "observed: one-dimensional non-negative floating count prefix",
            "expected: same-length strictly-positive floating expected-count prefix",
            "threshold: one finite positive floating value calibrated for the complete monitoring procedure",
        ],
        "output_contract": [
            "statistic: current maximum tail-rate twice-log-likelihood ratio",
            "split_index: estimated zero-based change bin, or -1 before readiness",
            "rate_multiplier: observed/expected tail rate",
            "direction: -1 lower, 0 not ready/equal, +1 higher",
            "alarm: integer 0/1 indicating whether statistic exceeds supplied threshold",
        ],
    }
    if provenance_path is not None:
        provenance_path.parent.mkdir(parents=True, exist_ok=True)
        provenance_path.write_text(
            json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
        )
    return adapter.module, loaded, artifact, provenance


def main(output_dir: Path = Path("models")) -> None:
    output_path = output_dir / "sequential_poisson_regime_monitor.pt"
    provenance_path = output_dir / "sequential_poisson_regime_monitor.provenance.json"
    _, _, _, provenance = export_monitor(output_path, provenance_path)
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
