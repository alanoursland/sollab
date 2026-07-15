# Sequential Poisson Regime Monitor

## What this artifact is

`sequential_poisson_regime_monitor.pt` is a portable TorchScript kernel for
monitoring an existing binned count forecast. As observed bins arrive, it tests
whether some sustained tail has become a persistent multiplicative departure
from the supplied expected counts.

It returns the current likelihood-ratio statistic, estimated change-bin index,
observed/expected tail-rate multiplier, direction, and threshold crossing.

## What it is not

This artifact is **not an earthquake forecast, earthquake early-warning model,
or public-safety alarm**. It contains no trained earthquake parameters, USGS
catalog, location model, magnitude model, hazard calculation, or universal
alarm threshold. It cannot predict whether a damaging earthquake will occur.

The aftershock experiment is one demonstration of the generic count-monitoring
kernel. Researchers must supply their own scientifically valid forecast and a
threshold calibrated under their own full predictive null.

## Files

- `sequential_poisson_regime_monitor.pt` — saved TorchScript module.
- `sequential_poisson_regime_monitor.provenance.json` — hashes, versions,
  validation evidence, and the machine-readable input/output contract.
- `../poisson_regime_monitor.py` — eager Python implementation and Monte Carlo
  calibration helpers.
- `../export_sequential_monitor.py` — reproducible strict-script export.
- `../reports/20_calibrated_sequential_regime_monitor.md` — experiment,
  evidence boundary, and limitations.

## Inputs

All inputs are tensors:

1. `observed`: one-dimensional, non-negative floating count prefix.
2. `expected`: same-length, strictly positive floating expected-count prefix.
3. `threshold`: one finite positive floating value.

The threshold must be calibrated for the complete intended monitoring horizon,
bin definition, scan domain, and predictive null. Copying the playground's
threshold to another model or catalog is invalid.

The exported design requires at least three pre-change and three post-change
bins. Before six bins are present it returns statistic `0`, split index `-1`,
rate multiplier `1`, direction `0`, and no alarm.

## Outputs

The named tuple contains:

- `statistic`: current maximum Poisson tail-rate twice-log-likelihood ratio;
- `split_index`: estimated zero-based change bin;
- `rate_multiplier`: observed tail count divided by expected tail count;
- `direction`: `-1` for lower rate, `0` when not ready/equal, `+1` for higher;
- `alarm`: integer `0/1` indicating whether `statistic > threshold`.

## Python use

```python
import torch

monitor = torch.jit.load("models/sequential_poisson_regime_monitor.pt")

observed = torch.tensor([10., 11., 9., 28., 31., 30., 29., 32.])
expected = torch.full_like(observed, 10.)
threshold = torch.tensor(14.5)  # example only; calibrate for your own null

result = monitor(observed, expected, threshold)
print(result.statistic)
print(result.split_index)
print(result.rate_multiplier)
print(result.direction)
print(result.alarm)
```

For calibration from a fixed Poisson expected-count trajectory:

```python
from poisson_regime_monitor import calibrate_poisson_monitor

calibration = calibrate_poisson_monitor(
    expected_full_horizon,
    false_alarm_rate=0.01,
    sample_count=8192,
    seed=20260717,
)
threshold = torch.tensor(calibration.threshold)
```

This calibration controls repeated scanning only under the supplied fixed
independent-Poisson null. If forecast parameters, catalog completeness, or
event dependence are uncertain, those uncertainties must be included in a
custom null sampler before the resulting alarm has the claimed interpretation.

## Export validation

The artifact is exported through KinoPulse in strict genuine script mode. The
export script validates the saved-and-reloaded file on 32 domain-valid cases
covering float32/float64, horizons from 6 to 24 bins, stable streams, higher-rate
tails, lower-rate tails, and zero-count tails. Exact validation evidence and
SHA-256 digests are recorded in the provenance JSON.

## License and citation

This repository currently contains no license file. Public availability alone
does not grant permission to reuse or redistribute the artifact; the repository
owner should add the intended license before external adoption.

If this artifact contributes to research, cite the repository and state the
forecast/null model used to calibrate it; the artifact alone does not define a
scientifically meaningful alarm.
