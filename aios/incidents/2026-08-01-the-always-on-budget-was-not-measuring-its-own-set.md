---
date: 2026-08-01
detected_by: >-
  adding the explorer subagent and seeing the ratchet report held
control: >-
  check-always-on.py is the single implementation of the measurement, and both the ratchet and
  the workflow step call it rather than counting
blocks_work: false
---

# 2026-08-01 — The always-on budget was not measuring the set it was written to measure

**Severity:** latent. Nothing had gone wrong yet, and nothing could have, because the omitted
inputs were all empty. It would have started being wrong on the first commit of `M4-01`.
**Detected by:** reading the measurement before adding the first thing it failed to count.
Not by a gate, and no gate would have caught it — the defect was *in* the gate.

## What happened

[ADR-010](../../docs/decisions/ADR-010-budget-covers-the-measured-always-on-set.md) exists
because ADR-003 budgeted `AGENTS.md` alone while three other things loaded on every turn. Its
words: a budget on one input while three grow freely "is not a budget — it is a budget-shaped
object that produces a green signal while the thing it protects degrades".

The implementation of ADR-010 had that defect. Two copies of the measurement existed:

- **`hygiene.yml`**, in shell, which counted all four contributors correctly.
- **`check-ratchets.py`**, in Python, which counted `AGENTS.md` and the `alwaysApply` rules
  and stopped.

Both read their thresholds from `aios/config.yml`, so the *numbers* could not disagree. Only
the *set* could, and it did. Both reported 143 lines and would have gone on agreeing for
exactly as long as `.claude/agents/` and `.claude/skills/` stayed empty — which was until the
`explorer` subagent, five lines of description, was added by the very next task.

At that point the Contract gate would have reported 148 and the ratchet would have reported
143 and "held". The ratchet's job is to notice the set creeping up to the cap; it would have
been blind to the only category likely to do the creeping, because subagents and skills are
the things a repository accumulates and `AGENTS.md` is the thing it guards.

## Why it survived review

The two implementations were written weeks apart, against the same ADR, and each was correct
against the sentence its author read. Nothing in the repository asserted they agreed, and they
could not disagree observably until an input neither had ever seen became non-empty.

`AGENTS.md` names this hazard in general terms — "two implementations of one gate can
disagree" — as the reason gate logic moves into the binary. It was written about the
binary-versus-scripts split and was true about two scripts the whole time.

## Resolution

One implementation, in
[`check-always-on.py`](../../.github/scripts/check-always-on.py). The workflow step calls it;
`check-ratchets.py` imports it. Neither restates the definition.

The ratchet then correctly reported the explorer's five lines as a regression against a
baseline of 143, which was declared through the `raised` mechanism rather than absorbed. That
is the mechanism working as designed on its first real use outside a test.

## The control this produced

- **A test that the workflow step contains no counting of its own**
  (`test_the_workflow_calls_the_script_rather_than_restating_it`). It asserts the step calls
  the script and contains no `wc -l`, which is how the second copy started.
- **A test per contributor** that each is counted, including one for descriptions
  specifically — the input that was missing. Ten mutations against the measurement, all
  caught, including "descriptions stop being counted", which is the defect itself replayed.

## What this does not fix

Nothing asserts that the *other* provisional gates have only one implementation. This one was
found by reading, and the general form — a definition restated in shell and in Python —
remains possible anywhere the workflow does work inline. It narrows as gate logic moves into
the binary (ADR-006), and the honest statement today is that this was caught by attention
rather than by a control.
