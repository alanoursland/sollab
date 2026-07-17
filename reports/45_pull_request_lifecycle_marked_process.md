# Pull-request lifecycles as a causal marked process

## Question

Does KinoPulse's new multitype temporal point-process surface let the
open-source experiment cross the evidence boundary identified in report 42:
an outcome-complete creation cohort with shared history, competing merge/close
events, and right censoring?

The scientific question is deliberately narrower than community health. It is
whether lifecycle age, repository, and author origin provide useful structure
for the observed event clock in a small fixed cohort.

## Frozen cohort

The fetch queried every PR created during calendar 2024 in `pallets/flask` and
`pallets/quart`, ordered each population by creation time, and selected 15
evenly spaced ranks including both endpoints. Events were observed through
2025-12-31.

| Repository | Population | Sample | Merged | Closed without merge | Right censored | First maintainer response |
|---|---:|---:|---:|---:|---:|---:|
| Flask | 111 | 15 | 6 | 8 | 1 | 3 |
| Quart | 33 | 15 | 9 | 3 | 3 | 4 |
| Combined | 144 | 30 | 15 | 11 | 4 | 7 |

This fixes the principal selection error in the earlier panel, which sampled
only successfully merged PRs. The source snapshot was retrieved at
`2026-07-17T06:50:34.891141+00:00`; its SHA-256 is
`47e537f87b089c4423d4474d90187ad14f135a00beb8fed616f599acc19a098d`.
Raw public account names remain only in the ignored snapshot.

The sample is systematic rather than random. It is appropriate for a bounded
mechanism experiment, not population confidence intervals.

## Event contract

Each PR is one marked history with three types:

1. first maintainer response: the first nonauthor issue comment or formal
   review whose association is `OWNER`, `MEMBER`, or `COLLABORATOR`;
2. merge, an absorbing terminal event;
3. close without merge, an absorbing terminal event.

Still-open PRs contribute exposure until the frozen cutoff and no terminal
mark. Response intensity becomes zero after the first response. Every
intensity becomes zero after merge or close. Author origin is reduced to
`automation`, `maintainer`, or `external`; no identity is retained in the
analysis artifact.

This is a genuine shared-history model. Fitting three independent unmarked
processes would not reproduce its risk intervals: response exposure stops at
response, while merge and close exposure continue until a terminal event or
censoring.

## KinoPulse contract check

The experiment uses `MultitypeTemporalPointProcess` with:

- a vector causal intensity;
- `MarkedEventHistory` to enforce one-shot and absorbing state changes;
- exact integrated intensities and per-type compensators;
- typed event contributions; and
- ordinary observation horizons for right censoring.

For pooled homogeneous rates, KinoPulse returns log likelihood
`-206.3871343417`. The independent analytical sufficient-statistic oracle is
identical to displayed precision. The fitted event counts and exposures are:

| Type | Events | Exposure days | MLE rate/day |
|---|---:|---:|---:|
| Maintainer response | 7 | 1,457.97 | 0.004801 |
| Merge | 15 | 2,460.63 | 0.006096 |
| Unmerged close | 11 | 2,460.63 | 0.004470 |

This validates the library mechanism. It does not validate the homogeneous
model as a description of the cohort.

The repository's older left-boundary history regression also changes from its
documented expected failure to a passing test under this release. The stale
expectation has been removed; report 22 remains an accurate record of the
earlier release.

## The homogeneous clock fails

The constant merge-plus-close hazard makes profoundly wrong operational-time
predictions:

| Age | Kaplan-Meier unresolved | Homogeneous unresolved |
|---|---:|---:|
| 1 day | 43.3% | 98.9% |
| 7 days | 36.7% | 92.9% |
| 30 days | 30.0% | 72.8% |
| 180 days | 13.3% | 14.9% |
| 365 days | 13.3% | 2.1% |

The apparent agreement near six months is a crossing, not calibration. The
same exponential clock misses both the initial resolution burst and the
persistent tail.

The response component is less visibly wrong for Quart: its observed
zero-response fraction is 73.3% versus 70.9% at the observed durations. For
Flask the corresponding values are 80.0% versus 92.8%. These are descriptive
checks on only 15 PRs per repository.

## Age-structured alternative

An exploratory piecewise model allows separate rates over ages
`[0,1)`, `[1,7)`, `[7,30)`, `[30,180)`, and `180+` days. Its integrated
intensity is exact rather than a grid approximation. The pooled in-sample log
likelihood rises to `-105.586`, but that comparison alone rewards 15 rate
parameters and is not evidence of generalization.

The stronger check is leave-one-PR-out log predictive density. Sparse cells use
an empirical-Bayes Gamma estimate centered on the training fold's pooled
homogeneous type rate. The shrinkage strength is varied rather than selected:

| Shrinkage exposure | Homogeneous pooled | Piecewise pooled | Improvement |
|---:|---:|---:|---:|
| 30 days | -215.585 | -131.343 | +84.242 nats |
| 180 days | -215.617 | -154.961 | +60.656 nats |
| 365 days | -215.646 | -168.498 | +47.148 nats |

The age result survives every tested shrinkage strength. At 180 days the best
homogeneous repository-by-origin model scores `-198.363`, still 43.40 nats
behind piecewise pooled. Adding repository or repository-by-origin cells to the
piecewise model also worsens prediction. In this small panel, lifecycle age is
the useful structure; finer group labels mostly spend data.

The first-day pooled MLE rates are large—response `0.360/day`, merge
`0.590/day`, and unmerged close `0.525/day`—then fall sharply. Later zero MLE
cells are boundary estimates, not evidence that events become impossible;
the predictive analysis explicitly shrinks them away from zero.

## What survived

1. The new KinoPulse marked-process implementation closes the specific library
   gap from report 42. Causal typed history, cause-specific compensators,
   absorbing intensity logic, and right-censored sequences all pass a real-data
   and analytical check.
2. Conditioning on successful merge was materially misleading. The fixed
   creation cohort contains 11 unmerged closures and four censored histories in
   only 30 observations.
3. One homogeneous workflow clock is decisively inadequate.
4. A coarse age-structured hazard earns its added complexity out of sample and
   is more useful than repository/origin stratification here.
5. Nothing in this panel supports a project-health, contributor-experience, or
   causal policy claim.

## Limitations and stopping rule

- The 30 PRs form a deterministic coverage sample, not a probability sample.
- The response channel sees issue comments and formal reviews, not inline
  review-comment bodies, commits, reactions, or private coordination.
- Maintainer association is GitHub metadata, not a stable social-role model.
- Automation detection recognizes `[bot]` accounts; other automation may be
  missed.
- The age boundaries were proposed after observing the homogeneous failure.
  Leave-one-out scoring reduces overfit risk but does not turn this exploratory
  choice into a prospective test.
- Pull requests within a repository are treated as conditionally independent;
  maintainer workload and calendar bursts are absent.

I would stop expanding this small API panel. The next credible step is a larger
prospectively specified creation cohort with inline review events, calendar
load, and a frozen age basis. That belongs in a new data program, not another
round of tuning these 30 histories.

## Reproduction

This report was produced with KinoPulse `0.1.0.dev2026071623`.

```powershell
.\.venv\Scripts\python.exe fetch_pull_request_lifecycle_panel.py
.\.venv\Scripts\python.exe pull_request_lifecycle_lab.py
.\.venv\Scripts\python.exe -m unittest tests.test_fetch_pull_request_lifecycle_panel -v
.\.venv\Scripts\python.exe -m unittest tests.test_pull_request_lifecycle_lab -v
```

The fetch creates a new public-data vintage and consumes unauthenticated GitHub
API quota. The ignored JSON evidence is
`artifacts/pull_request_lifecycle_marked_process.json`; the tracked figure is
`artifacts/pull_request_lifecycle_marked_process.png`.
