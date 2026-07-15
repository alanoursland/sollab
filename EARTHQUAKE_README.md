# Earthquake and aftershock research guide

This guide is the practitioner entry point to the earthquake work in the
KinoPulse Playground. The project asks a sequence of connected questions:

- How well does a compact aftershock decay law forecast beyond its fit window?
- Which parts of that law transfer between earthquakes?
- Can a new sequence adapt safely from a small historical population?
- Can an existing forecast recognize, causally, that its rate has entered a
  different regime?

The short answer is that modified Omori decay is a strong baseline, robust
partial pooling is promising on this small retrospective population, simple
metadata and spatial/excitation extensions have not generalized reliably, and
a calibrated monitor can identify sustained forecast failure. None of these
components is an operational earthquake forecast or public-warning system.

## Read this first

The work is public research software, not a validated seismic product. It does
not estimate the probability of a damaging earthquake, ground motion, loss, or
individual-event magnitude. It must not drive public alerts or protective
action.

The portable monitor in `models/` is particularly easy to misunderstand. It
only compares observed binned counts with expected binned counts supplied by
another forecast. It contains no earthquake parameters and cannot create a
forecast by itself. A threshold is meaningful only when calibrated against the
complete predictive uncertainty of the practitioner's own model and catalog.

This repository currently has no license file. Public visibility alone does
not grant permission to reuse or redistribute the code or binary artifact.

## Choose your path

| If you want to... | Start here | What you will get |
|---|---|---|
| Understand the scientific result | [Ridgecrest baseline](reports/12_ridgecrest_aftershocks.md), then [expanded hierarchy](reports/18_expanded_aftershock_hierarchy_and_count_guard.md) | The core single-sequence and population evidence |
| Audit every experiment in order | [Earthquake report sequence](#experiment-map) | Methods, held-out boundaries, failures, and limitations |
| Reproduce one compact example | [Single-sequence reproduction](#single-sequence-reproduction) | A fetched USGS catalog, fitted laws, scores, and figure |
| Reproduce the population study | [Population reproduction](#population-reproduction) | Model-blind screening and leave-one-earthquake-out evidence |
| Monitor your own count forecast | [Portable monitor model card](models/sequential_poisson_regime_monitor.md) | A generic TorchScript scan plus calibration reference code |
| Adapt the work to a new region | [Practitioner adaptation checklist](#practitioner-adaptation-checklist) | The decisions that must be remade rather than copied |
| Inspect current KinoPulse boundaries | [Release validation](reports/22_release_validation_2026071512.md) | Analytical API checks and a known point-process defect |

## What is usable today

### Retrospective modeling code

The Python labs are reproducible research implementations for binned aftershock
counts. They provide transparent Omori/exponential fits, strictly separated
calibration and evaluation windows, whole-earthquake cross-validation, robust
population shrinkage, predictive-count checks, and negative-result baselines.
They are appropriate starting points for methods research and independent
replication.

There is no committed trained twelve-earthquake forecast artifact. That is
deliberate: twelve selected and heterogeneous catalogs are not enough evidence
for a general model release.

### Portable forecast monitor

`models/sequential_poisson_regime_monitor.pt` is a saved strict-TorchScript
implementation of a two-sided sequential Poisson tail-rate scan. Given a
prefix of observed and expected bin counts plus a calibrated threshold, it
returns:

- the maximum twice-log-likelihood-ratio statistic;
- an estimated change-bin index;
- the observed/expected tail-rate multiplier;
- higher/lower direction; and
- a threshold-crossing indicator.

The artifact is stateless and deterministic: pass the complete observed and
expected prefix at every update. Its [model card](models/sequential_poisson_regime_monitor.md)
contains the exact tensor contract, example code, provenance, hash, and safety
boundary. The reference Python implementation and fixed-Poisson calibration
helpers are in `poisson_regime_monitor.py`.

The supplied calibration helper controls repeated scanning only for a fixed,
independent-Poisson expected trajectory. A real application should normally
simulate forecast-parameter uncertainty, catalog uncertainty, dependence, and
any data latency or missingness in its null procedure.

## Data and forecast boundaries

All catalogs come from the public [USGS FDSN Event Web
Service](https://earthquake.usgs.gov/fdsnws/event/1/). Fetch scripts save the
exact query and SHA-256 provenance used by the experiments.

The Ridgecrest baseline uses M2.5+ events within 100 km of the 2019 M7.1
mainshock, from 30 days before to 30 days after. The first post-mainshock hour
is excluded because early catalog completeness is especially concerning. The
model is fit from hour 1 through day 7 and evaluated on untouched days 7–30.

The population study uses a model-blind screen:

1. Query M5.8+ events from 2010 through 2025 in a western North American box.
2. Within overlapping 45-day, 150-km neighborhoods, retain the largest event.
3. Fetch M2.5+ catalogs within 100 km from day -30 through day +30.
4. Require at least 15 events in both hour-1-to-day-1 calibration and
   day-1-to-day-30 evaluation windows.
5. Preserve every acceptance, rejection reason, URL, and digest.

This yields 12 of 40 initial candidates. That is a reproducible selection rule,
not proof that the retained catalogs are complete, representative, or a single
tectonic population. A fixed M2.5 threshold is especially questionable across
networks, years, offshore regions, and the earliest post-mainshock period.

For every population score, the target earthquake is held out as a complete
group. Historical earthquakes may contribute their 30-day histories; the
target contributes only information explicitly available by the calibration
boundary. Target future counts cannot enter fitting or hyperparameter
selection.

## Main findings

### 1. Power-law relaxation is the right compact Ridgecrest baseline

A modified Omori law fit through day 7 predicts 341 of 387 held-out events
through day 30. Its holdout Poisson deviance is `28.34`, versus `2821.80` for an
exponential relaxation. Moderate binning changes preserve that conclusion.
This supports a long-memory decay baseline for this catalog; it is not evidence
that one global curve explains secondary triggering, fault geometry, or
time-varying completeness.

### 2. Plausible complexity often failed out of sample

A magnitude-weighted excitation kernel improved Ridgecrest holdout deviance by
only `2.12%` and did not win most causal intervals. A latent spatial-memory
model improved training spatial deviance by `16.1%` but worsened holdout by
`3.1%`. Simple first-day metadata conditioning increased total population
deviance substantially. These are preserved negative results, not unfinished
success stories.

### 3. Transfer is heterogeneous; partial pooling helps

One shared Omori shape transferred unevenly. In the expanded 12-sequence
leave-one-earthquake-out study, a robust partial-pooling model won `7 / 12`
targets and reduced summed day-1-to-day-30 deviance from `3576.5` for a fixed
robust population shape to `1148.4`. Central 80% predictive total intervals
covered `9 / 12` sequences.

The misses matter as much as the aggregate win. Ridgecrest and Stanley remained
more active than predicted, while the 2021 offshore Oregon sequence collapsed
far faster than predicted. Partial pooling is therefore a useful research
baseline, not a universally calibrated forecast.

### 4. Validation can correctly refuse a feature

A metadata-conditioned prior raised summed deviance to `2049.8`. When its trust
weight was selected in nested future-count space, every outer fold chose zero
metadata trust. The guard preserved the stronger hierarchy by refusing a
plausible but harmful correction. The practical lesson is to validate model
choices in the same observable forecast space used for final judgment.

### 5. A forecast can monitor its own sustained failure

Under a fixed-Poisson null, the sequential monitor detected all three total
predictive-interval misses by day `5.48` or earlier. Independent simulations
estimated a `0.972%` mean horizon-wide false-alarm rate for a requested 1%
level. It also identified temporal-shape departures in three sequences whose
final totals were covered.

These are retrospective model-diagnostic events. A rate-change alarm does not
distinguish secondary rupture, a new decay exponent, catalog outage,
completeness change, or other causes, and it is not a damaging-earthquake
prediction.

## Relationship to established forecasting practice

This project does not claim state-of-the-art aftershock forecasting. It has not
run a comprehensive matched-data comparison against ETAS, Reasenberg–Jones,
STEP, operational earthquake forecasting systems, or a prospective CSEP-style
evaluation. The exponential comparison in the Ridgecrest lab is a deliberately
simple dynamics contrast, not a sufficient seismological benchmark.

The strongest contribution so far is the auditable research workflow: explicit
forecast boundaries, whole-earthquake validation, preservation of negative
results, count-space rejection of harmful complexity, analytical software
checks, and a portable model-diagnostic kernel. Accuracy and calibration need
external comparison before the hierarchy itself should be considered a
practitioner model.

## Experiment map

The reports are cumulative; each one preserves its own evidence boundary.

| Report | Practitioner question | Result |
|---|---|---|
| [12 — Ridgecrest relaxation](reports/12_ridgecrest_aftershocks.md) | Power law or exponential decay? | Omori dominates the held-out exponential baseline. |
| [13 — Event excitation](reports/13_aftershock_excitation.md) | Do prior events improve the next interval? | Small aggregate gain; weak interval-level consistency. |
| [14 — Spatial memory](reports/14_aftershock_spatial_memory.md) | Does causal regional state predict location? | Training gain reverses on holdout. |
| [15 — Law transfer](reports/15_aftershock_law_transfer.md) | Does one decay shape transfer? | Wins 5 of 8, with severe opposite-direction failures. |
| [16 — Hierarchical transfer](reports/16_hierarchical_aftershock_transfer.md) | Can targets escape a population shape safely? | Partial pooling substantially improves the eight-sequence benchmark. |
| [17 — Population metadata](reports/17_aftershock_population_meta_prediction.md) | Can first-day features predict decay personality? | The compact metadata shortcut fails overall. |
| [18 — Expanded hierarchy and guard](reports/18_expanded_aftershock_hierarchy_and_count_guard.md) | Does pooling survive expansion, and can unsafe metadata be rejected? | Pooling wins 7 of 12; count-space validation rejects metadata. |
| [19 — Detector audit](reports/19_change_detector_contract_audit.md) | Is the existing change detector operationally interpretable? | No; controlled probes expose contract and calibration gaps. |
| [20 — Calibrated sequential monitor](reports/20_calibrated_sequential_regime_monitor.md) | Can sustained forecast failure be detected causally? | Yes under an explicit fixed-Poisson null. |
| [21 — Portable export](reports/21_portable_sequential_monitor_export.md) | What is responsible to publish? | The generic monitor, not a trained earthquake oracle. |
| [22 — KinoPulse release validation](reports/22_release_validation_2026071512.md) | Are the new count and point-process APIs analytically sound? | Count/fitting paths pass; history-dependent compensators have a boundary bug. |

For a short scientific reading path, use reports 12, 18, 20, 21, and 22. Read
reports 13, 14, 17, and 19 before proposing extra model complexity; they record
important ways plausible ideas failed.

## Reproduction

Use the repository `.venv`. The current results were last reproduced with
KinoPulse `0.1.0.dev2026071512`. Confirm the active installation before a long
run:

```powershell
.\.venv\Scripts\python.exe -c "from importlib.metadata import version; print(version('kinopulse'))"
```

The repository currently assumes a prepared local `.venv` and does not commit
a complete environment lock file. A public replicator should record Python,
PyTorch, KinoPulse, SciPy, NumPy, and plotting-library versions in addition to
the repository commit. The portable monitor provenance records its own relevant
runtime versions separately.

The fetch steps require internet access and query USGS. Generated CSV/JSON data
are intentionally not committed; the reports record the source queries and
digests. Figures are committed for review.

### Single-sequence reproduction

```powershell
.\.venv\Scripts\python.exe fetch_ridgecrest.py
.\.venv\Scripts\python.exe aftershock_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_aftershock_lab -v
```

This is the smallest end-to-end entry point. Inspect
`artifacts/aftershock_lab.png`, `artifacts/aftershock_analysis.json`, and report
12 together.

### Eight-sequence transfer progression

```powershell
.\.venv\Scripts\python.exe fetch_aftershock_benchmark.py
.\.venv\Scripts\python.exe aftershock_transfer_lab.py
.\.venv\Scripts\python.exe aftershock_hierarchy_lab.py
```

This progression makes the failure of a universal shape and the benefit of
partial pooling easier to understand before moving to the expanded screen.

### Population reproduction

```powershell
.\.venv\Scripts\python.exe fetch_aftershock_population.py
.\.venv\Scripts\python.exe aftershock_meta_lab.py
.\.venv\Scripts\python.exe aftershock_population_hierarchy_lab.py
.\.venv\Scripts\python.exe aftershock_count_guard_lab.py
.\.venv\Scripts\python.exe change_detector_lab.py
.\.venv\Scripts\python.exe sequential_regime_lab.py
```

Run the complete regression suite afterward:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The suite contains leakage-boundary tests, causal feature checks, synthetic
parameter recovery, exported-artifact verification, and analytical release
oracles. Expected failures are documented library-boundary probes rather than
silently skipped evidence.

### Reproduce the portable monitor

```powershell
.\.venv\Scripts\python.exe export_sequential_monitor.py
.\.venv\Scripts\python.exe -m unittest tests.test_export_sequential_monitor -v
```

Re-exporting updates binary and provenance evidence. Do not substitute a newly
generated binary into another project without checking its hash, model card,
KinoPulse/PyTorch versions, and licensing status.

## Interpreting the outputs

- **Poisson deviance** is a relative count-forecast score. Lower is better for
  the same observations, but its absolute value is not a calibrated hazard
  probability.
- **Sequence wins** give each earthquake equal voting weight; summed deviance
  emphasizes productive catalogs. Both are reported because they answer
  different questions.
- **Predictive total coverage** checks one aggregate property. A covered total
  can conceal a badly wrong temporal shape.
- **Bin coverage** depends strongly on the assumed predictive distribution and
  dependence structure.
- **Monitor threshold crossings** mean that a sustained multiplicative tail is
  surprising under the specified null. They do not identify a physical cause.
- **Change-bin estimates** are on logarithmic time bins; bin delay is not equal
  clock-time delay.

## Practitioner adaptation checklist

Do not copy the radius, magnitude cutoff, first usable time, binning, population
screen, or monitor threshold without re-establishing them for the new setting.

1. Define the forecast use case and decision boundary before looking at target
   outcomes.
2. Establish magnitude of completeness through time and space; a nominal
   catalog cutoff is not a completeness analysis.
3. Define mainshock association, overlapping-sequence handling, spatial
   geometry, and background estimation with domain justification.
4. Freeze calibration, evaluation, and any embargo windows. Keep entire
   earthquakes together in validation.
5. Preserve exact catalog query, retrieval time, revision policy, event IDs,
   and content digest.
6. Compare against transparent baselines and retain negative results.
7. Select hyperparameters using the final observable forecast objective, not a
   convenient latent-parameter surrogate.
8. Propagate parameter, population, catalog, and completeness uncertainty into
   predictive counts.
9. Calibrate monitoring across the complete horizon and scan domain with an
   independent validation simulation set.
10. Perform genuinely external geographic and temporal evaluation before any
    operational interpretation.
11. Add expert review, audit logs, failure handling, version pinning, and
    governance for any consequential deployment.

## Known technical boundaries

- KinoPulse `TemporalPointProcess` in the tested release drops the event at an
  integration interval's left boundary from the following history-dependent
  compensator. Do not rely on it for Hawkes/ETAS-style likelihoods until the
  [analytical regression](reports/22_release_validation_2026071512.md) passes.
- The current population model is empirical-Bayes-style penalized estimation,
  not a fully specified posterior over seismicity.
- Predictive sampling does not yet propagate every source of fit and catalog
  uncertainty.
- The sequential reference null assumes conditionally independent Poisson
  bins with fixed expectations.
- The spatial and excitation labs are research counterexamples, not validated
  modules to compose into a larger model.
- No prospective or blind external earthquake population has yet evaluated
  the complete hierarchy-plus-monitor workflow.

## A responsible next study

The most useful next step is not a larger neural model. It is a prospective or
historically frozen external benchmark with catalog-completeness modeling,
rupture geometry, and a full predictive null. The partial-pooling baseline
should remain unchanged until a candidate extension wins whole-earthquake
count-space validation and improves the known high-tail and collapse failure
modes without degrading the rest of the population.

If you build on this work, report the exact catalog revision, selection rules,
forecast boundary, null simulator, KinoPulse version, and repository commit.
That provenance is part of the scientific result, not administrative detail.
