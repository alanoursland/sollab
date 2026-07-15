# Exporting the Monitor, Not an Earthquake Oracle

## Objective

The calibrated sequential regime monitor may be useful to researchers as a
forecast-diagnostic component. This lab packages the reusable part as a
portable, independently loadable TorchScript artifact while preserving its
scientific boundary.

The exported object is deliberately **not** the twelve-earthquake hierarchy.
That population is too small, selective, and observationally heterogeneous to
deserve a universal model label. Instead, the artifact contains only the
generic sequential Poisson tail-rate scan. A researcher supplies their own
forecast expected counts and threshold calibrated under their own predictive
null.

## Deliverable

The committed bundle in `models/` contains:

- `sequential_poisson_regime_monitor.pt`, a `5,983`-byte TorchScript module;
- `sequential_poisson_regime_monitor.provenance.json`, with versions, hashes,
  contracts, and export evidence; and
- `sequential_poisson_regime_monitor.md`, the model card and usage example.

The eager implementation and calibration helpers live in
`poisson_regime_monitor.py`. `export_sequential_monitor.py` reproduces the
binary and provenance record.

## Runtime contract

The module accepts three tensors:

```text
observed  — non-negative one-dimensional count prefix
expected  — same-length, strictly positive expected-count prefix
threshold — one finite positive calibrated value
```

It returns a TorchScript-preserved named tuple:

```text
statistic       current maximum tail-rate twice-log-likelihood ratio
split_index     estimated zero-based change bin, or -1 before readiness
rate_multiplier observed / expected tail rate
direction       -1 lower, 0 not ready/equal, +1 higher
alarm           integer 0/1 threshold crossing
```

The design requires at least three pre-change and three post-change bins. It is
stateless: callers pass the complete currently observed prefix at every update.
This makes replay, audit, and recovery from a restarted process deterministic.

## Strict KinoPulse export evidence

The artifact is exported through `TorchModuleExportAdapter` and the KinoPulse
default export manager with:

```text
requested mode       script
actual mode          script
fallback             none
saved/reloaded check true
validation cases     32
maximum error        0.0
```

Validation covers float32 and float64, horizons of 6, 8, 12, and 24 bins,
stable forecasts, persistent higher-rate tails, lower-rate tails, and
zero-count tails. KinoPulse validates the saved-and-reloaded file rather than
only the in-memory module.

The exported artifact SHA-256 is:

```text
E02315D4CCAFB9AE8F8CC40E0EBC842A66BD4A76EF8D8D88DD600560F84C82BE
```

The provenance JSON also records the source SHA-256, KinoPulse
`0.1.0.dev2026071508`, and PyTorch `2.3.0`.

## Export finding

The original named output used a Boolean tensor for `alarm`. Genuine strict
script compilation and saving succeeded, but KinoPulse's validator attempted
to subtract the expected and actual Boolean leaves. PyTorch does not support
Boolean subtraction. The portable artifact therefore uses integer `0/1`, which
also has a simpler cross-runtime representation.

The underlying validator limitation is documented in
`kinopulse_gaps/export_validation_boolean_tensor_outputs.md`. The workaround is
part of the public contract rather than an unreported implementation detail.

Strict export also exposed a global compatibility side effect: importing
KinoPulse replaces `torch.any` and `torch.all` with Python `*args, **kwargs`
wrappers, which makes downstream modules using those reductions unscriptable.
The monitor avoids the patched functions, and
`kinopulse_gaps/global_torch_reduction_patch_breaks_torchscript.md` records the
reproduction and acceptance contract.

## Research use

A seismologist could place this kernel beside an existing Reasenberg–Jones,
ETAS, or other count forecast:

1. Produce expected counts for a fixed sequence of future bins.
2. Simulate from the *complete* predictive model, including relevant parameter
   and catalog uncertainty.
3. Calibrate the maximum-over-time scan threshold.
4. Feed observed and expected prefixes to the artifact as bins arrive.
5. Treat an alarm as a model-diagnostic event for expert review, not as a
   damaging-earthquake prediction.

`calibrate_poisson_monitor()` provides the fixed independent-Poisson reference
used in report 20. Researchers with richer forecasts should replace that null
sampler; reusing the playground threshold would be invalid.

## Safety boundary

The artifact contains no trained earthquake parameters, spatial model,
magnitude distribution, catalog, hazard calculation, or operational threshold.
It cannot estimate the probability of an M5+, M6+, or M7+ earthquake and must
not drive public alerts or protective action without a separate validated
forecasting and governance system.

## Licensing boundary

The repository currently has no license file. Public visibility alone does not
grant permission to reuse or redistribute the artifact. The repository owner
needs to select an intended license before inviting outside adoption.

## Reproduce

```powershell
.\.venv\Scripts\python.exe export_sequential_monitor.py
.\.venv\Scripts\python.exe -m pytest tests\test_export_sequential_monitor.py -q
```
