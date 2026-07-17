# Open-source community and GitHub research guide

This guide is the practitioner entry point to the open-source community work in
the KinoPulse Playground. The program asks a connected sequence of questions:

- What can a frozen public Git organization measure reproducibly?
- Can nearly stable commit volume conceal a change in contributor renewal?
- How much does Git traversal and merge policy change the observed population?
- Do pull-request events validate the collaboration mechanisms inferred from
  commit topology?
- Can a causal marked process represent response, merge, unmerged closure, and
  right censoring without conditioning on successful outcomes?

The short answer is that Git history supports a useful **commit ecology**, but
not a project-health score. Similar volume can arise from different contributor
flows; first-parent traversal can hide most observed contributors; formal
review events alone are a poor proxy for collaboration; and pull-request age is
far more predictive of lifecycle timing than one homogeneous workflow clock.

Nothing in this project establishes that Pallets—or any repository—is healthy,
declining, resilient, well governed, or approaching a tipping point.

## Read this first

This is public research software, not an employee-monitoring, maintainer-rating,
or repository-ranking product. Commit and pull-request records are incomplete
projections of collaborative work. They omit or distort issue triage, review,
design discussion, security response, community support, private work,
funding, governance, and contributor experience.

The labs intentionally retain public identity information only in ignored raw
snapshots when it is needed to exclude self-response or normalize aliases.
Tracked reports and aggregate artifacts do not publish names, email addresses,
or account-level rankings. Do not repurpose the code to score individuals.

Public visibility also does not erase contextual integrity. A person's public
commit or comment was created to collaborate on software, not necessarily to
support behavioral evaluation outside that setting.

This repository currently has no license file. Public visibility alone does
not grant permission to reuse or redistribute the code or figures.

## Choose your path

| If you want to... | Start here | What you will get |
|---|---|---|
| Understand the result quickly | [Commit ecology](reports/39_open_source_commit_ecology.md), then [lifecycle model](reports/45_pull_request_lifecycle_marked_process.md) | The broadest measurement audit and strongest event-model result |
| Audit the scientific progression | [Experiment map](#experiment-map) | Every question, negative result, and evidence boundary in order |
| Reproduce the frozen Git analysis | [Frozen-snapshot reproduction](#frozen-snapshot-reproduction) | Aggregate weekly ecology, contributor flows, and topology contrasts |
| Refresh public GitHub data | [Data refresh](#data-refresh) | A new, explicitly different data vintage |
| Adapt the method to another organization | [Adaptation checklist](#practitioner-adaptation-checklist) | Decisions that must be remade rather than copied |
| Understand privacy boundaries | [Privacy and responsible interpretation](#privacy-and-responsible-interpretation) | What raw data contain and what tracked outputs deliberately omit |
| See how KinoPulse is used | [KinoPulse capability map](#kinopulse-capability-map) | Online estimation, regression, point processes, and grouped validation roles |

## What is usable today

### Reproducible measurement code

The scripts can freeze a whole present-day public organization, verify exact
default-branch heads, reconstruct reachable and first-parent commit views,
normalize public Git identities without exporting them, classify obvious
automation, build weekly contributor-flow states, and freeze bounded
pull-request panels.

These are useful starting points for measurement research, software-repository
mining, and independent replication. They are not a turnkey comparative
benchmark: every organization can have different merge policy, repository
history, bot conventions, transferred projects, and public-event coverage.

### Causal marked lifecycle example

[pull_request_lifecycle_lab.py](pull_request_lifecycle_lab.py) is the most complete KinoPulse example in this
research line. Each PR is one causal history containing:

- first observed maintainer response;
- merge as an absorbing terminal event;
- close without merge as an absorbing terminal event; or
- a right-censored horizon for work still open at the frozen cutoff.

Response intensity becomes zero after the first response, and every intensity
becomes zero after a terminal event. The implementation has an independent
analytical likelihood oracle and tests identity-free tracked output.

It is a mechanism demonstration on 30 systematically sampled PRs, not a fitted
general model for GitHub.

### What is deliberately not shipped

There is no community-health index, contributor score, repository leaderboard,
decline alarm, trained cross-project model, or policy recommendation. The
evidence does not support any of them.

## Data and observation contracts

### Whole-organization Git snapshot

The initial fetch uses GitHub's official organization repository endpoint and
selects:

> all public repositories owned by `pallets`, excluding forks only

The frozen 2026-07-17 vintage contains 17 repositories, including six archived
repositories. Archived projects remain because dropping them would condition
the cohort on present-day survival. Each repository is stored as a blob-free
bare clone with its default branch, exact frozen head, API metadata, and commit
count recorded in an ignored manifest.

The current organization roster cannot recover repositories that were deleted
or transferred away. Early reachable commits can predate present ownership.
This is a frozen present-day organization cohort, not a complete history of the
organization as an institution.

### Commit identity and time

Commits are placed in UTC weeks using committer time. Contributors are
mailmap-aware author-email identifiers with GitHub `noreply` aliases normalized.
An identifier is not necessarily one person, and one person may retain several
identifiers. Obvious bot accounts are removed heuristically.

Tracked outputs contain aggregate counts only. The raw identifiers needed for
normalization remain inside ignored local data.

### Reachable versus first-parent history

Reports 39–40 use every commit reachable from the frozen default-branch head
because their target is authored participation preserved in the integrated Git
graph. Report 41 separately reconstructs first-parent history, which is useful
for mainline integration cadence but is not an equivalent contributor census.

Every use of “Git contributor” should name its traversal policy. Squash, rebase,
merge commits, force-pushes, and rewritten history alter what the graph retains.

### Pull-request panels

Two panels answer different questions:

1. Report 42 enumerates PRs merged during 2024 and selects ten evenly spaced
   creation-order ranks per repository. It validates the Git-topology contrast
   but is conditioned on successful merge.
2. Report 45 enumerates every PR **created** during 2024 and selects 15 evenly
   spaced ranks per repository. It observes them through 2025-12-31, preserving
   merge, unmerged close, and still-open censoring.

The second design repairs the principal selection error in the first. Both are
systematic coverage samples, not random samples supporting population standard
errors.

The REST fetches include formal reviews and issue comments. They do not retrieve
inline review-comment bodies, reactions, commits pushed during review, linked
issue discussion, or private coordination.

## Main findings

### 1. Stable commit volume does not imply a stable ecology

The most recent 52 complete weeks contain 871 human-classified commits, versus
894 in the preceding year: 97.4% as much volume. Yet the largest author's share
falls from 68.2% to 36.2%, and author-commit HHI falls from 0.473 to 0.202.

One scalar activity series would call the periods nearly identical while
hiding a major redistribution of contribution load. That redistribution is not
automatically good or bad.

### 2. The renewal mechanism changed beneath the volume

Recent active-author weeks rise 21.0% and continuing-author weeks rise 82.9%,
while newly observed author identifiers fall 27.6%. Only 13.7% of fully
observed 2013–2024 newcomer identifiers reappear within 52 weeks.

The flow decomposition is descriptively useful but adds only 1.04% to
chronological next-week prediction accuracy. A clearer state description does
not automatically become a strong forecast.

### 3. Git topology changes the observed contributor population

Of 20,530 complete-week human reachable commits, 9,526 lie outside first-parent
history: 46.4%. First-parent traversal retains only 488 of 2,161 reachable
author identifiers, or 22.6%.

The effect differs sharply by repository. First-parent author coverage is 14.1%
for Flask and 95.6% for Quart. A contemporaneous KinoPulse topology map reduces
weekly view-translation RMSE by 41.3%, but the remaining error is still 57.2%
of mean holdout activity. One scalar correction cannot make the histories
commensurate.

The conditional 52-week newcomer return rate changes only from 13.66% to
12.57%. Thus the qualitative claim that most observed contributors are
episodic survives, while the absolute contributor population does not.

### 4. The topology contrast survives a bounded PR audit

In report 42's merged-only samples, 9/10 Flask PRs correspond to merge commits,
whereas 7/10 Quart PRs have linear single-parent integration results. This
supports the interpretation that the first-parent contrast reflects real merge
policy rather than only a traversal bug.

Formal review appears on only one PR in each ten-PR sample. Adding nonauthor
issue comments yields any observed pre-merge response on three Flask PRs and
one Quart PR. Formal review counts are therefore an inadequate stand-in for
review culture or maintainer attention here.

### 5. Conditioning on merge hid most terminal diversity

The outcome-complete 30-PR sample contains 15 merges, 11 closes without merge,
and four right-censored histories. Those 15 non-merge outcomes were excluded by
construction from report 42.

The causal KinoPulse marked-process likelihood matches its analytical oracle
exactly. A homogeneous terminal clock nevertheless fails dramatically: it
predicts 98.9% of PRs unresolved after one day, while the Kaplan–Meier estimate
is 43.3%. At 365 days it predicts only 2.1% unresolved versus 13.3% observed.

A pooled age-structured process with boundaries at 1, 7, 30, and 180 days beats
every tested homogeneous alternative in leave-one-PR-out prediction. Its gain
over homogeneous pooled ranges from 47.1 to 84.2 log-density nats across
declared shrinkage strengths. Adding repository or author-origin detail to the
age model makes prediction worse. In this sample, lifecycle age earns its
complexity; finer group labels mostly spend scarce data.

### 6. The program has not measured decline or health

Every positive result concerns measurement structure, observation bias, or
event timing. None defines a transition outcome, compares multiple independent
organizations, or demonstrates an early-warning signal before a prospectively
declared decline.

A quiet repository may be mature. A busy repository may be distressed. A fast
merge may be careful automation or superficial review. A slow merge may be
neglect or thoughtful iteration. The available event record cannot decide
among those interpretations by itself.

## Experiment map

The community reports are 39, 40, 41, 42, and 45. Reports 43–44 are a separate
geomagnetic-storm branch of the playground.

| Stage | Report | Primary scripts | Tracked figure | Main evidence boundary |
|---|---|---|---|---|
| Commit ecology | [39](reports/39_open_source_commit_ecology.md) | [fetch](fetch_open_source_community.py), [analysis](open_source_commit_ecology_lab.py) | [figure](artifacts/open_source_commit_ecology.png) | Commits are activity, not health |
| Contributor renewal | [40](reports/40_contributor_flow_dynamics.md) | [analysis](contributor_flow_lab.py) | [figure](artifacts/contributor_flow.png) | Identifiers are not verified people; flow adds little prediction |
| Topology audit | [41](reports/41_merge_topology_measurement_audit.md) | [analysis](merge_topology_audit_lab.py) | [figure](artifacts/merge_topology_audit.png) | Reachable and first-parent histories measure different populations |
| Merged PR validation | [42](reports/42_pull_request_collaboration_panel.md) | [fetch](fetch_pull_request_panel.py), [analysis](pull_request_collaboration_lab.py) | [figure](artifacts/pull_request_collaboration_panel.png) | Successful merges only; response channel is sparse |
| Marked PR lifecycles | [45](reports/45_pull_request_lifecycle_marked_process.md) | [fetch](fetch_pull_request_lifecycle_panel.py), [analysis](pull_request_lifecycle_lab.py) | [figure](artifacts/pull_request_lifecycle_marked_process.png) | Thirty systematic PRs; exploratory age boundaries |

Report 42 accurately records that KinoPulse lacked a marked competing-event
contract at the time. KinoPulse `0.1.0.dev2026071623` added multitype temporal
point processes, and report 45 verifies the new surface. The corresponding
document in `kinopulse_gaps/marked_competing_event_processes.md` is now marked
resolved.

## KinoPulse capability map

| Capability | Where used | Purpose |
|---|---|---|
| Recursive least squares | Report 39 | Track a descriptive persistence coefficient while warning that smoothing induces persistence |
| Ridge regression | Report 40 | Test whether contributor-flow counts improve chronological next-week activity prediction |
| Ridge observation map | Report 41 | Test whether first-parent topology measurements can reconstruct reachable activity |
| Unmarked temporal point process and Poisson deviance | Report 42 | Demonstrate why one homogeneous response clock is inadequate |
| Multitype temporal point process | Report 45 | Jointly represent response, merge, close, causal history, and censoring |
| Differentiable likelihood and exact compensators | Report 45 | Check the implementation against a closed-form absorbing-process oracle |

KinoPulse provides numerical and validation machinery. It does not supply the
social interpretation, outcome definition, cohort validity, or ethical basis
for a community claim.

## Reproduction

Use the repository's `.venv` for every command.

### Documentation-only review

The reports and tracked PNG figures are sufficient to inspect the frozen
results without downloading public data or contacting GitHub.

### Frozen-snapshot reproduction

If the ignored `data/open_source_community/` snapshot is present, regenerate
the aggregate analyses without refreshing the data:

```powershell
.\.venv\Scripts\python.exe open_source_commit_ecology_lab.py
.\.venv\Scripts\python.exe contributor_flow_lab.py
.\.venv\Scripts\python.exe merge_topology_audit_lab.py
.\.venv\Scripts\python.exe pull_request_collaboration_lab.py
.\.venv\Scripts\python.exe pull_request_lifecycle_lab.py
```

The labs verify frozen heads or source digests where applicable. Aggregate JSON
evidence under `artifacts/` is ignored; figures are tracked for review.

### Data refresh

These commands contact public GitHub endpoints and create a **new data
vintage**, not an exact reproduction of the reports:

```powershell
.\.venv\Scripts\python.exe fetch_open_source_community.py
.\.venv\Scripts\python.exe fetch_pull_request_panel.py
.\.venv\Scripts\python.exe fetch_pull_request_lifecycle_panel.py
```

The REST API fetches are unauthenticated and consume public rate limits. A
refresh can change repository rosters, default-branch heads, archive status,
PR state, comments, reviews, and censoring outcomes. Preserve retrieval time,
selection rules, URLs, and hashes whenever publishing a refreshed result.

### Tests

Run the community-specific tests:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_open_source_commit_ecology_lab -v
.\.venv\Scripts\python.exe -m unittest tests.test_contributor_flow_lab -v
.\.venv\Scripts\python.exe -m unittest tests.test_merge_topology_audit_lab -v
.\.venv\Scripts\python.exe -m unittest tests.test_fetch_pull_request_panel -v
.\.venv\Scripts\python.exe -m unittest tests.test_pull_request_collaboration_lab -v
.\.venv\Scripts\python.exe -m unittest tests.test_fetch_pull_request_lifecycle_panel -v
.\.venv\Scripts\python.exe -m unittest tests.test_pull_request_lifecycle_lab -v
```

Or run the complete repository suite:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## Privacy and responsible interpretation

### Tracked outputs

Tracked reports and figures may contain repository names, public PR numbers,
aggregate event counts, frozen dates, and model diagnostics. They do not contain
author names, email addresses, login-level tables, or individual rankings.

### Ignored local data

`data/open_source_community/` can contain bare Git repositories, normalized
identity inputs, public PR authors, reviewers, commenters, URLs, and exact event
times. `artifacts/*.json` contains detailed aggregate evidence. Both are ignored
to prevent accidental publication of bulky snapshots or unnecessary identity
data.

The analysis artifact for report 45 deliberately reduces author origin to
`automation`, `maintainer`, or `external`. Public logins are needed locally to
exclude self-response but are not copied into tracked evidence.

### Responsible claims

Do not use these labs to:

- rank maintainers or contributors;
- infer effort, competence, burnout, sentiment, or intent;
- treat response latency as review quality;
- compare repository “health” without matched observation contracts;
- label a project as declining from commit volume alone; or
- identify people for employment, funding, enforcement, or moderation action.

Independent replication should aggregate at the repository or organization
level, minimize retained identity data, document deletion/retention policy, and
review whether the research purpose is proportionate to the people represented.

## Practitioner adaptation checklist

Before applying the work to another organization or cohort:

1. **Predeclare the unit.** Organization, repository, package ecosystem, and
   contributor network answer different questions.
2. **Freeze the roster without survivorship filtering.** State how forks,
   archived repositories, transfers, deletions, and mirrors are handled.
3. **Record exact heads and retrieval time.** A moving default branch is not a
   reproducible dataset.
4. **Name the Git traversal.** Reachable, first-parent, release-tag, and
   time-sliced views are not interchangeable.
5. **Audit merge policy before comparing contributors.** Squash, rebase, and
   merge-heavy repositories preserve different attribution structures.
6. **Define identity conservatively.** Keep alias logic, bot heuristics, and
   uncertainty visible; avoid claims about unique people.
7. **Choose an observation channel that matches the question.** Commits cannot
   answer review-work questions; formal review events alone may also be sparse.
8. **Preserve all outcomes.** For PR lifecycles, include merge, unmerged close,
   and still-open censoring. Do not select only successes.
9. **Split by independent groups.** Keep whole repositories, PRs, or
   organizations together as required; do not treat correlated weekly rows as
   independent evidence.
10. **Keep chronology causal.** Hyperparameters, thresholds, and issue decisions
    may use only outcomes available at that time.
11. **Predeclare the transition outcome.** “Decline” needs an observable,
    defensible definition before early-warning analysis begins.
12. **Use negative controls.** Test whether apparent warning signals are caused
    by smoothing, release cadence, repository mix, or observation-policy change.
13. **Report mechanism and uncertainty, not moral labels.** A count change rarely
    identifies its social cause.
14. **Minimize identity retention.** Export aggregates whenever account-level
    data are unnecessary for the stated claim.

## Current stopping point

The small Pallets program has reached its intended stopping point. It has:

- established a reproducible whole-organization commit ecology;
- decomposed contributor renewal beneath stable volume;
- measured severe traversal-policy sensitivity;
- validated the merge-topology interpretation through public PRs;
- repaired merged-only outcome selection; and
- exercised a causal marked lifecycle process with honest censoring.

More tuning on the same organization or 30 PRs would spend the sample rather
than strengthen the conclusion. The next credible program would require a
prospectively specified multi-organization cohort, a frozen age basis, inline
review activity, calendar workload, explicit observation-policy covariates,
and a transition outcome defined before analysis.

Until then, the strongest conclusion is methodological: **model the observation
system before modeling community change**.
