---
id: T-9a2b
title: Run the trial project on the OS for three months, instrumented
status: todo
satisfies: [TRIAL-2]
priority: 1
risk: high
blocked_by: [T-9a10]
touches:
  - docs/
acceptance:
  - "The system shall run on the trial project for a period fixed in advance and shall not extend it in response to the evidence accumulating"
  - "When the trial runs, the system shall collect the same metrics the baseline recorded, by the same method"
  - "If the trial is stopped early, then the system shall record the reason and the elapsed period rather than the intended one"
verify:
  - python3 .github/scripts/report-health.py
constraints:
  - "Not this repository. ADR-001 §2 — the OS's own development is not evidence about the OS, because the people building it are not the people it has to work for."
  - "Instrumented from day one. Metrics started partway through describe a period that has already been influenced by the thing being measured."
---

## Context

Carried over from `M6-02`. Three months is a fixed period rather than a target, and the
distinction is the whole of `TRIAL-2`: a trial with no end date is not evaluated, it is
inhabited. The decision point then arrives only when somebody happens to ask, by which time
the cost of stopping has already been paid.

The instrumentation is the deliverable here, not the running. Work happening on the project is
work that would have happened anyway — that is the condition under which it is evidence at all.

## Outcome

Open, blocked on the baseline.
