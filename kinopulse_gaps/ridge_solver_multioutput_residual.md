# Gap: `RidgeSolver` crashes after solving a multi-output target

## Discovered in

The ENSO recharge-state experiment, while fitting the coupled next state
`[MEI.v2, upper-ocean heat content]` from one shared design matrix with
KinoPulse `0.1.0.dev2026071623`.

## Observed behavior

`RidgeSolver.solve(A, b)` accepts a two-dimensional target, forms the correct
matrix right-hand side, and obtains a matrix solution. It then crashes while
computing its scalar objective because `torch.dot` requires one-dimensional
arguments:

```python
import torch
from kinopulse.solvers.opt.least_squares import RidgeSolver

A = torch.tensor([[1.0, 0.0], [1.0, 1.0], [1.0, 2.0]], dtype=torch.float64)
b = torch.tensor([[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]], dtype=torch.float64)

RidgeSolver(lambda_=0.1).solve(A, b)
```

The failure is:

```text
RuntimeError: 1D tensors expected, but got 2D and 2D tensors
```

It occurs at the equivalent of:

```python
residual_vec = A @ x - b
objective = 0.5 * torch.dot(residual_vec, residual_vec).item()
```

## Why it matters

Multi-output linear regression is the natural fit primitive for vector-state
dynamics, coupled oscillators, state-space identification, and shared-feature
system models. The normal equations already support this target shape; only
result accounting prevents the solve from completing.

## Suggested contract

Either:

1. explicitly reject `b.ndim != 1` before solving and document the solver as
   single-output; or, preferably,
2. support `b` shaped `[samples, outputs]`, return `x` shaped
   `[features, outputs]`, and compute residual/objective over every element.

The second option could replace the vector-only operation with:

```python
objective = 0.5 * torch.sum(residual_vec.square()).item()
```

Any convergence diagnostics should use the corresponding Frobenius norm.

## Regression oracle

For both vector and matrix targets, compare `result.x` to the direct solution:

```python
expected = torch.linalg.solve(
    A.T @ A + lambda_ * torch.eye(A.shape[1], dtype=A.dtype),
    A.T @ b,
)
```

Also verify that the reported residual is `torch.linalg.norm(A @ x - b)` and
the objective is half the summed squared residual. A one-column matrix target
should preserve its two-dimensional output shape rather than silently squeeze.

## Playground workaround

The experiment performs one public `RidgeSolver.solve` call per output and
stacks the coefficient vectors. This is algebraically equivalent because every
output shares the same design and ridge penalty, but it duplicates factorization
work and does not provide one native coupled fit result.
