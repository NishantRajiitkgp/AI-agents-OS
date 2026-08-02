# ADR-010 — The context budget is enforced against the measured always-on set

**Status:** accepted. **Supersedes [ADR-003](ADR-003-agents-md-line-budget.md).**
**Date:** 2026-07-31
**Arose from:** `M0-02`

## Context

[ADR-003](ADR-003-agents-md-line-budget.md) set a 150-line budget on `AGENTS.md`, implementing
[P4](../design/02-principles.md)'s requirement that always-on context be a fixed,
small, enforced allowance. The design assumes throughout that `AGENTS.md` *is* the always-on
surface.

M0 measured otherwise. Four things are in context on every turn in Cursor:

- root `AGENTS.md`
- every `.cursor/rules/*.mdc` with `alwaysApply: true`
- every skill **description**
- every subagent **description**

`AGENTS.md` is one of four contributors, and the only one ADR-003 was watching.

The failure this creates is the one P4 exists to prevent, arriving through an unwatched door. A
budget on one input while three grow freely is not a budget — it is a budget-shaped object that
produces a green signal while the thing it protects degrades. That is strictly worse than no
budget, because it is trusted.

## Decision

The budget is enforced against the **enumerated always-on set**, not against `AGENTS.md` alone.
The CI check must resolve and sum all four sources: it has to know which rule files are
`alwaysApply`, and it has to extract description fields from skills and subagents rather than
counting whole files.

`AGENTS.md` keeps 150 as a **sub-budget**. The total is set at `M1-02`, when the other three can
actually be counted — setting it now would be guessing at a number we are about to be able to
measure.

## Consequences

- **The check is real work, not a line count.** It has to parse frontmatter across three file
  types and follow the discovery matrix. That cost is the price of the budget meaning anything.
- **Glob-scoped rules are free at rest**, since they are not always-on. This is a genuine and
  unplanned advantage of [ADR-009](ADR-009-adapter-layer-rebuilt-on-measurement.md)'s decision to
  put path-scoped content in `.cursor/rules/` globs: that content costs nothing until the agent
  works the matching path. It is progressive disclosure obtained mechanically rather than by
  asking an agent to be disciplined.
- **The always-on set is tool-specific and measured**, so this check is coupled to the discovery
  matrix and must be revisited whenever the matrix is re-run — quarterly, and on any major tool
  release.
- **Adding a skill or a subagent now costs budget.** That is correct and was previously invisible:
  every skill description is always-on, so a repository accumulating skills is accumulating
  always-on context whether or not anyone notices.
- The ratchet at `M5-02` applies to the total, not to `AGENTS.md`, for the same reason.

## Alternatives rejected

- **Keep the `AGENTS.md`-only budget.** Caps one input and leaves three growing — the accretion
  failure the budget exists to prevent, made invisible by a passing check.
- **Budget each source separately.** Four numbers to defend instead of one, and it permits the
  total to grow while every individual check passes.
- **Drop the budget.** Contradicts P4, which rests on measured instruction-adherence collapse.

## Revisit when

The discovery matrix changes — a tool update altering what is always-on changes the denominator,
and the number must be re-derived rather than carried forward.
