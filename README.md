# KinoPulse Playground

See [DREAMS.md](DREAMS.md) for the long-term vision behind this dynamics
laboratory, and [RESEARCH_QUESTIONS.md](RESEARCH_QUESTIONS.md) for a prioritized
portfolio built around public real-world datasets.

Detailed methods, results, limitations, and reproduction instructions are in
the [experiment reports](reports/README.md).

Seismologists and earthquake-forecast practitioners should start with the
[earthquake and aftershock research guide](EARTHQUAKE_README.md). It separates
the retrospective models, reusable forecast monitor, reproduction paths, and
public-safety boundaries.

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
.\.venv\Scripts\python.exe aftershock_spatial_lab.py
.\.venv\Scripts\python.exe fetch_aftershock_benchmark.py
.\.venv\Scripts\python.exe aftershock_transfer_lab.py
.\.venv\Scripts\python.exe aftershock_hierarchy_lab.py
.\.venv\Scripts\python.exe fetch_aftershock_population.py
.\.venv\Scripts\python.exe aftershock_meta_lab.py
.\.venv\Scripts\python.exe aftershock_population_hierarchy_lab.py
.\.venv\Scripts\python.exe aftershock_count_guard_lab.py
.\.venv\Scripts\python.exe change_detector_lab.py
.\.venv\Scripts\python.exe sequential_regime_lab.py
.\.venv\Scripts\python.exe export_sequential_monitor.py
.\.venv\Scripts\python.exe kinopulse_release_lab.py
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
The spatial-memory follow-up writes `aftershock_spatial_lab.png` and
`aftershock_spatial_analysis.json`, including along-strike holdout diagnostics
and a deliberately preserved overfitting result.
The transfer benchmark writes `aftershock_transfer_lab.png` and
`aftershock_transfer_analysis.json`, with eight leave-one-sequence-out folds
and complete USGS query provenance.
The hierarchical follow-up writes `aftershock_hierarchy_lab.png` and
`aftershock_hierarchy_analysis.json`, with nested pooling selection and
population predictive intervals.
The population meta-prediction follow-up writes `aftershock_meta_prediction.png`
and `aftershock_meta_results.json`. Its generated selection manifest preserves
the model-blind USGS population screen and every rejection reason.
The expanded hierarchy and count-space guard write
`aftershock_population_hierarchy.png` and `aftershock_count_guard.png`, with
nested validation evidence showing both successful adaptation and explicit
rejection of unsafe metadata corrections.
The change-detector audit writes `change_detector_lab.png` and
`change_detector_analysis.json`, combining controlled contract probes with
causal held-out forecast-residual streams.
The calibrated sequential-monitor follow-up writes `sequential_regime_lab.png`
and `sequential_regime_analysis.json`, with target-specific null calibration,
change-direction estimates, and independent false-alarm validation.
The release-validation lab writes `kinopulse_2026071512_validation.json`, with
analytical count, point-process, fitting, residual-accounting, and covariance
oracles for the installed KinoPulse wheel.

## Portable research monitor

The reusable forecast-monitoring kernel is committed in `models/`:

- `sequential_poisson_regime_monitor.pt` — genuine strict-script TorchScript;
- `sequential_poisson_regime_monitor.provenance.json` — SHA-256, versions,
  validation, and machine-readable contracts; and
- `sequential_poisson_regime_monitor.md` — model card, safety boundary, and use.

It contains no trained earthquake parameters and is not an earthquake forecast
or public-safety alarm. Researchers must supply their own forecast and
scientifically calibrated threshold. The repository currently has no license
file; the owner should select one before external reuse is invited.

Run the regression checks with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Known library issues found while building the exhibit are documented in
`kinopulse_gaps/`.
