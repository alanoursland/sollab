# KinoPulse Playground Reports

These reports document the experiments in this repository as reproducible
scientific software studies. They describe the question, model, KinoPulse
capabilities exercised, numerical procedure, evidence, limitations, and
release-under-test observations for each lab.

For a practitioner-oriented path through reports 12–38, including data
contracts, reproduction tiers, interpretation, and safety boundaries, see the
[earthquake and aftershock research guide](../EARTHQUAKE_README.md).

For the connected GitHub and open-source community program in reports 39–42
and 45, see the
[open-source community and GitHub research guide](../OPEN_SOURCE_COMMUNITY_README.md).

For the connected ENSO program in reports 47–50, including chronology, public
data contracts, appropriate use, and the frozen July 2026 scoring rule, see the
[ENSO dynamics research guide](../ENSO_README.md).

All reported values come from the JSON evidence generated locally in
`artifacts/`. The JSON and downloaded source data are intentionally ignored;
figures are committed for convenient review. Results were last reproduced on
2026-07-17. Reports 45–50 use KinoPulse `0.1.0.dev2026071623`; report 51 uses
`0.1.0.dev2026071712`; earlier release-validation reports identify their own
release under test.

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
| [Full predictive stability replay](30_full_predictive_stability_replay.md) | Did the selected stress panel hide unstable quiet targets? | No: all 33 quiet targets remain quiet in 4/4 fresh batches; combined alarm evidence separates two unanimous, one near-unanimous, and one marginal target. |
| [Japan/Kuril transfer](31_japan_kuril_transfer.md) | Does the rare unanimous alarm survive a second untouched geography? | The frozen rectangle yields one apparent alarm, but a later boundary audit finds that target is not independent. |
| [Japan alarm anatomy and cohort edge](32_japan_alarm_anatomy_and_cohort_edge.md) | Is the sole second-geography alarm scientifically valid? | No: an equal-M6.1 event 0.98 days earlier and 32.8 km away was clipped by the cohort boundary; all eight valid targets are quiet. |
| [Foundational cohort isolation audit](33_foundational_cohort_isolation_audit.md) | Did the same selection flaw contaminate the western or Alaska cohorts? | All 12 development targets pass; one Alaska graph-chain ambiguity changes denominators but no substantive conclusion. |
| [Catalog magnitude-support audit](34_catalog_magnitude_support_audit.md) | Do M2.5 queries create comparable western, Alaska, and Japan catalogs? | No: Japan is effectively all M4+ global reporting; M4 harmonization leaves only three western development sequences. |
| [Magnitude-floor alarm robustness](35_magnitude_floor_alarm_robustness.md) | Are rare Alaska predictive alarms invariant to the reported-magnitude floor? | No: three original targets are eligible but quiet at M3, one is ineligible, and two different Fox Islands sequences begin alarming. |
| [Magnitude-time mark coupling](36_magnitude_time_mark_coupling.md) | Is raising the magnitude floor equivalent to random thinning of a common aftershock clock? | No: high magnitudes are strongly front-loaded, and mark timing explains the alarm-identity swap. |
| [Reporting-provenance stratification](37_reporting_provenance_stratification.md) | Does changing network or magnitude-type composition explain the mark-timing effect? | Only partly: network conditioning changes almost nothing and a strong within-magnitude-type residual remains. |
| [Earthquake program synthesis](38_earthquake_program_synthesis.md) | What survived the earthquake program, and where should it stop? | Pause at the observation-system boundary; stronger progress requires new data, marked-process support, or prospective validation. |
| [Open-source commit ecology](39_open_source_commit_ecology.md) | Can a whole-organization Git history support a defensible community-dynamics experiment? | Recent volume is 97.4% of the prior year, but contribution concentration changes sharply; activity is not health. |
| [Contributor flow dynamics](40_contributor_flow_dynamics.md) | What renewal mechanisms sit beneath nearly stable commit volume? | Active-author weeks rise 21% and continuing weeks rise 83%, while a flow-aware predictor improves RMSE only 1.0%. |
| [Merge-topology measurement audit](41_merge_topology_measurement_audit.md) | Does Git traversal policy change the observed contributor ecology? | First-parent history retains only 22.6% of reachable authors, although conditional 52-week return changes by just 1.1 points. |
| [Pull-request collaboration panel](42_pull_request_collaboration_panel.md) | Does the Git-topology contrast survive a bounded API validation panel? | Yes, but formal reviews appear in only 1/10 PRs per repository and a homogeneous response clock is not meaningful. |
| [Chronological multi-storm transfer](43_chronological_multi_storm_transfer.md) | Does the compact Dst response law survive later geomagnetic storms? | It beats persistence on 11/11 strict future storms; a validation-selected forcing memory worsens test RMSE by 8.0%. |
| [Storm forcing-gap robustness](44_storm_forcing_gap_robustness.md) | Does complete-case selection hide difficult storms? | Yes: bounded interpolation admits all 20 later storms and raises honest RMSE from 15.55 to 20.01 nT, while preserving 20/20 baseline wins. |
| [Pull-request lifecycle marked process](45_pull_request_lifecycle_marked_process.md) | Can a fixed creation cohort support causal response and competing terminal hazards? | Yes; age-structured hazards beat every homogeneous alternative out of sample, while repository/origin detail does not. |
| [Causal storm conformal nowcast](46_causal_storm_conformal_nowcast.md) | Can one-hour Dst predictions carry honest whole-storm uncertainty and selective abstention? | Group-conformal bands cover 16/20 storms while marginal hourly coverage hides the four failures; abstention catches three at substantial retention cost. |
| [ENSO oscillator or switching](47_enso_oscillator_or_switching.md) | Does threshold switching beat a compact delayed oscillator on untouched MEI.v2 years? | Switching has the best point RMSE, but its 2.7% edge over the oscillator is not distinguishable with eight whole-year test units. |
| [ENSO recharge state](48_enso_recharge_state.md) | Does equatorial upper-ocean heat add transferable memory beyond scalar MEI dynamics? | The learned coupling has recharge-oscillator signs and anticipates the 2026 sign transition, but loses original validation and misses the heat surge amplitude. |
| [ENSO wind-driven recharge](49_enso_wind_driven_recharge.md) | Does observed western-Pacific low-level wind improve the next ocean-heat tendency? | Three months of wind history improve later RMSE 9.6% over the matched state model and reveal a stable transient impulse kernel, but the archive ends before 2026. |
| [ENSO CORe measurement bridge](50_enso_core_measurement_bridge.md) | Can the wind mechanism cross from retired R1 to active CORe without a silent splice? | A frozen affine bridge preserves 92.5% of the later heat-model gain, fails to explain the 2026 surge, and records a prospective July heat prediction. |
| [Structured residual gating](51_structured_residual_gating_validation.md) | Can a learned gate suppress threshold chatter while retaining exact expert choices and useful gradients? | Hysteresis and dwell reduce 14 naive switches to the two true transitions; structured residuals match closed-form composition exactly. |

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
.\.venv\Scripts\python.exe fetch_omni_population.py
.\.venv\Scripts\python.exe multi_storm_transfer_lab.py
.\.venv\Scripts\python.exe storm_forcing_gap_robustness_lab.py
.\.venv\Scripts\python.exe storm_conformal_nowcast_lab.py
```

The ENSO report additionally requires:

```powershell
.\.venv\Scripts\python.exe fetch_meiv2.py
.\.venv\Scripts\python.exe enso_oscillator_lab.py
.\.venv\Scripts\python.exe fetch_enso_heat_content.py
.\.venv\Scripts\python.exe enso_recharge_lab.py
.\.venv\Scripts\python.exe fetch_enso_wind.py
.\.venv\Scripts\python.exe enso_wind_heat_lab.py
.\.venv\Scripts\python.exe fetch_enso_core_wind.py
.\.venv\Scripts\python.exe enso_core_bridge_lab.py
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
.\.venv\Scripts\python.exe merge_topology_audit_lab.py
.\.venv\Scripts\python.exe fetch_pull_request_panel.py
.\.venv\Scripts\python.exe pull_request_collaboration_lab.py
.\.venv\Scripts\python.exe fetch_pull_request_lifecycle_panel.py
.\.venv\Scripts\python.exe pull_request_lifecycle_lab.py
```

These are exploratory numerical experiments, not claims that every computed
quantity is a formal certificate. Each report states its own evidence boundary.
