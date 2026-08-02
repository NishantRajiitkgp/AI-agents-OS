# ADR-014 — Time spent on a diff is not measurable, and that enforcement is dropped

**Status:** accepted · **Date:** 2026-08-02 · **Milestone:** M5-09

## Context

The design asks for review-debt tracking: "count of merged tasks whose diffs the human spent
under a threshold on, or dismissed without comment, in a rolling window. Above the limit,
`aios next` refuses to hand out work."

The intent is sound and is arguably the most important claim in the whole design. Every quality
argument here terminates in a human reading a diff. If that stops happening, the gates are
checking the work of an agent whose output nobody reads, and the system is an elaborate way of
merging unreviewed code with a green tick on it.

The question is whether the first half of the measure can be taken.

## Decision

**The time-based half is dropped.** Not deferred, not marked as pending a better data source —
removed, and this ADR is the record of why.

Nothing in a forge records attention. What GitHub exposes is when a review was submitted, and
the interval between a review being requested and submitted contains lunch, three meetings and
eleven other tabs. A reviewer who reads carefully for forty minutes and one who approves from a
phone six hours later are indistinguishable in the data, and ordered the wrong way round.

A metric that wrong does not become useful by being enforced. It becomes worse than nothing,
because a dashboard reporting "review time: healthy" is read as evidence that someone is
reading — which is precisely the claim it cannot support. The design's own standard applies:
*a control that cannot be measured should be removed rather than left as decoration.*

**The engagement half is kept**, because it is recorded rather than inferred:

- **approvals carrying no comment**, which is what the target behaviour actually looks like.
  The design is explicit that the target is a person in a flow state who has stopped noticing
  they stopped reading — not a determined circumventer, whom no proxy catches.
- **diff size per review cycle**, because reading does not scale linearly with lines, and the
  honest place for the budget is on the diff rather than on the reader.

Above the limit, `aios next` refuses to hand out work. Refusing to create more work is the only
response that acts on the constraint; every other response adds to the queue that is the
problem.

## Alternatives considered

**Instrument the editor.** Measures the wrong population — reviewers often are not in this
editor — and buys a real surveillance problem for a weak signal.

**Ask the reviewer to self-report.** Self-reported attention from someone not paying attention.

**Use time anyway, with wide bounds.** The failure is not precision, it is that the ordering is
wrong. Widening the bounds makes it useless faster rather than more honest.

## Consequences

The report is narrower and every number in it means what it says. The remaining measure needs
merged pull requests to exist, which this repository has none of, and `check-review-debt.py`
exits "could not run" rather than passing quietly.

**What is given up:** a reviewer who reads nothing but leaves one comment per pull request
defeats the remaining measure completely. That is accepted. The alternative on offer was not a
better control, it was the same gap with a number printed next to it.

## Revisit when

A forge exposes a signal about attention rather than elapsed time, or `M6` produces evidence
that uncommented-approval rate does not move when review quality visibly falls.
