# Research Questions for Real-World Data

This is a prioritized portfolio of problems I would like to explore with
KinoPulse using data that is genuinely available online. The ranking favors
questions where dynamical modeling adds something beyond ordinary forecasting:
regime changes, stability, forcing, memory, hybrid events, interpretable model
discovery, or counterfactual simulation.

## 1. Can we learn the anatomy of a geomagnetic storm?

**Why I want this:** Space weather is almost an ideal natural experiment. The
solar wind is an observed upstream forcing; the magnetosphere is a nonlinear
system with memory; geomagnetic storms have recognizable onset, main, and
recovery phases. The system is beyond human control, so the scientific value
comes from understanding, falsification, and early warning rather than invented
control objectives.

**Data:** NASA's [OMNIWeb documentation](https://omniweb.gsfc.nasa.gov/html/ow_data.html)
describes hourly near-Earth solar-wind magnetic field and plasma data extending
from 1963 to the present, together with geomagnetic indices. Its
[high-resolution service](https://omniweb.gsfc.nasa.gov/ow_min.html) provides
one- and five-minute data shifted to the Earth's bow-shock nose.

**First experiment:** Select several hundred storm and quiet intervals. Treat
solar-wind speed, density, dynamic pressure, and southward magnetic field as
inputs; treat Dst or SYM-H as the observed response. Compare:

- a continuously forced low-dimensional ODE;
- a hybrid model with quiet, injection, and recovery modes;
- a sparse identified model with delayed inputs;
- a neural residual added only where the compact model fails.

Ask whether the inferred guard surfaces correspond to physically meaningful
storm thresholds, whether recovery has one or several timescales, and which
storms are irreducible counterexamples to the compact model.

**KinoPulse role:** nonautonomous systems, hybrid identification, sparse model
discovery, stability and timescale analysis, Monte Carlo uncertainty, and
evidence-rich event diagnostics.

**Access:** public; no key appears necessary for browser/FTP retrieval.

**Status:** Extended from the original 2015 demonstration in
[reports 43](reports/43_chronological_multi_storm_transfer.md) and
[44](reports/44_storm_forcing_gap_robustness.md). A compact forced Dst law beats
persistence on every later selected storm, while a validation-selected memory
term fails to transfer. Strict completeness hides the hardest storms: bounded
gap sensitivity raises mean error from 15.55 to 20.01 nT while retaining 20/20
baseline wins. [Report 46](reports/46_causal_storm_conformal_nowcast.md) then
uses causal forward-fill and one-hour predictions: an 80% group-conformal band
covers 16/20 complete recovery paths, while 99.49% marginal hourly coverage
would hide the failures. A pre-minimum abstention score catches three of four
misses but rejects five correct bands at its least restrictive frozen threshold.
The next target is a prospectively frozen new-storm replay or independent
high-resolution SYM-H validation, not more threshold tuning on these storms.

## 2. When does an open-source community tip from growth into decline?

**Why I want this:** This is dynamics close to my own world. Repositories are
living systems with arrivals, departures, review delays, feedback, bursts,
maintenance debt, and occasional recovery. I want to know whether project
decline is usually a smooth loss of activity or a transition with detectable
early-warning signals.

**Data:** [GH Archive](https://www.gharchive.org/) records GitHub's public event
timeline and offers hourly archives plus an hourly updated BigQuery dataset.
Events include pushes, issues, pull requests, comments, releases, forks, and
stars.

**First experiment:** Build weekly state vectors for a carefully sampled cohort:
active contributors, first-time contributors, review latency, open work,
merge/rejection rates, issue arrivals and closures, release cadence, and
contributor concentration. Identify recurring dynamical regimes and test whether
critical slowing, increasing variance, or changing network structure precedes
long inactivity.

The work must explicitly handle survivorship bias, bots, repository moves, and
the fact that activity is not equivalent to health.

**KinoPulse role:** system identification, hidden regimes, slowly varying
stability, networked dynamics, event models, and counterfactual simulations of
review or release policies.

**Access:** hourly files are public; BigQuery requires a Google Cloud project and
query costs beyond its free allowance.

**Status:** Started in [reports 39](reports/39_open_source_commit_ecology.md),
[40](reports/40_contributor_flow_dynamics.md), and
[41](reports/41_merge_topology_measurement_audit.md), with API validations in
[report 42](reports/42_pull_request_collaboration_panel.md) and
[report 45](reports/45_pull_request_lifecycle_marked_process.md). The
whole-organization snapshot establishes a reproducible commit ecology;
contributor flows show that stable volume can hide greater continuity and
lower concentration; the topology audit shows that first-parent traversal
retains only 22.6% of reachable author identities; and the PR panel validates
the integration-style contrast while invalidating formal-review counts as a
sufficient observation channel. The fixed-creation cohort now preserves merge,
unmerged close, and right censoring; causal marked-process likelihoods show
that lifecycle age predicts much better than homogeneous repository/origin
clocks. No decline or tipping-point claim is currently supported. The next
evidence boundary is a prospectively specified, larger event cohort with
inline review activity and calendar workload.

## 3. How does stress propagate through the interconnected electric grid?

**Why I want this:** A power grid is a network that must continually balance
supply and demand. I am interested in whether public operational data reveals
coherent regional modes, stress propagation, changing coupling, or precursors to
scarcity events.

**Data:** The U.S. Energy Information Administration's
[hourly grid monitor](https://www.eia.gov/electricity/gridmonitor/about) provides
balancing-authority demand, forecasts, net generation, generation by source, and
interchange from 2019 onward. The [EIA open-data API](https://www.eia.gov/opendata/)
also provides bulk files and structured routes.

**First experiment:** Represent balancing authorities as a forced network whose
states include forecast error, ramp rate, net interchange, and generation mix.
Identify time-varying coupling during ordinary days, heat waves, cold snaps, and
renewable ramps. Ask which modes absorb disturbances and when interchange begins
to propagate rather than damp stress.

This dataset is hourly operational data, not grid-frequency telemetry, so it can
support balancing and resilience questions but not claims about subsecond
electromechanical stability.

**KinoPulse role:** network dynamics, parameter-varying systems, stability
atlases, robust control thought experiments, and anomaly-driven regime discovery.

**Access:** free registration/API key; six-month CSV downloads and bulk files
offer alternatives.

## 4. Can arrhythmia be understood as a transition between oscillatory modes?

**Why I want this:** Heart rhythms make hybrid dynamics tangible: a continuous
electrical waveform produces discrete beats, and clinically meaningful events
often involve changes in timing, morphology, and mode. I would like to model the
transition, not merely classify a waveform window.

**Data:** PhysioNet's
[MIT-BIH Arrhythmia Database](https://physionet.org/content/mitdb/1.0.0/)
contains 48 half-hour, two-channel ambulatory ECG recordings from 47 subjects,
sampled at 360 Hz, with roughly 110,000 expert beat annotations. The files are
openly downloadable under an attribution license.

**First experiment:** Learn a phase-amplitude representation of normal rhythm,
then model ectopic beats and rhythm changes as hybrid guards and resets. Test
whether the learned state provides warning before annotated events and whether
patient-specific adaptation improves prediction without destroying a shared
physiological structure.

This would be a methodological exploration, not a medical device or clinical
claim. Patient-level splits, annotation uncertainty, and subgroup limitations
must remain visible.

**KinoPulse role:** oscillator analysis, phase response, hybrid events, online
adaptation, uncertainty, and interpretable guard discovery.

**Access:** direct public download; approximately 104 MB uncompressed.

## 5. How does a city recover its mobility rhythm after a shock?

**Why I want this:** Cities are strongly forced oscillators—daily and weekly
rhythms perturbed by weather, holidays, disruptions, and policy changes. I want
to separate ordinary periodic forcing from genuine changes in the underlying
mobility state.

**Data:** New York City's TLC makes
[trip-record data](https://www.nyc.gov/site/tlc/about/request-data.page)
available for immediate download. The records are also published as monthly
[Parquet files on AWS](https://registry.opendata.aws/nyc-tlc-trip-records-pds/).

**First experiment:** Aggregate trips into flows among taxi zones, build a
time-dependent network state, and learn its normal daily/weekly limit cycle.
Measure the phase displacement and recovery time after snowstorms, transit
outages, holidays, and other externally documented shocks. Test whether recovery
is uniform or whether some neighborhoods occupy metastable mobility regimes.

**KinoPulse role:** periodic forcing, stroboscopic maps, network dynamics,
slowly varying parameters, anomaly transitions, and recovery-time analysis.

**Access:** direct public Parquet downloads; large but easy to partition by month.

## 6. Is ENSO better described as an oscillator, a switching process, or both?

**Why I want this:** El Niño and La Niña are familiar labels for a coupled
ocean-atmosphere process whose predictability, asymmetry, and changing behavior
remain scientifically interesting. It is a good test of whether compact learned
dynamics clarify a system or merely redescribe an index.

**Data:** NOAA's [ENSO portal](https://psl.noaa.gov/enso/) links historic and
current Multivariate ENSO Index values and related time series; the
[monthly MEI.v2 page](https://psl.noaa.gov/data/timeseries/month/DS/MEIV2/)
provides an index combining oceanic and atmospheric variables.

**First experiment:** Compare delayed oscillator, slow-fast, stochastic, and
three-regime hybrid models across rolling historical windows. Ask whether model
structure or stability changes materially over time and whether apparent tipping
signals survive honest out-of-sample evaluation.

**KinoPulse role:** nonautonomous and slow-fast analysis, stochastic dynamics,
bifurcation tracking, model comparison, and uncertainty-aware identification.

**Access:** public monthly time series; richer gridded inputs would require more
substantial NOAA data handling.

**Status:** The scalar baseline is complete in
[report 47](reports/47_enso_oscillator_or_switching.md), and
[report 48](reports/48_enso_recharge_state.md) adds NOAA equatorial upper-ocean
heat content. The coupled model learns the expected recharge signs and
anticipates the sharp 2026 sign transition, but it loses the original
validation selection, its later point gains are uncertain, and it severely
underpredicts the 2026 heat surge. [Report 49](reports/49_enso_wind_driven_recharge.md)
then finds a stable three-month low-level-wind impulse that improves later
one-month heat-change RMSE by 9.6% over the matched no-wind state. The R1 wind
archive ends before 2026. [Report 50](reports/50_enso_core_measurement_bridge.md)
completes the predeclared overlap bridge to NOAA CORe: it retains 92.5% of the
later wind-model gain but does not explain the opened 2026 heat surge. A frozen
July 2026 heat-state prediction now provides the stopping point. Do not tune
this branch again until that outcome is available; the next scientifically
useful act is prospective scoring, not another retrospective model.

## 7. What dynamical law governs aftershock cascades?

**Status:** Paused after reports 12 through 38. Robust partial pooling improves
whole-sequence count forecasts, but external uncertainty is poorly calibrated,
alarm identities depend on the reported-magnitude channel, and high magnitudes
are systematically front-loaded even within recorded network and magnitude-
type strata. Report 38 records the stopping rule: resume only with matched
catalogs and completeness estimates, marked-process observation modeling, or a
prospectively frozen benchmark cohort.

**Why I want this:** Earthquakes are events interacting across time, magnitude,
depth, and space. They challenge KinoPulse to connect continuous latent stress
with discrete point events rather than forcing everything into a smooth state
trajectory.

**Data:** The USGS
[Earthquake Catalog API](https://earthquake.usgs.gov/fdsnws/event/1/)
supports CSV, GeoJSON, and QuakeML queries filtered by time, geography, depth,
and magnitude. Individual queries are limited to 20,000 events but can be
partitioned reproducibly.

**First experiment:** Select well-recorded mainshock sequences and compare a
classical self-exciting event model against a hybrid latent-stress model. Test
whether learned state variables improve spatial or magnitude-conditioned
aftershock forecasts, and analyze cases where catalog completeness changes
immediately after a large event.

**KinoPulse role:** stochastic and hybrid dynamics, event likelihoods, online
parameter adaptation, spatial fields, and simulation-based calibration.

**Access:** public API without a key.

## 8. Can stellar variability reveal a compact hidden oscillator?

**Why I want this:** Stellar light curves contain rotation, pulsation, flares,
instrumental systematics, and planetary transits on different timescales. They
offer a beautiful setting for separating continuous dynamics from discrete
events.

**Data:** NASA's [TESS data-products guide](https://heasarc.gsfc.nasa.gov/docs/tess/data-products.html)
states that light curves and target-pixel files are archived publicly at MAST.
The [NASA Exoplanet Archive](https://exoplanetarchive.ipac.caltech.edu/) provides
large searchable collections of light curves and planet metadata.

**First experiment:** Choose variable stars with repeated TESS sectors. Identify
compact oscillatory models on one sector, test phase and amplitude stability on
later sectors, and treat flares or transits as candidate hybrid events rather
than asking a smooth model to explain them.

**KinoPulse role:** spectral and phase analysis, nonautonomous oscillators,
sparse discovery, hybrid event separation, and long-horizon validation.

**Access:** public, but archive queries and astronomy-specific formats add setup
cost.

## 9. Can coastal buoys reveal a changing wave regime before extremes?

**Why I want this:** Ocean observations connect field dynamics to a tangible
safety question. I am interested in whether short-lived extreme waves arise as
outliers within one regime or as part of a detectable change in the surrounding
wave field.

**Data:** NOAA's [National Data Buoy Center](https://www.ndbc.noaa.gov/)
provides current observations and station-linked historical data for meteorology
and waves.

**First experiment:** Build multiscale state representations from spectral wave
parameters, wind, pressure, and sea state at long-running stations. Identify
regime transitions and test whether extremes are preceded by changes in spectral
shape, nonlinear coupling, or directional spread.

**KinoPulse role:** PDE-inspired reduced models, spectral operators, stochastic
stability, regime discovery, and extreme-event simulation.

**Access:** public; station coverage and variable consistency require auditing.

## 10. Can wastewater measurements expose epidemic waves and reporting delay?

**Why I want this:** Wastewater is a population-level observation of an epidemic
process, but it is indirect, delayed, noisy, and irregularly sampled. That makes
it a useful test of identification under partial observation rather than another
curve-fitting exercise.

**Data:** The CDC publishes a documented
[SARS-CoV-2 wastewater surveillance dataset](https://data.cdc.gov/Public-Health-Surveillance/CDC-Wastewater-Data-for-SARS-CoV-2/j9g8-acpt/about_data)
through its open-data platform and API.

**First experiment:** Fit latent epidemic dynamics with explicit observation
delay and site-specific scaling, then test whether shared dynamics transfer
across treatment plants. Compare continuous latent-state models with switching
models around variant or policy eras while avoiding causal claims unsupported by
the observational data.

**KinoPulse role:** partially observed dynamics, parameter identification,
nonautonomous forcing, online adaptation, and uncertainty propagation.

**Access:** public API; interpretation requires careful attention to changing
coverage and measurement methods.

## What I would start first

I would begin with the geomagnetic-storm project. It has the best combination of
clear input/output direction, nonlinear memory, rare transitions, long history,
high-resolution episodes, physical interpretability, and public access. It also
uses capabilities that make KinoPulse distinctive rather than treating it as a
generic prediction package.

The first deliverable would be deliberately small: ten storms, ten quiet
intervals, one compact forced model, one hybrid alternative, and a report that
shows where each succeeds and fails. If that evidence is promising, the next
step would scale the experiment and let model disagreement choose the most
informative new intervals.
