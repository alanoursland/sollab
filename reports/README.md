# KinoPulse Playground Reports

These reports document the experiments in this repository as reproducible
scientific software studies. They describe the question, model, KinoPulse
capabilities exercised, numerical procedure, evidence, limitations, and
release-under-test observations for each lab.

All reported values come from the JSON evidence generated locally in
`artifacts/`. The JSON and downloaded source data are intentionally ignored;
figures are committed for convenient review. Results were last reproduced on
2026-07-15 using KinoPulse `0.1.0.dev2026071508` in the repository's `.venv`.

## Experiment index

| Report | Question | Main result |
|---|---|---|
| [Lorenz chaos](01_lorenz_chaos.md) | Can KinoPulse detect chaos and sensitive dependence? | Positive largest Lyapunov exponent (`1.088`) and diverging nearby trajectories. |
| [Pitchfork bifurcation](02_pitchfork_bifurcation.md) | Can equilibrium continuation expose symmetry breaking? | Central-branch eigenvalue crosses zero at the analytical bifurcation. |
| [LQR control](03_lqr_control.md) | Can an unstable equilibrium be stabilized and verified? | Stable poles at `-3.164` and `-3.689`; CARE residual `4.08e-14`. |
| [Equation discovery](04_lorenz_equation_discovery.md) | Can the Lorenz law be recovered from trajectories alone? | Exact seven-term structure recovered; unseen rollout RMSE `0.138`. |
| [Hybrid impacts](05_hybrid_bouncing_ball.md) | Can impacts and geometric event accumulation be simulated? | Impact laws match theory and geometric Zeno accumulation is detected. |
| [Heat diffusion](06_heat_diffusion.md) | Does the PDE solver converge at its expected order? | Observed spatial order `1.99`; variance decreases monotonically. |
| [Parametric resonance](07_mathieu_resonance.md) | Can Floquet analysis reveal Mathieu instability tongues? | Principal resonance correctly separates bounded and growing responses. |
| [Constrained pendulum](08_constrained_pendulum.md) | Can projection control holonomic drift? | Circle error held below `4.5e-7` versus `0.299` without projection. |
| [Geomagnetic storm](09_geomagnetic_storm.md) | Can a compact forced model reproduce a real storm? | Held-out rollout RMSE `21.47 nT` versus `45.51 nT` constant baseline. |
| [TorchScript export](10_torchscript_export.md) | Can a controlled one-step model become a validated standalone artifact? | Genuine script mode, 32 saved-artifact checks, and zero numerical error. |
| [Release validation](11_release_validation_2026071508.md) | Did the new release close the laboratory findings? | Seven fix areas confirmed; two narrower boundary gaps remain. |
| [Aftershock relaxation](12_ridgecrest_aftershocks.md) | Does seismic activity remember a large shock through a power law? | A seven-day Omori fit predicts the next 23 days; exponential relaxation collapses too quickly. |
| [Aftershock excitation](13_aftershock_excitation.md) | Do observed events improve the next conditional interval? | A magnitude-weighted kernel lowers holdout deviance by only `2.12%` and does not win most intervals. |

## Reproduction

Run all tests:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Regenerate a specific experiment by running its corresponding `*_lab.py` file.
The geomagnetic-storm report additionally requires:

```powershell
.\.venv\Scripts\python.exe fetch_omni.py
.\.venv\Scripts\python.exe space_weather_lab.py
```

The Ridgecrest report additionally requires:

```powershell
.\.venv\Scripts\python.exe fetch_ridgecrest.py
.\.venv\Scripts\python.exe aftershock_lab.py
.\.venv\Scripts\python.exe aftershock_excitation_lab.py
```

These are exploratory numerical experiments, not claims that every computed
quantity is a formal certificate. Each report states its own evidence boundary.
