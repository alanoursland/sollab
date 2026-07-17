# Earthquake Program Synthesis and Stopping Point

## Decision

Pause the earthquake research line here.

The project has reached the boundary of what its frozen public USGS catalogs
can answer honestly. Further analysis of the same rows could produce more
statistics, but it cannot separate physical aftershock dynamics from
time-varying detection, magnitude revision, network processing, and catalog
composition. That distinction now controls the main scientific question.

This is a successful stopping point, not an abandoned experiment. The work
produced reusable software, several real empirical results, important negative
results, and increasingly precise claim boundaries. It also discovered the
data and library capabilities required for a stronger second program.

## What survived

### Reusable software result

The strongest portable artifact is the generic strict-TorchScript sequential
Poisson regime monitor in `models/`. It has explicit input contracts,
provenance, saved-artifact validation, and no trained earthquake parameters.
It is useful wherever a researcher already has expected count bins and a
scientifically calibrated threshold.

The monitor is not an earthquake forecast or public-safety alarm. Its value is
the reusable causal scan implementation and the evidence discipline around its
export.

### Empirical modeling result

Across the western development population, robust partial pooling is clearly
better than a universal shared decay shape and safer than an unguarded metadata
correction. Across the original 12-sequence population it wins seven folds and
preserves explicit sequence-level failures.

The frozen hierarchy also improves point-deviance ranking across the 37-target
Alaska cohort. That is real end-to-end empirical transfer for the downloaded
catalog pipeline. It is not evidence of calibrated uncertainty: nominal 80%
totals cover only 51.4% before later corrective experiments.

### Scientific diagnostic result

Reported magnitude is not an exchangeable mark on a common aftershock clock.
High magnitudes are strongly front-loaded in western and Alaska sequences. The
effect survives conditioning on earthquake, reporting network, and magnitude
type. This is the clearest scientific finding late in the program.

It establishes a time-dependent observation channel or physical mark process;
it does not identify which. That distinction matters because changing the
magnitude floor changes both fitted population shape and alarm identity.

### Research-method result

The most durable contribution is the audit sequence itself:

1. freeze whole-earthquake groups rather than split dependent rows;
2. keep hyperparameter selection inside nested group boundaries;
3. propagate population uncertainty into complete future paths;
4. repeat stochastic threshold calibration;
5. audit target isolation outside rectangular query boundaries;
6. audit realized measurement support rather than trust requested filters;
7. rerun conclusions across defensible observation policies; and
8. test whether recorded provenance explains the sensitivity.

Each audit was capable of weakening the attractive result. That is exactly what
a public scientific playground should permit.

## What did not survive

### A universal aftershock law

One transferred Omori shape fails in opposite directions on different
earthquakes. Hierarchical adaptation helps, but no universal curve is supported.

### Metadata-based decay prediction

Mainshock metadata and first-day features do not safely predict target decay
personality. Nested count-space validation selects zero trust in the learned
correction.

### Nominal predictive calibration

Western population intervals are too narrow in Alaska. Chronological and
prequential repairs improve coverage only by sacrificing substantial sharpness.
Simple abstention features do not reliably identify unsafe forecasts in
advance.

### A fixed-Poisson operational alarm

The initially calibrated scan alarms on 64.9% of Alaska sequences. Its
simulation calibration is numerically correct and its scientific null is too
narrow. A hierarchy-predictive null reduces the alarm flood, but detection
becomes late and insensitive.

### Magnitude-invariant alarm identities

The rare M2.5 Alaska alarms reproduce across Monte Carlo batches but not across
reported-magnitude floors. At M3, three original targets remain eligible and
quiet, one becomes ineligible, and two different Fox Islands sequences alarm.
The detector found catalog-channel departures, not an invariant earthquake
state.

### A second-geography replication

The sole Japan alarm belongs to an invalid target. An equal-M6.1 predecessor
occurred 0.98 days earlier and 32.8 km away, just outside the candidate
rectangle. Once removed, all eight isolated Japan targets are quiet.

The Japan catalogs are also effectively global M4+ data while the western
population is dominated by regional M2.5--3 rows. Only three western sequences
remain eligible at M4. The experiment is a useful software/catalog stress test,
not matched-support geographic replication.

## Why this is the stopping point

Five independent stopping conditions are now met.

### 1. The unresolved variable is not in the data

The public rows do not contain a defensible time-varying detection probability,
station availability history, waveform-overlap measure, or complete revision
history. Recorded network and magnitude type do not explain away the effect.
No additional regression on the same fields can recover missing observation
mechanics.

### 2. Common-support populations are too small

M4 harmonization leaves three western development sequences. Fitting a new
hierarchy to those outcome-selected survivors would produce unstable numbers,
not credible validation.

### 3. The external data are no longer untouched

Alaska and Japan have now informed model criticism, null design, consensus
rules, floor selection, and mechanism hypotheses. They remain useful for
retrospective diagnostics but cannot serve as pristine prospective evidence
for another revised alarm.

### 4. The missing model is structural

A convincing next model needs marked or multitype temporal point processes and
probably an explicit observation layer. KinoPulse currently supplies scalar
temporal point-process tools. The required marked-process contract is recorded
in `kinopulse_gaps/` rather than improvised as another earthquake-only loop.

### 5. External scientific comparison is still absent

The hierarchy has not been benchmarked against ETAS, Reasenberg--Jones, STEP,
operational earthquake forecasting systems, or a prospective CSEP-style test.
More internal refinement before that comparison would optimize the playground
against itself.

## Gates for reopening the program

The earthquake line becomes worth reopening when at least one complete path is
available.

### Matched-catalog path

- comparable regional catalogs for development and external geographies;
- documented magnitude harmonization;
- sequence-specific, time-varying completeness estimates; and
- enough M4+ western earthquakes to build and hold out populations separately.

### Observation-model path

- a marked or multitype point-process implementation;
- explicit latent-event versus reported-event semantics;
- context-conditioned mark likelihoods;
- validation on synthetic thinning and recovery fixtures; and
- uncertainty propagation through the forecast and monitor.

### Prospective-validation path

- a protocol and thresholds frozen before new earthquakes occur;
- immutable code and artifact digests;
- outcome-maturity and catalog-revision rules;
- comparison against established baselines; and
- a predefined reporting policy that publishes quiet and failed cases.

A new release alone is not enough. The program should reopen around a new data
or validation capability, not merely a more flexible optimizer.

## Guidance for public release

Publish the repository as an exploratory dynamics and scientific-software
study. Lead with the practitioner guide and preserve reports 13, 14, 17, 19,
27, 32, and 35--37; the negative and corrective results are essential context.

Avoid names such as "aftershock alarm" or "earthquake predictor" for the
repository as a whole. A responsible description is:

> A reproducible KinoPulse playground for aftershock-rate modeling, sequential
> forecast diagnostics, and observation-system sensitivity using frozen public
> earthquake catalogs.

The portable monitor should retain its model card and explicit statement that
users must supply their own forecast and calibrated threshold. Before inviting
reuse, the repository still needs a license chosen by its owner.

## Final position

The earthquake work did not produce a state-of-the-art earthquake forecast.
It produced something I value more than a fragile leaderboard result: a model
that was allowed to become less impressive as the evidence became better.

The honest endpoint is:

- partial pooling is useful for these downloaded count sequences;
- predictive uncertainty and external calibration remain inadequate;
- rare alarms are catalog-channel specific;
- magnitude-time coupling is real in the reported rows;
- its physical versus observational origin is unresolved; and
- stronger progress now requires new information, not more analysis of the
  same catalog.

That is where this research line should pause.
