# KinoPulse 0.1.0.dev2026071508 Release Validation

## Release under test

- Package version: `0.1.0.dev2026071508`
- Package source commit: `2d9d434d654c7506d82d4a5a73b3d3836d858c36`
- Wheel SHA256: `CFEFD5130BA3345C5E4AB1BFA1C4288D6BF7EB3CD483AE3A91E5D1FBE435AF81`
- Environment: repository `.venv`
- Validation date: 2026-07-15

The supplied wheel hash was independently recomputed before installation.

## Laboratory regression

All ten experiments were regenerated from the installed wheel. Numerical
results for chaos, control, discovery, diffusion, resonance, constraints, and
space weather remained stable. The repository suite reports `23 passed` and
one intentional expected failure documenting a remaining DAE hook boundary.

## Fix matrix

| Release item | Playground evidence | Outcome |
|---|---|---|
| Genuine one-step TorchScript | Strict script export, save/reload, 32 cases, zero error | Confirmed |
| Export provenance and fallback policy | Requested=`script`, actual=`script`, fallback=`none` | Confirmed |
| Nested output validation | `(next_state, output)` tuple retained and compared | Confirmed |
| Merged bifurcation detections | One neutral event at `mu=0`, not three adjacent candidates | Confirmed |
| Singular/plural DAE hooks | Initializer accepts both; projector still misses plural-only systems | Partial |
| Geometric Zeno detection | Bouncing ball detected at `4.03691 s` with a scale-appropriate window | Confirmed |
| Diffusion stability warnings | Unsafe RK4 step warns with limit and ratio | Confirmed |
| Exact `t_eval` output grids | Requested count/order returned; float64 grid is downcast | Partial |
| Decimal sparse formatting | Native default emits readable decimals; rationalization is opt-in | Confirmed |
| Locked-integrator guidance | No locked-integrator lab in this repository | Not exercised |

## Remaining findings

Two minimal reproducers were written in `kinopulse_gaps/`:

1. `ConstraintProjector` ignores a plural-only `constraints` hook even though
   consistent initialization recognizes it.
2. `solve_ivp` casts `t_eval` to its float32 internal time dtype while retaining
   float64 states. Returned times are not bit-exact, and a rounded decimal
   endpoint can be rejected as outside `t_span`.

Neither finding invalidates the original experiments. The first is isolated to
plural-only projection paths; the pendulum lab retains the singular hook. The
second produces at most `1.91e-8` displacement in the successful focused probe,
but can also raise on a valid `0.2` endpoint. Both matter for a public
compatibility API promising exact requested grids.

## Reproduce

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe export_lab.py
.\.venv\Scripts\python.exe hybrid_lab.py
.\.venv\Scripts\python.exe diffusion_lab.py
```
