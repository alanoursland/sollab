# Can a learned gate change regimes without chattering?

## Purpose

KinoPulse `0.1.0.dev2026071712` adds structured neural residual corrections and
an explicit-state `GatingPolicy`. These are attractive for future grey-box
models: retain compact physical dynamics, invoke learned corrections only where
needed, and choose among experts without unstable threshold chatter.

This report validates the public wheel with analytical synthetic oracles. It
does not train on ENSO or alter the frozen July 2026 prediction.

## Installed artifact

The wheel installed into the playground `.venv` is:

```text
kinopulse-0.1.0.dev2026071712-py3-none-any.whl
SHA-256 F39CDF1B09CC7068FBA587C565176D7E50D6F9C25EE52A1730CF527D420ED619
```

The locally computed digest matches the published digest. Installation used
`--no-deps` because the environment already contained the required
dependencies and network resolution was unavailable.

## Regime-chatter oracle

Two experts return opposite scalar dynamics, `-1` and `+1`. The true sequence
has three regimes:

1. expert 0;
2. a sustained transition to expert 1; and
3. a sustained transition back to expert 0.

Before each real transition, alternating score margins cross zero but remain
inside a declared `0.25` hysteresis region. This is measurement or classifier
jitter, not a true regime change.

Two policies receive the identical logits:

- **naive hard gate:** exact `argmax`, no memory;
- **stable hard gate:** hysteresis `0.25`, minimum dwell two steps, and
  caller-owned `GatingState` passed between decisions.

## Result

| Policy | Switches | Selection accuracy | Expert-output MSE |
|---|---:|---:|---:|
| Naive hard gate | 14 | 78.6% | 0.8571 |
| Hysteresis + dwell | **2** | **100%** | **0.0000** |

The stable policy ignores every sub-threshold alternation and switches on both
sustained changes. Its dwell counters evolve per sample rather than being
hidden mutable module state, so a caller can reorder, branch, checkpoint, or
subset batches explicitly.

This controlled example does not establish that `0.25` or two steps are good
settings for real data. It establishes that the declared semantics are
implemented and observable.

## Exact forward choice with a training gradient

A separate two-expert oracle uses logits `[0.2, -0.2]` and candidate values
`[2, 5]`.

```text
forward weights       [1, 0]
forward result         2.0
logit gradient         [-0.720782, +0.720782]
gradient norm          1.019340
gradient sum           approximately zero
```

The hard forward pass is exactly one-hot rather than an approximate soft
mixture. The straight-through surrogate nevertheless sends a finite,
oppositely signed gradient to both logits. That is the useful contract for a
model that must make discrete deployment decisions while learning its gate.

## Structured residual algebra

The retained base law is `dx/dt = -2x`, evaluated at `x = 3`, so the base
derivative is `-6`.

### Multiplicative correction

A constant residual of `0.5` should produce

```text
-6 × (1 + 0.5) = -9
```

KinoPulse returns exactly `-9`.

### Gated additive correction

A residual of `4` with gate logit zero has sigmoid gate `0.5`, so it should
produce

```text
-6 + 0.5 × 4 = -4
```

KinoPulse returns gate `0.5` and derivative `-4` exactly.

These neutral and composition contracts matter more than randomly initialized
network output: they show precisely how retained physics and a learned term are
combined.

## Playground compatibility

Before adding this lab, all 176 existing playground tests passed under the new
wheel with two documented expected failures. The underlying gaps are unchanged:

- plural-hook DAE projection runs but stops near `1.0e-7` violation rather
  than the `1.0e-10` oracle; and
- multi-output `RidgeSolver` still fails during objective accounting because
  `torch.dot` receives a matrix residual.

Neither failure is caused by the new gating/residual surface. This lab adds
three passing regression tests and no new KinoPulse gap.

## Appropriate use

This API is promising for models with a strong retained law and localized
misspecification: drag changes, unmodeled forcing, saturation, contact regimes,
or instrument-specific corrections. A gate should not be used to hide poor
base dynamics or to retroactively partition a test set until it looks good.

For the ENSO branch, the correct next action remains scoring the frozen July
prediction. Neural residuals become scientifically legitimate only after new
prospective errors accumulate or on a separately declared dataset.

## Reproduction

```powershell
.\.venv\Scripts\python.exe gating_residual_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_gating_residual_lab -v
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The ignored evidence is `artifacts/gating_residual_analysis.json`; the tracked
figure is `artifacts/gating_residual_lab.png`.
