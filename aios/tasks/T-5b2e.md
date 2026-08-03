---
id: T-5b2e
title: Measure Claude Code's discovery and hook contract
status: waiting
waiting_on: "Claude Code is not installed, and npm is refused by the same execution policy that produced ADR-006 — two independent blockers, not one install command"
satisfies: [ADAPTERS-1, ADAPTERS-4]
priority: 2
risk: medium
blocked_by: []
touches:
  - aios/bin/probe/
  - .claude/settings.json
acceptance:
  - "Where the design relies on Claude Code reading a location, the system shall record a measurement of whether it does, dated and named to the version measured"
  - "When the hook contract is measured, the system shall record the event shape and the response mechanism from observation, and shall demonstrate one denial"
  - "If a location is found not to be read, then the system shall record that result distinctly from a location that was never measured"
verify:
  - python3 .github/scripts/check-hooks.py
  - python3 -m unittest discover -s tests
constraints:
  - "Rule out the confounds in probe/prompt.md before recording any `no`. A rejected file format and an unread location produce identical null results and are completely different findings."
  - "Allow for the settling lag measured in the Cursor run: a location read `NONE` twice and appeared two hours later. A probe with no settling period manufactures false negatives."
---

## Context

Two bootstrap items merged, because the plan already said to take both measurements in one
sitting and they share a single blocker. `M0-03` wanted the discovery matrix's Claude Code
column filled in; `M4-13` wanted the hook registrations in `.claude/settings.json` confirmed
against behaviour rather than against documentation. Splitting them would produce two tasks
that unblock on the same day and can only be done together.

`M4-13` is the sharper of the two. Those registrations are currently written to documentation,
and this repository's record on trusting tool documentation is five for five wrong — every
measured constraint in `AGENTS.md` contradicted something the design assumed. The
`UNVERIFIED` comment in the settings file is the standing admission of that.

Half the assumed asymmetry stays unmeasurable regardless. "Cursor reads parts of `.claude/`"
was measured; "Claude Code does not read `.cursor/`" needs the tool, and until then the matrix
records `not measured`, which is a different fact from `no`.

## Outcome

Blocked. Re-checked 2026-08-02: still not installed. Unblocks when Claude Code, or any second
coding tool, becomes available on the development machine.
