# Causal storm nowcasts with group-conformal recovery bands

## Question

Can the compact Dst response model become honest about uncertainty without
pretending its correlated hourly errors are independent? Can information known
before recovery identify storms for which its band should not be issued?

This experiment changes the target from the recursive response rollouts in
reports 43–44 to a genuinely causal one-hour prediction. It tests the new
KinoPulse grouped conformal and selective-prediction contracts on complete
storm paths.

## Information contract

At hour `t`, the model predicts `Dst[t+1]` from:

- `Dst[t]`;
- positive solar-wind electric field at `t`; and
- dynamic-pressure change from `t-1` to `t`.

No future pressure value enters the design. Missing electric field and pressure
are carried forward from the most recent valid observation for at most 24
hours. This fill is causal: future observations never backfill earlier gaps.
Dst is never filled.

The storm centers remain retrospectively selected local Dst minima. Therefore
the result evaluates one-hour prediction within known storm windows; it is not
prospective storm detection.

## Chronology

| Role | Years | Storms |
|---|---:|---:|
| Ridge fit | 2010–2015 | hourly population rows |
| Group-conformal calibration | 2016–2018 | 5 |
| Untouched chronological test | 2019–2025 | 20 |

Bounded forward-fill supplies 810 electric-field hours and 1,324 pressure
hours across the 140,256-hour archive. All 43 Dst-selected storms have a valid
causal prediction path after this policy. The data manifest is unchanged from
reports 43–44.

## Why the calibration unit is a storm

There are 168 post-minimum hourly errors in each recovery window, but they are
not 168 independent calibration observations. Each storm contributes one
score: its maximum absolute post-minimum one-hour error. A conformal radius
therefore covers a storm only when every recovery-hour error lies inside the
band.

`SplitConformalIntervalCalibrator` is fitted at nominal 80% group coverage with
five independent calibration storms. The finite-sample rank is
`ceil((5 + 1) × 0.8) = 5`, so the supported correction is the largest
calibration score: `33.720 nT`.

## Result

The fixed radius covers 16/20 later storms, exactly 80%. A prequential replay
then recalibrates each test storm using only earlier storms whose 168-hour
recovery outcomes have matured.

| Metric | Result |
|---|---:|
| Simultaneously covered test storms | 16/20 (80.0%) |
| Marginal covered recovery hours | 99.494% |
| Mean prequential radius | 33.227 nT |
| Radius range | 24.516–33.720 nT |

The enormous difference between 80% storm coverage and 99.49% hourly coverage
is the central measurement result. Reporting only the latter would make four
complete-path failures almost invisible.

The misses are:

| Storm minimum | Dst minimum | Known pre-min max error | Recovery max error | Issued radius |
|---|---:|---:|---:|---:|
| 2023-04-24 | -213 nT | 30.50 nT | 38.93 nT | 33.72 nT |
| 2024-05-11 | -406 nT | 86.11 nT | 68.81 nT | 24.52 nT |
| 2024-10-11 | -333 nT | 58.72 nT | 61.05 nT | 33.72 nT |
| 2025-11-12 | -217 nT | 80.82 nT | 42.75 nT | 33.06 nT |

The May 2024 extreme is especially instructive. Prequential calibration had
narrowed after quieter outcomes immediately before a regime in which the
model's one-hour errors became much larger. A fixed 33.72 nT radius would still
miss it, but the narrowed 24.52 nT band makes the failure more confident.

## Selective prediction

At the selected minimum, errors accumulated over the prior 48 hours are known.
Their maximum absolute value is used as the only abstention score. It has
Spearman correlation `0.484` with the later recovery maximum (`p = 0.0305`) in
the 20 test storms. This is descriptive evidence, not a calibrated effect.

All thresholds are frozen from the five calibration storms before test:

| Policy | Threshold | Retained | Issued coverage | Misses caught by abstention | Correct bands rejected |
|---|---:|---:|---:|---:|---:|
| Calibration median | 20.40 nT | 5/20 | 100% | 4/4 | 11 |
| Calibration 80th rank | 22.40 nT | 5/20 | 100% | 4/4 | 11 |
| Calibration maximum | 33.56 nT | 12/20 | 91.7% | 3/4 | 5 |

The loosest rule is directionally useful but expensive. It catches the May and
October 2024 extremes and the November 2025 miss, while rejecting five correct
bands. The April 2023 miss has a benign-looking pre-error and survives every
tested threshold. This is a triage signal, not a reliable failure detector.

KinoPulse's `SelectivePredictionAudit` preserves the distinction between
ineligible, issued, and abstained groups; it also records that the thresholds
are prospective rather than a test-set sweep. Its history validation confirms
that every issue decision uses only matured earlier storm outcomes.

## What survived

1. Grouping by storm rather than hour exposes four failures hidden by 99.49%
   marginal coverage.
2. KinoPulse's finite-sample rank makes the small calibration support visible:
   80% is supported by five groups, but only at the maximum calibration error.
3. Prequential calibration achieves the nominal fraction on this test set but
   can narrow immediately before an extreme regime.
4. Pre-minimum error contains some useful warning information, but useful
   abstention costs substantial retention and still misses one failure.
5. Causal forward-fill removes the future-information flaw of linear
   interpolation while retaining all selected storms.

## Limitations and stopping rule

- Twenty test storms cannot establish a durable coverage guarantee.
- Split-conformal validity relies on independent exchangeable groups; solar
  cycle, instrument coverage, and changing storm severity make that assumption
  doubtful across this chronology.
- The 24-hour forward-fill policy is causal but may replace rapidly changing
  forcing with stale measurements.
- The one-hour model is teacher-forced with observed current Dst. It is not a
  168-hour autonomous forecast.
- Storm centers and the minimum-time decision point are known retrospectively.
- The abstention score and recovery maximum are both model-error summaries and
  may share storm-severity confounding.
- A ±33 nT simultaneous band is scientifically informative but may be too wide
  for operational decisions.

I would stop before tuning more thresholds on these 20 storms. A serious next
step would freeze the model, causal fill policy, 33.72 nT band, and 33.56 nT
abstention threshold prospectively on newly arriving storms—or validate them on
an independent high-resolution SYM-H archive with explicit data-latency rules.

## Reproduction

This report uses KinoPulse `0.1.0.dev2026071623`.

```powershell
.\.venv\Scripts\python.exe storm_conformal_nowcast_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_storm_conformal_nowcast_lab -v
```

The ignored evidence is `artifacts/storm_conformal_nowcast.json`; the tracked
figure is `artifacts/storm_conformal_nowcast.png`.
