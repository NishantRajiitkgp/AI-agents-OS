---
id: T-9a4d
title: Evaluate the trial against the six kill criteria as written
status: todo
satisfies: [TRIAL-3]
priority: 1
risk: high
blocked_by: [T-9a2b]
touches:
  - docs/
acceptance:
  - "The system shall evaluate each of the six kill criteria against the trial's measurements and the recorded baseline"
  - "If a kill criterion is met, then the system shall report it against the criterion as written, without reinterpreting the criterion"
  - "When a criterion cannot be evaluated, the system shall report it as unevaluated rather than as not met"
verify:
  - python3 .github/scripts/validate-references.py
constraints:
  - "The criteria are fixed before the evidence and may not be edited in response to it. A criterion rewritten after the results are visible is a description of the outcome."
  - "Check criterion 6 first. It is the one most likely to be true and the cheapest to check, and a system nobody reads has already failed regardless of its numbers."
---

## Context

Carried over from `M6-04`. The six, unchanged: median start-to-merge worse and unexplained by
better outcomes; review debt chronically over limit; Contract gates overridden more often than
they pass; repository markdown volume exceeding source volume; host tools having absorbed
enough that this is a thin shim; and nobody having read a task file, an ADR or a requirement in
a month.

`TRIAL-3`'s point is that these were written before any evidence arrived, which is the only
condition under which they mean anything. Once the results are visible nobody can un-see them
while deciding what would have counted as failure, so this task's real constraint is that it
does no writing — it reads criteria somebody else already committed to.

## Outcome

Open, blocked on the trial running.
