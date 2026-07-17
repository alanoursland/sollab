# Can the wind mechanism cross a reanalysis boundary?

## Question

Report 49 stopped when NCEP/NCAR Reanalysis 1 production ended. NOAA now
identifies CORe as its continuing climate-monitoring reanalysis and includes it
in the same WRIT regional time-series tool. Can an observation bridge defined
before viewing its later overlap preserve both the old wind index and the
three-month heat-recharge impulse?

This is a measurement-continuity experiment, not a new ENSO model search. A
high correlation between two reanalyses is not sufficient: the downstream
report-49 model must also keep its advantage.

## Identical measurement request

`fetch_enso_core_wind.py` asks NOAA WRIT for the same quantity used in report
49, changing only the dataset:

- CORe rather than NCEP/NCAR R1;
- 850 mb zonal-wind anomaly;
- 5°S–5°N, 140°E–170°W;
- monthly values; and
- the 1981–2010 climatology.

WRIT produces a temporary CSV link. The fetcher discovers and downloads that
link but records the reproducible query URL, not the expiring artifact URL. It
also rejects a changed variable/region header. The frozen snapshot has 918
valid values from January 1950 through June 2026, SHA-256
`52dd9a3889eff365dc5d85614380f82474a26957ee65037bc68eab2bf0c0577c`.

NOAA describes CORe as a 1950–present reanalysis designed to replace the
real-time R1 extension for climate monitoring. The public comparison product
is on a 2.5° grid and largely avoids satellite assimilation except atmospheric
motion vectors. Those choices make continuity plausible, not automatic.

## Frozen chronology

| Role | Overlap years | Use |
|---|---:|---|
| Bridge training | 1979–2009 | estimate mappings |
| Bridge validation | 2010–2017 | choose mapping complexity |
| Bridge test | 2018–2025 | first later comparison of the two instruments |

The candidates are identity, additive bias, and affine mappings fit with
KinoPulse `RidgeSolver` at penalties from 0 through 10. Selection minimizes the
mean of eight whole-year bridge RMSE values. The old report-49 heat model and
its three wind lags are frozen; no heat-model coefficient is tuned here.

## Selection

| Mapping | 2010–2017 mean annual RMSE |
|---|---:|
| Identity | 0.6917 m/s |
| Additive bias | 0.7150 m/s |
| Affine, no penalty | **0.6780 m/s** |
| Best penalized affine | 0.6780 m/s |

The selected training-only map is

```text
R1-scale wind = 0.0619 + 0.8729 × CORe wind
```

The distinction among affine penalties is negligible. The scientifically
important choice is rescaling rather than the exact regularization strength.

## Untouched 2018–2025 bridge test

| Diagnostic | Result |
|---|---:|
| Paired months | 95 |
| Correlation | 0.9812 |
| RMSE | 0.5244 m/s |
| Mean error | +0.2987 m/s |
| Scale ratio | 1.0513 |
| Sign agreement | 93.7% |

The bridge is strong but visibly imperfect. Its persistent positive mean error
shows that one stationary affine map does not remove all changing
observation-system differences. That residual is retained in the evidence
rather than corrected after opening the test.

## Does the physical impulse survive?

Applying the frozen report-49 kernel to R1 and bridged CORe gives:

| Impulse diagnostic | Result |
|---|---:|
| Correlation | 0.9657 |
| RMSE | 0.0400°C |
| Sign agreement | 94.8% |

The more consequential downstream test is next-month upper-ocean heat:

| Input to frozen heat law | 2018–2025 RMSE | Change correlation | Direction accuracy |
|---|---:|---:|---:|
| State only | 0.3139°C | 0.261 | 69.8% |
| Original R1 wind | **0.2837°C** | **0.487** | 71.9% |
| Bridged CORe wind | 0.2860°C | 0.477 | **72.9%** |

The bridge retains 92.5% of R1 wind's RMSE gain over the state model. It passes
all four frozen continuation checks: wind correlation at least 0.95, scale
ratio within 0.9–1.1, impulse correlation at least 0.90, and at least half of
the downstream heat gain retained.

That is enough to continue measuring this mechanism with CORe. It is not
evidence that CORe and R1 are generally interchangeable.

## The opened 2026 replay still fails

After the bridge passed, its chosen affine family was refit on all completed
R1/CORe overlap through November 2025. The frozen heat model was then replayed
over January–June 2026, whose heat outcomes had already been opened in report
48.

| Model | Six-month heat RMSE |
|---|---:|
| State only | **0.3742°C** |
| Bridged CORe wind | 0.3923°C |

Wind helps February and approaches the May state, but it misses much of the
March–April rise and predicts too much June cooling. Crossing the archive
boundary does not explain the extraordinary 2026 heat buildup. That negative
result prevents a measurement-engineering success from becoming a physical
success story it did not earn.

## A prospective July record

The frozen source snapshots contain June 2026 MEI, heat, and CORe wind but no
July heat outcome. This creates one genuinely prospective target:

```text
issued after data through June 2026
June heat anomaly                 2.140°C
bridged June CORe wind            3.465 m/s
state-only July prediction        1.960°C
wind-memory July prediction       2.215°C
wind-memory predicted change     +0.075°C
```

An 80% KinoPulse split-conformal band calibrated on each 2018–2025 year's
maximum monthly error is `[0.749, 3.680]°C`. With only eight groups, the
finite-sample rank is the largest calibration score, so the interval is
appropriately enormous. It is an honest warning that the point-model
disagreement is more informative than either point estimate's precision.

The July value is a dated research prediction, not an operational ENSO
forecast. It predicts one regional upper-ocean heat index, carries reused and
small-sample calibration, and has no public-safety interpretation. It must not
be revised after the July outcome arrives.

## What KinoPulse contributed

- `RidgeSolver` fits the affine observation map and frozen heat laws;
- the report-49 causal dynamical feature contract carries through unchanged;
- `SplitConformalIntervalCalibrator` makes the tiny grouped uncertainty sample
  explicit through its conservative finite-sample rank; and
- the continuation checks turn an archive splice into a falsifiable contract.

No new KinoPulse gap was required. The earlier multi-output ridge residual bug
remains documented separately; this lab uses scalar fits.

## Reproduction

This report uses KinoPulse `0.1.0.dev2026071623`.

```powershell
.\.venv\Scripts\python.exe fetch_meiv2.py
.\.venv\Scripts\python.exe fetch_enso_heat_content.py
.\.venv\Scripts\python.exe fetch_enso_wind.py
.\.venv\Scripts\python.exe fetch_enso_core_wind.py
.\.venv\Scripts\python.exe enso_core_bridge_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_fetch_enso_core_wind tests.test_enso_core_bridge_lab -v
```

The ignored evidence is `artifacts/enso_core_bridge_analysis.json`; the tracked
figure is `artifacts/enso_core_bridge_lab.png`.
