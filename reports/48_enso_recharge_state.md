# ENSO recharge state: useful memory or a better story?

## Question

Does a public equatorial upper-ocean heat-content state add forecast information
beyond the scalar MEI.v2 models in report 47? More specifically, does a learned
coupled state recover the sign structure of an ENSO recharge oscillator, and
does that structure transfer to later forecasts?

## New state and provenance

`fetch_enso_heat_content.py` freezes NOAA PSL's Central Pacific Heat Content
series. It is the equatorial upper-300 m mean temperature anomaly over
160°E–80°W, relative to the 1981–2010 climatology, in degrees Celsius. NOAA
identifies GODAS Ocean Reanalysis as the source and warns that recent values may
be revised.

The snapshot contains 570 valid monthly values from January 1979 through June
2026. Its SHA-256 is
`0f9556f448448649878aed81bc1c867d2c2c8e1de1b4a7dbfcb7d3112aa57193`.

The ingestion audit immediately found that this NOAA series uses `-99.9` for
missing slots while MEI.v2 uses `-999`. The shared parser now treats any value
at or below `-90` as missing, and a regression test preserves that distinction.
No July–December 2026 heat observations are fabricated.

## Evidence boundary

This is a follow-up to report 47, so 2018–2025 is no longer an untouched
holdout. I already saw those MEI outcomes before specifying the coupled model.
The chronology is therefore labeled honestly:

| Role | Years | Interpretation |
|---|---:|---|
| Initial training | 1979–2009 | First expanding forecast |
| Model selection | 2010–2017 | Select physical model form and ridge penalty |
| Reused evidence | 2018–2025 | Exploratory comparison only |
| Newly scored path | Jan–Jun 2026 | First outcomes not scored in report 47 |

The scalar delayed oscillator and threshold-switching specifications are frozen
exactly from report 47. No scalar parameter is retuned here.

Every annual forecast observes MEI and heat through the preceding December,
then recursively forecasts both states. Future observed heat is never injected.
The 2026 path similarly initializes in December 2025 and runs for six months.

## Coupled models

The **recharge** model predicts the next two-state vector from current MEI,
current heat content, and annual sine/cosine terms. The **delayed recharge**
model adds the preceding month's two-state vector. Both equations share one
design matrix and ridge penalty.

KinoPulse `ExpandingWindowGroupSplit` and `cross_validate` select among ridge
penalties `0.001, 0.01, 0.1, 1, 10`. `RidgeSolver` fits each state equation.

## Validation result

| Family | Selected penalty | Mean 2010–2017 MEI path RMSE |
|---|---:|---:|
| Frozen threshold switching | `0.01`, guard `±0.3` | **0.6950** |
| Frozen delayed oscillator | `0.001` | 0.7801 |
| Delayed recharge | `0.1` | 0.7832 |
| Recharge | `10.0` | 0.8022 |

The physical state does **not** earn model replacement under the original
selection window. Delayed recharge wins only among the two new physical
families. This prevents the later point improvements from being rewritten as a
clean prospective selection win.

## Reused 2018–2025 evidence

| Family | MEI RMSE | Relative to frozen delayed oscillator |
|---|---:|---:|
| Frozen delayed oscillator | 0.7705 | — |
| Frozen threshold switching | 0.7496 | +2.7% |
| Recharge | 0.7382 | +4.2% |
| Delayed recharge | **0.7340** | **+4.7%** |

Delayed recharge wins 5/8 years against each scalar comparator. Whole-year
resampling does not distinguish the gains:

- versus the delayed oscillator, relative skill is 4.7%, with a 95% bootstrap
  interval of −4.2% to 19.4% and paired randomization `p = 0.211`;
- versus threshold switching, relative skill is 2.1%, with an interval of
  −9.1% to 20.3% and `p = 0.410`.

These numbers are descriptive because the period was already opened.

## Newly scored January–June 2026 path

| Model | Six-month MEI RMSE |
|---|---:|
| Frozen delayed oscillator | 0.8302 |
| Frozen threshold switching | 0.8231 |
| Recharge | 0.7922 |
| Delayed recharge | **0.7440** |

Observed MEI moves from `−1.03` in March to `+0.27` in May and `+1.52` in June.
Delayed recharge is the only tested model to cross zero in May, but reaches
only `+0.11` by June. The scalar models remain negative throughout.

This directional success is not an amplitude success. Observed heat content
rises from `0.45°C` in January to `2.14°C` in June; delayed recharge predicts
only `0.23°C` to `0.40°C`, for heat-content RMSE `1.252°C`. One six-month path
cannot validate forecast skill, and recent GODAS values may still be revised.

## Learned dynamics

The simple recharge fit is especially interpretable. Removing the seasonal
forcing, its current-state transition is approximately:

```text
[ MEI(t+1)  ]   [  0.832   0.231 ] [ MEI(t)  ]
[ heat(t+1) ] = [ -0.071   0.949 ] [ heat(t) ]
```

The signs match the conceptual recharge loop: positive subsurface heat drives
future surface ENSO upward, while positive surface ENSO discharges subsequent
equatorial heat. The eigenvalues are `0.890 ± 0.114i`, a stable oscillatory pair
with magnitude `0.898`, an implied period near 49 months, and amplitude
e-folding near 9 months.

The selected delayed model has a four-dimensional companion state. Its dominant
pair has magnitude `0.876` and implied period near 31 months; a second roughly
annual pair damps within about one month. These are empirical discrete-time
modes, not identified physical constants. Seasonal regressors, reanalysis
smoothing, and the chosen index geometry all affect them.

## KinoPulse gap found

The coupled fit exposed a narrow library gap. `RidgeSolver` accepts a matrix
target and computes its coefficient matrix, then crashes while calculating the
objective because it applies vector-only `torch.dot` to a matrix residual.

The experiment therefore performs one KinoPulse ridge solve per output and
stacks the results. The complete reproducer, expected contract, and regression
oracle are in
[`kinopulse_gaps/ridge_solver_multioutput_residual.md`](../kinopulse_gaps/ridge_solver_multioutput_residual.md).

## What survived

1. The public subsurface state learns the expected bidirectional recharge signs
   without enforcing them.
2. Both learned unforced state systems are stable and oscillatory.
3. Physical-state forecasts improve later point RMSE modestly and anticipate
   the sign of the sharp 2026 transition earlier than either frozen scalar
   model.
4. The physical models lose the original validation selection, their later
   gains are uncertain, and they severely underpredict the 2026 heat surge.
5. An interpretable mechanism can be scientifically interesting without being
   a validated forecast improvement.

## Next move

I would keep the recharge state and stop tuning it on these outcomes. The
missing input is likely forcing: the model cannot generate the abrupt 2026
subsurface buildup from a quiet December state. A defensible next experiment
would add a frozen equatorial Pacific wind or wind-stress index, use only values
available at initialization, and test whether it predicts heat-content change
rather than directly chasing MEI. Seasonal initialization and revision latency
should be explicit.

This remains an exploratory index model, not an operational ENSO forecast and
not a state-of-the-art comparison.

## Reproduction

This report uses KinoPulse `0.1.0.dev2026071623`.

```powershell
.\.venv\Scripts\python.exe fetch_meiv2.py
.\.venv\Scripts\python.exe fetch_enso_heat_content.py
.\.venv\Scripts\python.exe enso_recharge_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_fetch_meiv2 tests.test_fetch_enso_heat_content tests.test_enso_oscillator_lab tests.test_enso_recharge_lab tests.test_kinopulse_ridge_multioutput_gap -v
```

The ignored evidence is `artifacts/enso_recharge_analysis.json`; the tracked
figure is `artifacts/enso_recharge_lab.png`.
