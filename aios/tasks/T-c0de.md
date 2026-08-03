---
id: T-c0de
title: Re-run the adapter probe and delete what the host tools now do
status: todo
satisfies: [ADAPTERS-5]
priority: 3
risk: low
blocked_by: []
touches:
  - aios/bin/probe/
  - docs/
acceptance:
  - "The system shall re-run the discovery measurements on a fixed interval regardless of releases, and shall record the results against the tool versions measured"
  - "When a tool the system depends on releases a major version, the system shall re-run the measurements and record the results against that version"
  - "Where an OS feature now overlaps a native feature of a host tool, the system shall delete the OS version unless a written reason to keep it is recorded"
verify:
  - python3 .github/scripts/validate-references.py
constraints:
  - "Allow the settling period measured in the first run. A location read `NONE` in two sessions and appeared two hours later; a probe without settling manufactures false negatives."
  - "Default to deleting, not to keeping. Keeping an overlapping feature requires a written reason — usually cross-tool portability — and 'ours is slightly better' is not one."
---

## Context

The standing item, carried over from `S-01`, and the first one due after this repository's own
build finishes. Every measurement in `aios/bin/probe/results/` is a fact about a tool version;
tools ship, discovery behaviour changes, and a recorded result quietly becomes a recorded
belief. Re-running is cheap. Finding out by accident that a rule stopped attaching is not.

The Windows-specific assumptions need re-verifying each time too — the execution policy, the
symlink checkout behaviour, the network filtering. All three are undocumented behaviour and
will change without notice.

The deletion half matters more than the probe half. A shrinking OS is a healthy one; if this
is the same size in two years it has stopped tracking reality, which is kill criterion 5
arriving quietly rather than at the evaluation.

## Outcome

Open. Recurring: closing this one opens the next, dated a quarter on.
