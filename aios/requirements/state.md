# STATE — project state, task lifecycle, and verification

What the OS must guarantee about the record of its own work: where state lives, how progress
is derived from it, and what has to be true before anything may be called done.

This is the capability area for the first slice. Every requirement here is one the walking
skeleton at `M1` either satisfies or is explicitly deferred against.

Requirements are never deleted. A withdrawn one keeps its entry, its status, and its reason,
because the record of what was once wanted is the memory this system exists to keep.

---

## STATE-1 — One file per unit of work

**Status:** active
**Rationale:** An aggregate store is a single merge region every concurrent change contends
for, and a format where a bad merge stays syntactically valid is one that loses work
silently. Per-unit files make a conflict a conflict.

The system shall store each task in exactly one file whose name contains that task's ID.

The system shall store requirements in one file per capability area, rather than one file
per requirement.

**Out of scope:** any aggregate index, cache, or database derived from these files. If one is
ever added it is a build artifact and never the source of truth.

---

## STATE-2 — Progress is computed, never asserted

**Status:** active
**Rationale:** The core claim of the design. An agent that can write its own progress will
eventually write progress it has not made, and the failure is silent because the record looks
identical either way.

When asked for the state of the project, the system shall derive it from the task files
present on disk.

The system shall reject any stored value that claims a project-level or requirement-level
completion state.

---

## STATE-3 — Done requires a machine-verified record

**Status:** active
**Rationale:** [D-010](../../docs/design/10-decision-register.md#d-010--done-requires-a-machine-verified-record).
This is the single property `M1` exists to prove; if it does not hold, the rest of the system
is ceremony.

When a task is moved to `done`, the system shall require a verification record naming the
command that was run and the exit status it returned.

If no verification record exists, or the recorded exit status is non-zero, then the system
shall refuse the transition and leave the task in its previous state.

The system shall refuse a `done` transition requested without a verification record even when
the requester asserts the work is complete.

---

## STATE-4 — Verification is re-run by the grader, not trusted from the record

**Status:** active
**Rationale:** A verification record written by the party being graded is a claim, not
evidence. Re-running it somewhere the agent cannot reach is what converts one into the other.

When a pull request is opened, the system shall re-execute the verification command of every
task changed in that pull request.

If a re-executed result differs from the recorded result, then the system shall fail the
pull request and report both values.

---

## STATE-5 — Task selection is deterministic

**Status:** active
**Rationale:** A selector whose answer depends on who asked, or on what was asked first,
reintroduces the judgement call the state model exists to remove.

When asked for the next task, the system shall return the same task for the same repository
state, regardless of invocation order or of which agent is asking.

If no task is eligible, then the system shall say so and name the condition blocking each
candidate, rather than returning an arbitrary task.

---

## STATE-6 — Malformed state is refused at the boundary

**Status:** active
**Rationale:** State that is half-valid is worse than state that is missing: every consumer
downstream has to guess, and they guess differently.

If a task or requirement file does not conform to its schema, then the system shall report
the specific violation and exit non-zero.

The system shall distinguish an inability to run a check from a check that ran and passed.

---

## STATE-7 — Identifiers are unique across the repository

**Status:** active
**Rationale:** Two branches can each add `STATE-8` without either being wrong locally. The
conflict is cheap to fix while a requirement is new and expensive once it is cited from tasks,
tests, and commit messages.

The system shall reject a requirement or task identifier that is already in use elsewhere in
the repository.

---

## STATE-8 — A withdrawn requirement is retained, never removed

**Status:** active
**Rationale:** The record of what was once wanted, and why it stopped being wanted, is the
institutional memory the whole system exists to preserve. Deleting it destroys exactly the
thing that cannot be recovered by reading the code later.

When a requirement is withdrawn, the system shall retain its entry and record a status of
`dropped` or `superseded-by`, together with a stated reason.

The system shall reject a status of `deferred`, `dropped`, or `superseded-by` that carries no
reason.

---

## STATE-9 — Computed board view

**Status:** deferred
**Reason:** Agreed, not now. Scheduled at `M5-08`. A visualisation of a loop that has not yet
run end to end would be a view over data whose shape is still being decided, and the first
slice needs the loop to work rather than to look finished.

When asked for a board, the system shall render the current task set grouped by state,
computed at the moment of the request.
