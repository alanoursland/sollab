# Can concurrent hybrid trajectories keep independent event histories?

## Question

KinoPulse `0.1.0.dev2026071712` adds isolated serial and concurrent batched
hybrid simulation, padded asynchronous outputs, synchronized-trace checks, and
partial-result errors. Do those orchestration contracts preserve the physical
event accuracy of the existing bouncing-ball experiment? If one sample raises
outside the scalar solver boundary, are its valid neighbors still recoverable?

## Physical batch

Three inelastic balls start at heights `0.5`, `1.0`, and `2.0` with zero
velocity. They share gravity `9.81`, restitution `0.8`, a `0.002` integration
step, and a two-second horizon.

For each initial height `h`, the first impact has the closed form

```text
t = sqrt(2h/g)
```

Every subsequent post-impact velocity should be `0.8` times the preceding
post-impact velocity. These are per-sample physical oracles; the batch API is
not allowed to trade them away for throughput.

## Event accuracy

| Initial height | Impacts | First-impact absolute error | Mean restitution ratio |
|---:|---:|---:|---:|
| 0.5 | 5 | `3.78e-8` s | `0.80000019` |
| 1.0 | 3 | `2.03e-7` s | `0.80000027` |
| 2.0 | 2 | `7.56e-8` s | `0.79999985` |

First-impact errors remain below `2.1e-7` seconds and restitution errors below
`2.8e-7`. The tolerance is deliberately numerical (`1e-6`), not a claim of
symbolic exactness from finite-step integration and event location.

## Serial versus concurrent isolation

The identical three-sample batch is run twice:

- `max_workers=1`; and
- `max_workers=3`.

For every sample, stored times and states are bit-exact, mode traces are equal,
and transition times are equal. The result makes no speed claim: a small
threaded CPU batch may be slower. The validated property is deterministic
isolation and ordering.

The caller-owned `HybridSystem` remains in its initial `flight` mode with no
recorded transitions after the batch. Each sample ran on an isolated runtime
rather than mutating shared guard or mode state.

## Ragged histories

Different impact counts insert different event records into the otherwise
common time grid:

```text
trajectory lengths    [1009, 1006, 1004]
transition counts     [5, 3, 2]
valid-mask counts     [1009, 1006, 1004]
```

The padded batch uses a boolean validity mask and fills every invalid time slot
with `NaN`. The original unpadded `HybridSimulationResult` remains available
through `sample(index)`, so downstream code need not infer events from padding.

## Synchronized mode

Two balls with equal initial height produce one matching transition each and
set `synchronization_verified=True`.

Two balls starting at `0.5` and `1.0` do not have a synchronized discrete
history. KinoPulse raises `BatchSynchronizationError` at sample 1 and retains
the full two-sample result, including transition counts `[2, 1]`. Rejection is
therefore diagnostic rather than destructive.

## Partial worker exception

A second controlled system has three stationary samples. Its guard deliberately
raises only when the state exceeds `0.5`, so only the middle initial state
fails.

The resulting `BatchExecutionError` preserves index alignment:

```text
failed indices      [1]
result statuses     [completed, null, completed]
exception types     [null, RuntimeError, null]
```

All workers are attempted in concurrent mode. This is a stronger contract than
fail-fast execution for ensemble research: one pathological sample cannot erase
valid neighboring evidence, while the exception remains impossible to ignore.

## What survived

1. Scalar physical event accuracy survives batching.
2. Serial and concurrent executions are bit-exact for this deterministic
   system.
3. Caller mode and guard state remain isolated.
4. Ragged event histories have explicit masks and accessible scalar results.
5. Synchronized divergence carries the rejected batch.
6. Escaped sample exceptions retain ordered partial results and exceptions.

No new KinoPulse gap was found. This does not validate thread-scheduled random
streams, GPU scaling, trainable system-owned tensors, or large-batch
performance; the public contract explicitly treats those as separate concerns.

## Reproduction

```powershell
.\.venv\Scripts\python.exe batched_bouncing_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_batched_bouncing_lab -v
```

The ignored evidence is `artifacts/batched_bouncing_analysis.json`; the tracked
figure is `artifacts/batched_bouncing_lab.png`.
