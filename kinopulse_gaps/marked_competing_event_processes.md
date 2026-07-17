# Gap: Marked temporal processes with competing terminal events

## Status: addressed in `0.1.0.dev2026071623`

`MultitypeTemporalPointProcess` now supplies typed causal histories,
cause-specific intensities and compensators, batched/right-censored horizons,
observation probabilities, missing/censored mark policies, differentiable
likelihoods, and homogeneous simulation. Report 45 exercises the release on an
outcome-complete PR cohort. History-dependent intensities implement a one-shot
response and become identically zero after merge or unmerged close; the package
likelihood matches the analytical absorbing-process oracle exactly.

The remainder of this document records the historical boundary that motivated
the addition. It is no longer an open gap.

## Discovered in

The bounded pull-request collaboration panel following the merge-topology
audit. A pull request can receive typed events (issue comment, formal review,
approval, changes requested) and then terminate through competing outcomes
(merge, close without merge, or censoring while still open).

## Historical boundary

`kinopulse.stochastic.TemporalPointProcess` accepts one sorted one-dimensional
tensor of event times. Its intensity and history contracts receive no event
marks or event types. The likelihood has one event contribution and one
compensator, and the simulator supports only the homogeneous unmarked subset.

That is sufficient for a single event channel such as homogeneous arrivals or
an unmarked Hawkes process. It cannot natively express:

- cause-specific intensities for several event types;
- a history containing both time and mark;
- an absorbing terminal event after which intensity is zero;
- competing merge/close hazards;
- right-censored sequences with no terminal event;
- sequence covariates such as author association or change size;
- a joint likelihood that sums cause-specific compensators while selecting the
  observed event's cause-specific intensity.

Fitting independent unmarked processes per event type is not an equivalent
workaround because every channel shares the same history and risk interval.

## Why it matters beyond this lab

The same contract is needed for aftershock time–magnitude marks, failures with
several modes, clinical competing risks, queue events with typed transitions,
and hybrid systems observed through heterogeneous events.

## Suggested minimal API

A `MarkedTemporalPointProcess` or compatible extension could accept:

```python
event_times: Tensor[n]
event_marks: Tensor[n, ...]  # or integer event types Tensor[n]
horizon: float
terminal_type: int | None
sequence_covariates: Any = None
```

The intensity contract should return either one value for the supplied mark or
a vector over a fixed event-type vocabulary. The result should expose:

- per-type event contributions;
- per-type compensators;
- total log likelihood;
- terminal/censoring provenance;
- validation that no event occurs after an absorbing terminal event.

## Analytical regression oracle

Use two constant cause-specific rates `lambda_1` and `lambda_2` over horizon
`T`. For an observed type-2 event at `t < T`, the log likelihood is

```text
log(lambda_2) - (lambda_1 + lambda_2) * t
```

when that event is absorbing. For right censoring at `T`, it is

```text
-(lambda_1 + lambda_2) * T
```

Batch results should match scalar evaluation exactly, and an event after the
absorbing terminal time must be rejected.

## What the playground did instead

The current pull-request lab fits only a deliberately inadequate homogeneous
process to nonterminal human response events and reports its failure. It does
not implement a local competing-risk substitute.
