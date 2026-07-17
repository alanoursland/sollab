# Gap: stochastic ensembles silently drop member diffusion uncertainty

## Discovered in

The stochastic neural vector-field uncertainty lab using KinoPulse
`0.1.0.dev2026071712`.

## Observed behavior

`EnsembleNeuralVectorField` accepts `NeuralStochasticVectorField` members because
they are valid `NeuralSystem` instances with matching state and input
contracts. Its `predict_distribution` implementation evaluates each member's
forward drift, computes epistemic variance across those drifts, and always
returns zero aleatoric covariance.

Consequently, stochastic member diffusion is silently discarded:

```python
first = NeuralStochasticVectorField(2, 2, dtype=torch.float64)
second = NeuralStochasticVectorField(2, 2, dtype=torch.float64)
# assign distinct drift_net and diffusion_net modules

result = EnsembleNeuralVectorField([first, second]).predict_distribution(
    torch.tensor(0.0), torch.zeros(2, dtype=torch.float64)
)

result.epistemic_variance      # drift disagreement is present
result.aleatoric_covariance    # exactly zero
```

The individual members' `predict_distribution` results correctly contain
`diffusion @ diffusion.T`; only the ensemble composition loses that term.

## Why it matters

An ensemble of stochastic learned dynamics is the natural case where both
uncertainty channels coexist:

- member drift disagreement represents epistemic uncertainty; and
- each member's diffusion represents aleatoric uncertainty.

Silently returning zero diffusion covariance makes the structured result look
complete while understating total predictive uncertainty. A caller can combine
the terms manually, but must first realize that the accepted composition has
discarded information.

## Suggested contract

Preferably, when every member exposes a compatible `predict_distribution`, the
ensemble should return:

```text
mean                 = mean(member means)
epistemic variance   = population variance(member means)
aleatoric covariance = mean(member aleatoric covariances)
```

This is the law-of-total-variance decomposition for an equally weighted mixture
when the two components are reported separately. Full epistemic covariance
rather than componentwise variance could be a future extension.

If stochastic composition is intentionally unsupported, construction should
instead reject members with nonzero diffusion or document and flag the lossy
conversion. Accepting them and returning zero aleatoric covariance is the
unsafe boundary.

## Regression oracle

Use two constant stochastic members:

```text
drifts       [1, 2], [3, 0]
diffusions   diag(1, 2), diag(0.5, 0.5)
```

The ensemble distribution should have:

```text
mean                   [2, 1]
epistemic variance     [1, 1]
aleatoric covariance   diag(0.625, 2.125)
```

The preserved expected-failure test is
`tests/test_kinopulse_stochastic_ensemble_gap.py`.

## Playground workaround

Call `predict_distribution` on every stochastic member directly. Average the
member means and aleatoric covariance matrices, and compute population variance
across member means. Do not use the ensemble's zero aleatoric covariance as a
total-uncertainty estimate.
