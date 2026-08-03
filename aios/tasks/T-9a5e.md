---
id: T-9a5e
title: Record the trial verdict as a decision, including a negative one
status: todo
satisfies: [TRIAL-5]
priority: 1
risk: high
blocked_by: [T-9a4d]
touches:
  - docs/decisions/
acceptance:
  - "When the trial period ends, the system shall record the verdict as a decision with its reasoning, whether that verdict is to continue, to rewrite substantially, or to abandon"
  - "The system shall retain the record of a negative verdict on the same terms as a positive one"
  - "If the trial ends with no verdict recorded, then the system shall report that as the outcome rather than continuing by default"
verify:
  - python3 .github/scripts/validate-references.py
  - python3 .github/scripts/check-docs.py
constraints:
  - "The decision record is immutable once written. A verdict that gets revised is a second record superseding the first, never an edit of it."
  - "Three outcomes, not two. 'Substantially rewrite' is a real verdict and collapsing it into 'continue' is how a system survives its own evaluation."
---

## Context

Carried over from `M6-05`. The failure mode this guards against is not a bad verdict, it is no
verdict — the trial period ends, nobody writes anything down, and the system continues because
continuing is what happens when nothing is decided.

A system that cannot be abandoned will be maintained past its usefulness, and the design's own
strongest quality is that it said in advance what would make abandoning it right. `TRIAL-5`
keeps a negative record on the same footing as a positive one for that reason: to whoever finds
this repository later, "we tried this and it did not work, here is why" is worth more than a
system quietly still running.

## Outcome

Open, blocked on the evaluation.
