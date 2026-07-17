# ENSO Dynamics Research Guide

This guide is the entry point for climate researchers reviewing the ENSO
experiments in this KinoPulse playground. The work is a compact, reproducible
study of model structure, ocean recharge, low-level wind memory, and
observation-system continuity. It is not an operational ENSO forecast system.

## Bottom line

Four results survive:

1. A scalar switching model has the lowest later MEI.v2 error, but its small
   advantage over a delayed oscillator is not distinguishable with eight
   complete test years.
2. A coupled MEI/upper-ocean-heat model learns the expected recharge-oscillator
   signs, but it loses the original model-selection contest and badly
   underpredicts the early-2026 heat surge.
3. Three months of western tropical Pacific 850 mb wind improve later
   one-month heat-tendency RMSE over the matched no-wind state and form a stable
   transient impulse kernel within NCEP/NCAR R1.
4. A chronologically frozen bridge to NOAA CORe preserves 92.5% of that wind
   gain, but the continuing wind channel still does not explain the 2026 surge.

The active scientific object is now one frozen July 2026 upper-ocean heat
prediction. The branch should not be tuned again until that outcome is scored.

## Study map

| Report | Scientific role | Evidence status |
|---|---|---|
| [47: Oscillator or switching](reports/47_enso_oscillator_or_switching.md) | scalar MEI.v2 structure comparison | 2018–2025 opened once as the original test |
| [48: Recharge state](reports/48_enso_recharge_state.md) | add equatorial upper-300 m heat memory | later test reused; Jan–Jun 2026 first opened here |
| [49: Wind-driven recharge](reports/49_enso_wind_driven_recharge.md) | causal next-month heat tendency and transient wind kernel | later heat outcomes reused; wind mechanism selected on 2010–2017 |
| [50: CORe bridge](reports/50_enso_core_measurement_bridge.md) | cross the retired-R1 observation boundary | 2018–2025 first used for bridge testing; July 2026 is prospective |

The reports are cumulative. Report 50 does not replace report 49's R1 result;
it tests whether that result survives a particular change of instrument.

## Public data channels

| Channel | Role | Fetcher |
|---|---|---|
| NOAA MEI.v2 | scalar coupled ocean/atmosphere state | `fetch_meiv2.py` |
| NOAA GODAS equatorial heat content | upper-300 m recharge state, 160°E–80°W | `fetch_enso_heat_content.py` |
| NOAA NCEP/NCAR R1 850 mb zonal wind | retired historical wind mechanism, 5°S–5°N and 140°E–170°W | `fetch_enso_wind.py` |
| NOAA CORe 850 mb zonal wind | active continuation of the identical WRIT request | `fetch_enso_core_wind.py` |

Downloaded data and manifests are ignored so every researcher must retrieve
the public sources directly. Each fetcher writes retrieval time, source URLs,
coverage, byte count, SHA-256, interpretation, and missing-value counts. The
CORe fetcher records the reproducible WRIT query and deliberately excludes the
temporary generated CSV URL.

## Chronology and leakage controls

- Initial model training ends in 2009.
- Expanding 2010–2017 folds select structure and penalties.
- Complete years, not overlapping months, are the uncertainty units for annual
  forecasts and bridge comparisons.
- Heat at `t+1` never enters the feature vector used to predict it.
- Report 50 fits the R1-to-CORe bridge on 1979–2009, selects its family on
  2010–2017, and first tests it on 2018–2025.
- The continuing bridge is refit through the final paired R1 observation only
  after passing its frozen continuation contract.

The repository labels reused outcomes explicitly. A later experiment can add a
new mechanism, but it cannot make an already viewed year fresh again.

## Frozen July 2026 record

Using observations available through June 2026, report 50 records:

| Quantity | Frozen value |
|---|---:|
| June upper-ocean heat anomaly | 2.140°C |
| Bridged June CORe wind anomaly | 3.465 m/s |
| State-only July heat prediction | 1.960°C |
| Wind-memory July heat prediction | 2.215°C |
| Wind-memory predicted monthly change | +0.075°C |
| 80% whole-year group-conformal band | 0.749–3.680°C |

The interval uses each 2018–2025 year's maximum monthly absolute error. Eight
calibration groups force the finite-sample correction to their largest score.
The resulting width is a feature of honest small-sample uncertainty, not a
useful operational range.

### Scoring rule

When NOAA publishes the July heat-content value:

1. freeze a new source manifest before changing model code;
2. record the point error for both frozen predictions;
3. record whether the observed value lies in the frozen conformal band;
4. do not alter the bridge, heat model, or interval before those scores are
   written; and
5. call the result one prospective month, not prospective validation of the
   entire ENSO program.

## Reproduction

Use the repository environment:

```powershell
.\.venv\Scripts\python.exe fetch_meiv2.py
.\.venv\Scripts\python.exe enso_oscillator_lab.py
.\.venv\Scripts\python.exe fetch_enso_heat_content.py
.\.venv\Scripts\python.exe enso_recharge_lab.py
.\.venv\Scripts\python.exe fetch_enso_wind.py
.\.venv\Scripts\python.exe enso_wind_heat_lab.py
.\.venv\Scripts\python.exe fetch_enso_core_wind.py
.\.venv\Scripts\python.exe enso_core_bridge_lab.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Tracked PNGs provide convenient visual summaries. Generated JSON evidence and
downloaded observations remain local and can be regenerated from their
manifests and scripts.

## Appropriate and inappropriate uses

Useful pieces for researchers include the causal one-month row construction,
whole-year chronological validation, observation-bridge contract, physical
coefficient extraction, and grouped conformal calibration. The experiments can
serve as baselines or falsification targets for richer coupled models.

Do not use the repository to issue public El Niño/La Niña outlooks, infer a
causal atmospheric intervention, claim superiority to operational climate
centers, or treat the July point as a calibrated categorical ENSO forecast.
The models use compact regional summaries and omit much of the coupled Pacific
state, forecast initialization machinery, ensembles, and expert synthesis used
in operational practice.

## Current stopping point

Wait for the July score. After that, the most valuable expansion would be an
independent wind-stress product or a prospectively accumulated sequence of
monthly CORe/heat forecasts. More retrospective tuning on 2018–2026 would add
complexity without adding independent evidence.
