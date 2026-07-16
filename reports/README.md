# KinoPulse Playground Reports

These reports document the experiments in this repository as reproducible
scientific software studies. They describe the question, model, KinoPulse
capabilities exercised, numerical procedure, evidence, limitations, and
release-under-test observations for each lab.

For a practitioner-oriented path through reports 12–22, including data
contracts, reproduction tiers, interpretation, and safety boundaries, see the
[earthquake and aftershock research guide](../EARTHQUAKE_README.md).

All reported values come from the JSON evidence generated locally in
`artifacts/`. The JSON and downloaded source data are intentionally ignored;
figures are committed for convenient review. Results were last reproduced on
2026-07-15 using KinoPulse `0.1.0.dev2026071512` in the repository's `.venv`.

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
| [Aftershock spatial memory](14_aftershock_spatial_memory.md) | Can causal regional activity predict where the next event occurs? | A plausible latent state cuts training spatial deviance `16.1%` but worsens holdout by `3.1%`. |
| [Aftershock law transfer](15_aftershock_law_transfer.md) | Does one relaxation shape transfer to an unseen earthquake? | Transferred Omori wins `5 / 8` sequences but fails oppositely on El Mayor and Ridgecrest. |
| [Hierarchical aftershock transfer](16_hierarchical_aftershock_transfer.md) | When should a new sequence escape the population shape? | Partial pooling cuts summed deviance `74.1%` and its 80% totals cover `7 / 8` sequences. |
| [Aftershock meta-prediction](17_aftershock_population_meta_prediction.md) | Can mainshock metadata and the first day predict a sequence's decay personality? | Model-blind screening retains 12 sequences, but conditioned point estimates worsen held-out count forecasts. |
| [Expanded hierarchy and count guard](18_expanded_aftershock_hierarchy_and_count_guard.md) | Does partial pooling survive expansion, and can unsafe metadata be rejected? | Partial pooling wins `7 / 12`; count-space validation rejects metadata in every fold and preserves the stronger model. |
| [Change-detector audit](19_change_detector_contract_audit.md) | Can online residual monitoring detect when the hierarchy enters a new regime? | Synthetic probes expose dead configurations, repeated alarms, and stale reset state; real alarms are not yet specific enough. |
| [Calibrated sequential monitor](20_calibrated_sequential_regime_monitor.md) | Can a forecast admit early that it has entered a sustained higher/lower-rate regime? | A 1%-calibrated scan detects all three predictive-total misses by day 5.48 and validates at `0.972%` null alarms. |
| [Portable monitor export](21_portable_sequential_monitor_export.md) | What should be exported for researchers without overstating the earthquake model? | A generic 5,983-byte strict TorchScript monitor passes 32 saved-artifact cases exactly and contains no trained seismic parameters. |
| [Release validation](22_release_validation_2026071512.md) | Do the new count, fit, and point-process contracts survive analytical oracles? | Count and fit APIs pass and now power the aftershock lab; a causal left-boundary bug remains in history-dependent compensators. |
| [External aftershock validation](23_external_aftershock_validation.md) | Does the frozen western hierarchy survive outside its home region? | Point forecasts improve across 37 Alaska-sector sequences, but nominal 80% predictive totals cover only 51.4%. |
| [Chronological uncertainty recalibration](24_chronological_uncertainty_recalibration.md) | Can earlier Alaska outcomes repair later predictive coverage? | Asymmetric expansion raises 2020–2025 coverage from 28.6% to 71.4%, still below target at 83% greater median width. |
| [Prequential uncertainty calibration](25_prequential_uncertainty_calibration.md) | Can completed external outcomes repair the next interval online? | Rolling calibration reaches 80% overall coverage by allowing later median width to grow to 8.73×. |
| [Causal abstention audit](26_causal_abstention_audit.md) | Can target-time warning signals identify which external intervals should not be issued? | Consensus and width gates reject covered forecasts while retaining every miss; the simple abstention signals fail. |
| [External sequential-monitor audit](27_external_sequential_monitor_audit.md) | Does the 1%-calibrated monitor retain its interpretation on external earthquakes? | Its fixed null validates internally, but 64.9% of real external sequences alarm; the null is too narrow. |
| [Hierarchy-predictive sequential monitor](28_hierarchy_predictive_sequential_monitor.md) | Can a predictive rather than point-Poisson null repair the external alarm flood? | External alarms fall from 24 to four, all raw misses, at a large cost in threshold and detection delay. |
| [Predictive threshold stability](29_predictive_threshold_stability.md) | Do the four predictive-null alarms survive independent proposal batches? | Three alarms reproduce in 8/8 batches; the day-30 fourth alarm reproduces only 3/8 times. |

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
```

These are exploratory numerical experiments, not claims that every computed
quantity is a formal certificate. Each report states its own evidence boundary.
