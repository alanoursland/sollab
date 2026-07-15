# Validated TorchScript Export of a Controlled LTI Model

## Objective

Determine whether a discrete controlled state-space model can leave the Python
runtime as a genuine scripted one-step artifact while preserving its numerical
semantics and recording what export mode actually occurred.

The model has two states, one input, and one output:

```text
x[k+1] = A x[k] + B u[k]
y[k]   = C x[k] + D u[k]
```

with a stable triangular `A`, nonzero `B`, and direct feedthrough `D=0.05`.

## Method

`export_lab.py` constructs `DiscreteLTISystem`, wraps it with
`DiscreteStateSpaceExportAdapter`, and asks the default export manager for
TorchScript in strict `script` mode. Mode fallback is therefore forbidden.
The artifact is saved to `artifacts/controlled_lti_one_step.pt`, loaded again
with `torch.jit.load`, and validated on 32 deterministic cases. The loaded
module returns the nested semantic output `(next_state, output)`.

## Results

- Requested mode: `script`
- Actual mode: `script`
- Fallback status: `none`
- Saved-artifact validation: passed, 32 cases
- Maximum validation error: `0.0`
- Reloaded example errors: `[0.0, 0.0]`
- Example next state: `[0.414, -0.080]`
- Example output: `[0.495]`
- Serialized size: approximately `6 KB`

This is a genuine script export, not a traced fallback. The tuple result also
exercises structure-preserving validation rather than flattening the two output
meanings into one tensor.

## Interpretation and limitations

The result validates one controlled affine LTI graph on CPU with float32
tensors. It does not establish portability across devices, dtype conversion,
mobile runtimes, version-skewed TorchScript loaders, or arbitrary neural
transition modules. Those are separate deployment questions.

The most valuable design feature is provenance: downstream tooling can reject
an unexpected traced fallback rather than treating every `.pt` file as
semantically equivalent.

## Reproduce

```powershell
.\.venv\Scripts\python.exe export_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_export_lab -v
```
