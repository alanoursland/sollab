# Does low-level wind drive the next ocean-heat change?

## Question

Report 48 found an interpretable recharge oscillator but also its central
failure: initialized in December 2025, it could not generate the extraordinary
upper-ocean heat buildup observed in early 2026. Does western tropical Pacific
low-level wind contain causal one-month information about that heat tendency?

This report deliberately narrows the target. It predicts
`heat[t+1] - heat[t]`; it does not add future wind to an annual MEI forecast.

## Wind channel

`fetch_enso_wind.py` freezes NOAA PSL's monthly 850 mb zonal-wind anomaly
averaged over 5°S–5°N, 140°E–170°W. Values are in m/s relative to the 1981–2010
climatology and come from NCEP/NCAR Reanalysis 1.

The snapshot has 935 valid values from January 1948 through November 2025. Its
SHA-256 is
`d75d0408304f992ac93eedb898566dcdfa9ff2e129addedbb4f63d7ad1a97e6b`.
December 2025 is explicitly missing rather than silently filled.

NCEP/NCAR Reanalysis 1 production ended in 2026. This is therefore a historical
mechanism archive, not a continuing forecast input. I do not manufacture 2026
wind or claim a fresh 2026 forcing test.

## Information and chronology

Each target month uses only values observed through the preceding month:

- current heat content and its most recent change;
- current MEI.v2;
- target-month sine and cosine;
- optionally current 850 mb wind; and
- optionally wind from one and two months earlier.

The target heat value never enters its own feature vector. Tests mutate a target
after feature construction and verify that its predictors are unchanged.

| Role | Target years | Status |
|---|---:|---|
| Initial training | 1979–2009 | first expanding forecast |
| Model selection | 2010–2017 | untouched by this mechanism experiment |
| Later comparison | 2018–2025 | reused exploratory evidence |

Heat outcomes were already viewed in report 48, so 2018–2025 is not labeled a
fresh holdout. Grouped uncertainty treats each complete target year as one unit,
not each of its twelve serially correlated monthly changes.

KinoPulse `ExpandingWindowGroupSplit` creates the chronological folds,
`cross_validate` selects family and penalty, and `RidgeSolver` fits each
one-month tendency law.

## Models

1. **Persistence:** predict no heat change.
2. **State:** heat, recent heat tendency, MEI, and season.
3. **State plus wind:** add current low-level wind.
4. **State plus wind memory:** add current wind and its preceding two months.

Ridge penalties are selected from `0.001, 0.01, 0.1, 1, 10`.

## Chronological selection

| Family | Selected penalty | 2010–2017 mean one-month RMSE |
|---|---:|---:|
| Persistence | fixed | 0.2934°C |
| State | 0.001 | 0.2290°C |
| State plus wind | 10.0 | 0.2215°C |
| State plus wind memory | 0.001 | **0.1956°C** |

Wind memory improves validation RMSE by 14.6% over the matched no-wind state.
This selection occurred before examining the later mechanism scores.

## Reused 2018–2025 evidence

| Family | RMSE | Change correlation | Direction accuracy |
|---|---:|---:|---:|
| Persistence | 0.3173°C | undefined | not applicable |
| State | 0.3139°C | 0.261 | 69.8% |
| State plus wind | 0.3024°C | 0.355 | 68.8% |
| State plus wind memory | **0.2837°C** | **0.487** | **71.9%** |

The selected wind-memory model improves RMSE by 9.6% over the no-wind state and
wins 7/8 whole target years. The year-bootstrap relative-skill interval is
5.7%–18.0%; the exact one-sided paired sign-randomization value is `0.0117`.

Against the current-wind-only model it wins all 8 years, with 6.2% relative
skill, a 1.7%–16.0% interval, and exact `p = 0.00391`. Against persistence it
wins 7/8 years, but the wider interval crosses zero.

These diagnostics are unusually consistent for this small archive, but they do
not restore prospective status to outcomes already opened by report 48.

## Large recharge months

The extreme threshold is the training-only 90th percentile of positive monthly
heat changes: `0.34°C`.

| Model | Actual extremes detected | Predictions issued | Precision | Recall |
|---|---:|---:|---:|---:|
| State | 0/11 | 2 | 0% | 0% |
| State plus current wind | 1/11 | 2 | 50% | 9.1% |
| State plus wind memory | **4/11** | 5 | **80%** | **36.4%** |

Wind history reveals some recharge bursts that the ocean/MEI state alone
misses. Most extremes remain undetected, so this is not an event alarm.

## What the wind kernel says

The selected physical coefficients for heat change per 1 m/s wind anomaly are:

```text
current month   +0.0954 °C
one month ago   -0.0568 °C
two months ago  -0.0316 °C
sum             +0.0069 °C
```

The near-zero sum matters. The model responds to a transient westerly pulse or
wind change, not a permanently elevated wind level. Current positive anomalies
raise next-month heat tendency; the preceding anomalies subtract most of that
effect.

The three wind lags are correlated (`0.719`–`0.739`), so individual
coefficients could have been unstable. They are not within the expanding audit:
fits ending from 2009 through 2016 keep the current coefficient between
`0.0954` and `0.0980`, lag one between `−0.0545` and `−0.0570`, and lag two
between `−0.0287` and `−0.0347`. That supports the impulse interpretation within
this archive, while not proving causality from reanalysis associations alone.

## What survived

1. Wind memory is selected chronologically, and its improvement transfers in
   direction and size to the later reused years.
2. The effect is not merely a contemporaneous ENSO proxy: two wind lags improve
   every later year over current wind alone.
3. The learned kernel is a stable transient response rather than a sustained
   forcing coefficient.
4. Wind history improves large-recharge precision but still misses 7/11
   extremes.
5. The result explains one-month heat tendency; it does not forecast the 2026
   heat surge from December 2025 because the historical wind archive ends.

## Stopping point and next move

I would stop using this NCEP/NCAR R1 index here. Its production has ended, and
splicing a new reanalysis after observing 2026 would create an unmeasured
observation-system change.

A responsible continuation would predefine the identical geographic average
in NOAA's replacement CORe reanalysis, quantify its overlap bias against R1,
freeze a bridge using only overlap years, and then ask whether the three-month
impulse kernel survives. Alternatively, an independently maintained surface
wind-stress product could provide a cleaner physical forcing channel.

This remains retrospective mechanism evidence, not an operational ENSO
forecast and not a causal intervention estimate.

## Reproduction

This report uses KinoPulse `0.1.0.dev2026071623`.

```powershell
.\.venv\Scripts\python.exe fetch_meiv2.py
.\.venv\Scripts\python.exe fetch_enso_heat_content.py
.\.venv\Scripts\python.exe fetch_enso_wind.py
.\.venv\Scripts\python.exe enso_wind_heat_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_fetch_enso_wind tests.test_enso_wind_heat_lab -v
```

The ignored evidence is `artifacts/enso_wind_heat_analysis.json`; the tracked
figure is `artifacts/enso_wind_heat_lab.png`.
