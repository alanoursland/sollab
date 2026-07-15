# KinoPulse Playground

See [DREAMS.md](DREAMS.md) for the long-term vision behind this dynamics
laboratory, and [RESEARCH_QUESTIONS.md](RESEARCH_QUESTIONS.md) for a prioritized
portfolio built around public real-world datasets.

Detailed methods, results, limitations, and reproduction instructions are in
the [experiment reports](reports/README.md).

This repository is an experimental field guide to nonlinear dynamics built with
KinoPulse. The exhibits explore Lorenz chaos, pitchfork bifurcations, LQR
control, sparse equation discovery, hybrid bouncing-ball dynamics, and heat
diffusion, parametric resonance, and constrained pendulum dynamics. Together
they exercise simulation, classification, stability, system identification,
control synthesis, event detection, state resets, TorchScript deployment,
visualization, and real-data model discovery from NASA space-weather
observations and the USGS earthquake catalog.

## Run

Use the repository's local environment:

```powershell
.\.venv\Scripts\python.exe lorenz_lab.py
.\.venv\Scripts\python.exe pitchfork_lab.py
.\.venv\Scripts\python.exe control_lab.py
.\.venv\Scripts\python.exe discovery_lab.py
.\.venv\Scripts\python.exe hybrid_lab.py
.\.venv\Scripts\python.exe diffusion_lab.py
.\.venv\Scripts\python.exe resonance_lab.py
.\.venv\Scripts\python.exe constraint_lab.py
.\.venv\Scripts\python.exe export_lab.py
.\.venv\Scripts\python.exe fetch_omni.py
.\.venv\Scripts\python.exe space_weather_lab.py
.\.venv\Scripts\python.exe fetch_ridgecrest.py
.\.venv\Scripts\python.exe aftershock_lab.py
.\.venv\Scripts\python.exe aftershock_excitation_lab.py
```

Generated files are written to `artifacts/`:

- `lorenz_lab.png` — attractor and sensitive-dependence visualization
- `lorenz_analysis.json` — parameters and KinoPulse chaos diagnostics
- `lorenz_trajectory.csv` — uniformly sampled trajectory data
- `pitchfork_lab.png` — equilibrium branches and stability crossing
- `pitchfork_analysis.json` — raw detector output and analytical reference
- `control_lab.png` — open-loop versus LQR-stabilized pendulum dynamics
- `control_analysis.json` — gain, poles, controllability, and Riccati checks
- `discovery_lab.png` — hidden truth versus the data-discovered Lorenz model
- `discovery_analysis.json` — recovered equations and unseen-rollout error
- `hybrid_lab.png` — impact events and geometrically shrinking dwell times
- `hybrid_analysis.json` — reset-law and energy-decay measurements
- `diffusion_lab.png` — analytical comparison and grid-convergence study
- `diffusion_analysis.json` — errors, convergence orders, and variance decay
- `resonance_lab.png` — Mathieu instability tongues and direct responses
- `resonance_analysis.json` — resonance classification and amplitude growth
- `constraint_lab.png` — Cartesian pendulum orbit and constraint drift
- `constraint_analysis.json` — initialization, drift, and energy diagnostics
- `space_weather_lab.png` — observed and learned geomagnetic-storm response
- `space_weather_analysis.json` — provenance, coefficients, and held-out errors

The export lab additionally writes `controlled_lti_one_step.pt` and
`export_analysis.json` with script-mode provenance and validation evidence.
The aftershock lab writes `aftershock_lab.png` and `aftershock_analysis.json`
with catalog provenance, model comparison, and holdout diagnostics.
The excitation follow-up writes `aftershock_excitation_lab.png` and
`aftershock_excitation_analysis.json` with strictly causal conditional scores
and binning sensitivity.

Run the regression checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Known library issues found while building the exhibit are documented in
`kinopulse_gaps/`.
