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

The earthquake research line's conclusions, withdrawn claims, and stopping
rule are summarized in [report 38](reports/38_earthquake_program_synthesis.md).

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
.\.venv\Scripts\python.exe fetch_external_aftershock_population.py
.\.venv\Scripts\python.exe external_aftershock_lab.py
.\.venv\Scripts\python.exe external_uncertainty_lab.py
.\.venv\Scripts\python.exe online_uncertainty_lab.py
.\.venv\Scripts\python.exe abstention_audit_lab.py
.\.venv\Scripts\python.exe external_sequential_monitor_lab.py
.\.venv\Scripts\python.exe predictive_sequential_monitor_lab.py
.\.venv\Scripts\python.exe predictive_threshold_stability_lab.py
.\.venv\Scripts\python.exe full_predictive_stability_lab.py
.\.venv\Scripts\python.exe fetch_japan_aftershock_population.py
.\.venv\Scripts\python.exe japan_transfer_lab.py
.\.venv\Scripts\python.exe audit_japan_cohort_isolation.py
.\.venv\Scripts\python.exe japan_alarm_anatomy_lab.py
.\.venv\Scripts\python.exe cohort_boundary_audit_lab.py
.\.venv\Scripts\python.exe cohort_boundary_impact_lab.py
.\.venv\Scripts\python.exe catalog_magnitude_support_lab.py
.\.venv\Scripts\python.exe magnitude_floor_alarm_robustness_lab.py
.\.venv\Scripts\python.exe magnitude_time_coupling_lab.py
.\.venv\Scripts\python.exe magnitude_provenance_stratification_lab.py
.\.venv\Scripts\python.exe fetch_open_source_community.py
.\.venv\Scripts\python.exe open_source_commit_ecology_lab.py
.\.venv\Scripts\python.exe contributor_flow_lab.py
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
The external-validation lab writes `external_aftershock_validation.png` and
`external_aftershock_validation.json`, preserving the failed 2026 temporal
screen and the frozen 37-sequence Alaska/Gulf geographic test.
The chronological uncertainty follow-up writes
`external_uncertainty_recalibration.png` and
`external_uncertainty_recalibration.json`, measuring whether pre-2020
external-domain interval corrections survive from 2020 through 2025.
The prequential uncertainty lab writes `online_uncertainty_calibration.png` and
`online_uncertainty_calibration.json`, replaying expanding and rolling grouped
calibration with a 30-day outcome-maturity embargo.
The abstention audit writes `abstention_audit.png` and `abstention_audit.json`,
testing whether causal feature novelty, forecast disagreement, or interval
width can identify unsafe external predictions before their outcomes arrive.
The external sequential-monitor audit writes `external_sequential_monitor.png`
and `external_sequential_monitor.json`, contrasting internally valid 1%
fixed-Poisson calibration with the much broader variation in real external
sequences.
The predictive sequential-monitor follow-up writes
`predictive_sequential_monitor.png` and `predictive_sequential_monitor.json`,
propagating first-day-conditioned population-shape uncertainty into complete
null paths before calibrating the same scan statistic.
The predictive-threshold stability lab writes
`predictive_threshold_stability.png` and
`predictive_threshold_stability.json`, repeating full proposal and path
calibration to distinguish robust alarms from Monte Carlo boundary cases.
The full predictive-stability replay writes `full_predictive_stability.png` and
`full_predictive_stability.json`, extending independent calibration batches to
all 37 external targets and comparing alarm-consensus policies.
The Japan/Kuril transfer writes `japan_transfer.png` and
`japan_transfer.json`, applying the frozen western hierarchy and four-batch
unanimous predictive-null rule to a second geography defined before download.
The cohort-edge audit and alarm-anatomy follow-up write
`japan_cohort_isolation_audit.png` and `japan_alarm_anatomy.png`. They show that
the transfer's sole alarm was a rectangular-boundary selection leak, leaving
eight boundary-isolated targets and no valid alarms.
The foundational cohort audit writes `cohort_boundary_audit.png` and
`cohort_boundary_impact.png`. All 12 western development targets pass; a single
Alaska graph-policy ambiguity changes denominators but not model or alarm
conclusions.
The catalog support audit writes `catalog_magnitude_support.png` and
`catalog_magnitude_support.json`, showing that the Japan/Kuril catalogs are
effectively global M4+ reporting and cannot support a matched-M2.5 transfer
claim with the existing western population.
The magnitude-floor robustness lab writes
`magnitude_floor_alarm_robustness.png` and
`magnitude_floor_alarm_robustness.json`, refitting the clean Alaska audit across
four reported-magnitude channels and showing that alarm identities change.
The magnitude-time coupling lab writes `magnitude_time_coupling.png` and
`magnitude_time_coupling.json`, conditionally testing whether high-magnitude
labels are exchangeable between the first day and the rest of the forecast.
The reporting-provenance stratification lab writes
`magnitude_provenance_stratification.png` and
`magnitude_provenance_stratification.json`, testing whether network or
magnitude-type composition explains the mark-timing result.
The open-source commit-ecology lab writes `open_source_commit_ecology.png` and
`open_source_commit_ecology.json`. It freezes a whole public organization,
measures activity composition, and explicitly stops short of treating commits
as project health.
The contributor-flow follow-up writes `contributor_flow.png` and
`contributor_flow.json`, decomposing weekly participation into newly observed,
continuing, and returning author identifiers with a chronological predictive
check.

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
