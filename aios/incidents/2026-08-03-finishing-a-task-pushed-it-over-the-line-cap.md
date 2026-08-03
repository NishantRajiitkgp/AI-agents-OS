---
date: 2026-08-03
detected_by: >-
  the task-schema gate in CI, on the push that retired the bootstrap plan; the same command
  had passed locally minutes earlier against the same file
control: >-
  the line cap now measures what a person wrote, excluding the verification record `aios done`
  appends
blocks_work: false
---

# 2026-08-03 — The act of completing a task made the task invalid

**Severity:** low in effect, and it is the second time one mechanism has surprised the other.
**Detected by:** `Task files conform to the schema` in `hygiene.yml`, at 61 lines against a
cap of 60.

## What happened

`T-b160` was written at 50 lines, well inside the 60-line cap, and validated. `aios done`
re-ran its four verify commands and appended the record it is supposed to append: a commit
SHA, a date, and two lines per command. Eleven lines. The file was then one over the cap and
a Contract gate refused it.

The local check had passed because it ran *before* the transition. There is no way to run it
after and before the push without knowing to look, and nothing said to look.

## Why the message was wrong

The gate's message says a task needing more than the cap is two tasks, or its context belongs
in a requirement or an ADR. Neither is available at that moment. The overrun is not context,
it is machine-written evidence; the task is finished, so splitting it is meaningless; and the
only edit that would fit is deleting prose from a file nobody is editing any more — which
would mean deleting the reasoning to make room for the proof.

The size of the problem scales with the number of verify commands. A task with six of them
owes fourteen lines, nearly a quarter of the budget, to a block it does not control and
cannot see while it is being written.

## Resolution

The cap now measures the file minus the `verified:` block. That is what the cap was for: it
bounds what a person has to read and hold in their head, and a machine-written record of
which commands exited zero is neither read that way nor written by hand.

`T-b160` keeps all fifty lines it was written with.

## What this does not fix

The record is still unbounded. Nothing stops a task declaring twenty verify commands and
carrying forty lines of record, and the cap will no longer notice. That is the right trade
today — a task with twenty verify commands has a different problem, and the schema gate is
not where it should be caught — but it is a limit removed rather than moved, and it is worth
saying so plainly.

The deeper shape is the one this repository keeps meeting: two mechanisms, each correct
alone, meeting for the first time in CI. The binary that writes the record and the validator
that judges the file already disagreed once, on 2026-08-02, about whether the field exists at
all. Both disagreements were only reachable by running the loop for real, which is the
argument for having run it.
