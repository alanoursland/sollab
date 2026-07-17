# ENSO as a scalar oscillator or switching process

## Question

Does a threshold-switched scalar model forecast NOAA's Multivariate ENSO Index
better than an ordinary delayed oscillator, or does the extra regime story
merely fit a short historical sample?

This first ENSO experiment deliberately uses only the index itself. It is a
small falsification lab for model structure, not an attempt to compete with
operational forecasts that ingest subsurface ocean heat, winds, and spatial
fields.

## Data and measurement contract

`fetch_meiv2.py` retrieves NOAA PSL's public MEI.v2 ASCII series and records the
source URL, documentation URL, retrieval time, byte count, and SHA-256. The
snapshot used here contains 570 valid values from January 1979 through June
2026; its SHA-256 is
`4a57479eb5bcdb508cc1ea339596739555a0192bb2b2b19c64858037ae435606`.

MEI.v2 is not twelve independent monthly measurements per year. Each published
value summarizes an overlapping bimonthly period, placed in a monthly slot;
January represents December–January. Adjacent-value persistence is therefore
partly constructed by the measurement itself. Every result below is about the
published scalar index, not the full coupled ocean–atmosphere state.

The experiment stops at December 2025 even though the downloaded source has six
2026 slots. That boundary was fixed before model selection so every test target
year is complete.

## Chronology and information boundary

| Role | Target years | Use |
|---|---:|---|
| Initial fit | 1979–2009 | First validation forecast |
| Expanding validation | 2010–2017 | Select family and regularization |
| Final refit | 1979–2017 | Fit the frozen family specifications |
| Untouched test | 2018–2025 | Compare preselected families once |

For each target year, the model observes November and December of the preceding
year, then recursively forecasts January through December. The model never
receives an observed value inside that twelve-month path. Validation refits on
all earlier target years before forecasting the next one.

KinoPulse's `ExpandingWindowGroupSplit` supplies the eight chronological
validation folds, `cross_validate` evaluates every candidate with visible
failure policy, and `RidgeSolver` fits the dynamical laws. The independent unit
for uncertainty is a complete target year—not one of the 96 correlated monthly
errors in the holdout.

## Predeclared model families

- **Persistence:** every month equals the preceding December.
- **Monthly climatology:** each target month equals its historical training
  mean.
- **Delayed oscillator:** the next value is linear in the last two values plus
  annual sine and cosine terms.
- **Weakly nonlinear oscillator:** the delayed oscillator plus squared and
  cubed current-state terms.
- **Threshold switching:** three separately fitted delayed oscillators selected
  by whether the recursively predicted current state is cold, neutral, or warm.

Ridge penalties are selected from `0.001, 0.01, 0.1, 1.0` for the two shared
oscillators. Switching considers thresholds `0.3, 0.5, 0.7` and penalties
`0.01, 0.1, 1.0`. The familiar ±0.5 boundary is used only for descriptive
warm/neutral/cold accuracy; it does not constrain the selected switching guard.

## Validation selection

| Family | Selected specification | Mean annual-path RMSE, 2010–2017 |
|---|---|---:|
| Persistence | fixed | 1.0223 |
| Monthly climatology | fixed | 0.9463 |
| Delayed oscillator | ridge `0.001` | 0.7801 |
| Weakly nonlinear | ridge `1.0` | 0.7845 |
| Threshold switching | ridge `0.01`, guard `±0.3` | **0.6950** |

Threshold switching therefore wins the frozen selection. The nonlinear terms
do not improve on the linear delayed oscillator during validation.

## Untouched 2018–2025 result

| Family | RMSE | Skill vs persistence | ±0.5 regime accuracy |
|---|---:|---:|---:|
| Persistence | 0.9167 | 0.0% | **64.6%** |
| Monthly climatology | 0.9428 | −2.8% | 30.2% |
| Delayed oscillator | 0.7705 | 16.0% | 46.9% |
| Weakly nonlinear | 0.7707 | 15.9% | 46.9% |
| Threshold switching | **0.7496** | **18.2%** | 50.0% |

The selected model retains the best aggregate RMSE, but not by much. It is only
2.7% better than the delayed oscillator. Its regime labels are also less
accurate than persistence, so lower continuous error must not be translated
into a stronger El Niño/La Niña classification claim.

The gain over persistence is heterogeneous. Switching wins only 4/8 target
years: it helps substantially in 2018, 2023, and 2024, but loses badly in 2021,
2022, and 2025. Against the delayed oscillator it wins 5/8 years.

## Whole-year uncertainty

I resample complete forecast years and also enumerate all `2^8` paired sign
randomizations of the annual mean-squared-error differences.

| Comparison | Relative skill | 95% year-bootstrap interval | Wins | One-sided paired randomization p |
|---|---:|---:|---:|---:|
| Switching vs persistence | 18.2% | −44.7% to 42.2% | 4/8 | 0.219 |
| Switching vs delayed oscillator | 2.7% | −6.7% to 12.3% | 5/8 | 0.281 |

Eight years give low power and unstable tails; these are diagnostics rather
than asymptotic certificates. They reject the tempting strong interpretation.
The experiment does not distinguish threshold switching from a linear delayed
oscillator, and it does not establish that either will outperform persistence
in a new climate regime.

## What I learned

1. A two-lag scalar dynamical state is useful enough to beat both simple
   baselines in aggregate here, especially at longer forecast leads.
2. Cubic state terms earn no measurable improvement.
3. Switching survives selection and the point estimate, but its test advantage
   over the linear oscillator is tiny relative to whole-year uncertainty.
4. Continuous RMSE and ENSO-state classification answer different questions;
   the lowest-RMSE model is not the best regime classifier.
5. Overlapping bimonthly construction makes short-lead scalar skill easier and
   should remain visible in every follow-up.

## Limits and next move

- The model has no thermocline depth, equatorial wind, subsurface temperature,
  or spatial information. It cannot diagnose the physical delayed-feedback
  mechanism from MEI.v2 alone.
- Annual December resets create eight comparable forecast paths but do not test
  arbitrary initialization months or the spring predictability barrier.
- Model comparison spans only eight validation and eight test years; climate
  nonstationarity makes exchangeability doubtful even at the year level.
- NOAA may revise the live source. The exact hash is preserved, but downloaded
  data are intentionally ignored by the repository.
- These are retrospective standardized-index forecasts, not an operational
  climate product and not state of the art.

I would not tune more guards on 2018–2025. The next worthwhile experiment is
physically richer and still chronological: add public equatorial Pacific wind
and ocean-heat-content predictors, freeze the scalar models unchanged as
baselines, and test forecasts initialized in each season. That could reveal
whether a genuine slow state resolves the long-lead failures; another scalar
threshold sweep cannot.

## Reproduction

This report uses KinoPulse `0.1.0.dev2026071623`.

```powershell
.\.venv\Scripts\python.exe fetch_meiv2.py
.\.venv\Scripts\python.exe enso_oscillator_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_fetch_meiv2 tests.test_enso_oscillator_lab -v
```

The ignored evidence is `artifacts/enso_oscillator_analysis.json`; the tracked
figure is `artifacts/enso_oscillator_lab.png`.
