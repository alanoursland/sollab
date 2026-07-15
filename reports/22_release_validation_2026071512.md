# KinoPulse 0.1.0.dev2026071512 release validation

## Question

Does the `2026071512` release provide trustworthy count-data and fitting
contracts for the aftershock playground, and is its new temporal point-process
abstraction correct beyond the homogeneous reference case?

## Artifact under test

- package: `kinopulse==0.1.0.dev2026071512`;
- source commit reported by the publisher:
  `4dd199a10a774e074f60b1ad70cdee5f59288aa3`;
- wheel SHA-256 independently rechecked in this workspace:
  `F15A39EB7CAEAAF9AEEBD6F32A31504FD3DF46682DCC0CC38050A49D3330E682`;
- environment: this repository's `.venv` on CPU with `torch.float64` analytical
  probes.

The wheel was force-installed without dependency replacement so the existing
playground environment remained intact. The lab records the installed version
through standard package metadata.

## Method

`kinopulse_release_lab.py` uses small problems with closed-form answers rather
than only checking that calls do not raise:

1. Poisson log likelihood, deviance, signed deviance residuals, and Anscombe
   residuals are evaluated with zero and positive observations. The likelihood
   is compared term-by-term with the distribution formula, the residual square
   identity is checked, and gradients must remain finite.
2. Analytical compensator differencing and numerical rate integration are
   compared for a linear rate, where the trapezoidal rule is exact. The
   parameter derivative is also checked.
3. A homogeneous temporal point process is compared with
   `n log(rate) - rate * horizon`; expected bin counts, batched likelihood, and
   seeded simulation replay are exercised.
4. An exponential Hawkes process is compared with its analytical event term
   and compensator. This is the causal, history-dependent stress test.
5. A named weighted residual stack fits a two-parameter line. The rich LM
   result, rank, condition number, covariance, and block contribution ledger
   are checked.
6. Explicit multistart fitting receives two valid starts and one deliberately
   invalid basin. The failure must remain visible and an exact valid solution
   must win deterministically.
7. A rank-one Jacobian exercises the explicit pseudoinverse covariance policy.

The existing Ridgecrest lab was then migrated from local Poisson/Anscombe math
and a hand-written multistart loop to these release APIs. Its public helper
contracts remain unchanged for downstream experiments.

## Results

| Contract | Result |
|---|---:|
| Poisson log-likelihood error | `0.0` |
| Deviance versus squared signed residuals | `2.22e-16` |
| Zero-count deviance limit | exact (`0.4`) |
| Count-objective gradient | finite |
| Analytical versus numerical bin counts | `0.0` maximum error |
| Expected-count parameter gradient | exact (`2.0`) |
| Homogeneous point-process likelihood | `0.0` error |
| Homogeneous expected bin counts | `0.0` maximum error |
| Batch versus scalar likelihood | exact |
| Seeded homogeneous simulation | bit-reproducible |
| Weighted line-fit parameters | `[1.5, -0.25]` to floating precision |
| Fit Jacobian rank | `2 / 2` |
| Residual contribution sum versus objective | exact to test tolerance |
| Multistart invalid candidate | recorded at supplied index `0` |
| Multistart best solution | `[2.0, -1.0]` |
| Singular covariance | rank `1`, finite, pseudoinverse provenance visible |

The complete repository suite passes: `64` tests run, with `2` intentional
expected failures. One expected failure predates this experiment; the new one
is the point-process boundary regression below.

The full Ridgecrest lab also reran successfully through the migrated APIs. Its
published scientific result is numerically preserved: Omori `K=315.86`,
`c=0.02678 days`, `p=1.1130`, training deviance `69.94`, and holdout deviance
`28.34` versus `2821.80` for the exponential baseline.

## One causal point-process gap

The homogeneous subset is sound, but the current history-dependent
compensator is not. With `mu=0.7`, `alpha=1.2`, `beta=0.8`, events
`[0.4, 1.1, 1.7]`, and horizon `2.4`:

| Quantity | KinoPulse | Analytical | Absolute error |
|---|---:|---:|---:|
| Event contribution | agrees | agrees | `0.0` |
| Total log likelihood | `-2.0384467` | `-3.8966444` | `1.8581977` |
| Compensator | differs | oracle | `1.8581977` |

The localization is unusually clean: event intensities are causal and exact;
only the integrated term is wrong. `log_likelihood` splits at event times, then
`expected_counts` retains only history strictly less than the interval's left
edge. The event at that edge is therefore omitted over the whole following
interval. The minimal reproduction, design ambiguity, and acceptance checks
are recorded in
`kinopulse_gaps/temporal_point_process_left_boundary_history.md`.

This means the release's `TemporalPointProcess` is validated here for
homogeneous processes only. Its likelihood should not yet be used for Hawkes or
other event-history models without an external compensator check.

## What changed in the playground

The aftershock lab now delegates conventional Poisson deviance and Anscombe
residual evaluation to KinoPulse. The wrapper negates the library Anscombe
residual only to retain the playground's historical `expected - observed`
orientation; least-squares objectives are invariant to that sign.

It also uses `multistart_least_squares` directly. This removes library-shaped
control flow from the lab and preserves failed-start evidence for future
diagnosis. Synthetic Omori recovery, exponential comparison, transfer,
hierarchy, and change-detector tests all remain green after the migration.

## Evidence boundary

These are deterministic analytical and regression probes, not a general proof
of optimizer convergence, covariance coverage, or point-process correctness.
The covariance result is a local linearized frequentist approximation, as the
KinoPulse result itself states. Homogeneous simulation was checked for seeded
replay and contract consistency, not distributional calibration at scale.

## Conclusion

This release materially improves the playground: the new count objectives,
integration tools, fit result, multistart provenance, residual accounting, and
covariance policy all survived direct analytical tests and are now used by the
real aftershock workflow. The temporal point-process interface has a strong
minimal shape, but its left-boundary history rule currently makes the
history-dependent likelihood numerically incorrect. Fixing that one causal
boundary would make it a compelling foundation for the next unbinned
aftershock experiment.
