# Does stochastic neural uncertainty obey its declared moments?

## Question

KinoPulse `0.1.0.dev2026071712` separates learned stochastic diffusion from
ensemble disagreement. Do the public APIs reproduce analytical drift,
covariance, supplied-noise, and population-variance oracles? Can the two
uncertainty channels be composed without losing information?

This is a synthetic release-validation lab. It supplies all randomness from
the application boundary and does not touch the frozen ENSO forecast.

## Stochastic field oracle

The two-dimensional constant field is

```text
drift = [1.0, -2.0]

            [0.5, 0.0]
diffusion = [0.1, 0.3]
```

Therefore the declared aleatoric covariance must be

```text
BBᵀ = [0.25, 0.05]
      [0.05, 0.10]
```

KinoPulse returns the exact matrix and zero epistemic variance. Given supplied
noise `[2, -1]`, `apply_noise` returns `[1.0, -0.1]`, exactly matching matrix
multiplication. The field never samples internally, so seeds and replay remain
owned by the solver or application.

## Seeded one-step distribution

For step size `0.04`, 100,000 application-supplied standard-normal samples
produce Euler increments

```text
Δx = drift × dt + diffusion × noise × sqrt(dt)
```

| Diagnostic | Error from analytical value |
|---|---:|
| Mean L2 error | `1.14e-4` |
| Covariance Frobenius error | `2.83e-5` |

The empirical covariance matches all four entries of `dt × BBᵀ`. This is not a
test of Gaussian convergence in general; it verifies batching, orientation,
dtype, and the supplied-noise contract at realistic scale.

## Epistemic ensemble oracle

Three deterministic member drifts are:

```text
[1, 2], [3, 0], [2, 4]
```

KinoPulse returns their exact mean `[2, 2]` and population componentwise
variance `[2/3, 8/3]`. The member tensor is retained, allowing downstream users
to audit or compute richer covariance rather than receiving only a summary.

## Composition gap

The primitives are correct individually, but an ensemble of stochastic neural
members exposes an unsafe seam. `EnsembleNeuralVectorField` accepts those
members, evaluates only their drift, and returns zero aleatoric covariance even
when every member has nonzero diffusion.

For two constant stochastic members, the law-of-total-variance decomposition
should be:

```text
mean                   [2, 1]
epistemic variance     [1, 1]
mean aleatoric cov.    diag(0.625, 2.125)
```

The first two values are returned; the third becomes zero. This is documented
in
`kinopulse_gaps/stochastic_ensemble_drops_aleatoric_covariance.md` with a
preserved expected-failure regression. Either propagating the mean member
covariance or rejecting stochastic ensemble members would be safer than a
lossy accepted composition.

## What survived

1. Learned drift and diffusion have precise, independently inspectable
   contracts.
2. `apply_noise` keeps randomness outside the model and is reproducible.
3. Aleatoric covariance equals `BBᵀ` exactly.
4. Deterministic ensemble disagreement uses the population variance expected
   for equally weighted members.
5. Combined stochastic ensembles require an explicit workaround until the
   composition gap is addressed.

## Why this matters for later real models

A physical model with a neural correction can be uncertain for two different
reasons: observations may have irreducible variability, and plausible learned
models may disagree. Treating those as separate objects supports better
diagnosis than one undifferentiated error bar. It also prevents more ensemble
members from being mistaken for less physical noise.

No real-data model should use these fields until its diffusion scale and
ensemble diversity are calibrated on chronology-respecting held-out groups.

## Reproduction

```powershell
.\.venv\Scripts\python.exe stochastic_uncertainty_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_stochastic_uncertainty_lab -v
.\.venv\Scripts\python.exe -m unittest tests.test_kinopulse_stochastic_ensemble_gap -v
```

The ignored evidence is `artifacts/stochastic_uncertainty_analysis.json`; the
tracked figure is `artifacts/stochastic_uncertainty_lab.png`.
