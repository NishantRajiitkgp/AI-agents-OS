# ADR-011 — The always-on budget is 200 lines, with 150 of it reserved for `AGENTS.md`

**Status:** accepted
**Date:** 2026-07-31
**Decides:** the total left open by
[ADR-010](ADR-010-budget-covers-the-measured-always-on-set.md). **Closes `P0-4`'s reopening.**

## Context

ADR-010 established that the budget is enforced against the enumerated always-on set rather
than against `AGENTS.md` alone, and deliberately deferred the total: setting it before the
other three contributors could be counted would have been guessing at a number that was
about to become measurable.

`M1-02` made them countable. The set as measured today, by the same counter the gate uses:

| Source | Lines |
|---|---|
| `AGENTS.md` | 106 |
| `.cursor/rules/` marked `alwaysApply` (one file) | 25 |
| Skill descriptions in the repository | 0 |
| Subagent descriptions in the repository | 0 |
| **Total** | **131** |

## Decision

**200 lines total**, with `AGENTS.md` keeping **150** as a sub-budget.

The total is not derived from evidence about where adherence degrades — no such number
exists at this granularity, and inventing one would violate P8. It is derived from the
structure it has to hold: the 150 that ADR-003 set for `AGENTS.md` and that ADR-010 kept,
plus 50 for everything else that is always-on. That leaves 69 lines of headroom against
today's 131.

What makes the number work is not its precision. It is that it is fixed, enforced before
merge, and small enough that the next addition has to argue against an existing line rather
than append. A budget nobody ever hits is decoration.

## Consequences

- **The two subagents at `M2` are the first real draw.** `explorer` and `verifier` contribute
  their descriptions, not their bodies. If the pair costs more than a few lines each, the
  description format is wrong and should be fixed rather than the budget raised.
- **Raising the total requires superseding this ADR.** That is the intended friction. The
  failure mode being prevented is a budget quietly widened to fit whatever was just written,
  which is indistinguishable from having no budget while looking responsible.
- **The check must resolve the set, not count a file.** It parses frontmatter to find which
  rules are `alwaysApply` and extracts description fields rather than whole files. That is
  real work and is the price of the number meaning anything.
- **Trimming `.cursor/rules/no-presumed-stack.mdc` from 45 lines to 25 was part of this
  task.** It was also factually wrong — it stated that no language or CI host had been
  chosen, which ADR-005 and ADR-002 had already contradicted. Always-on context asserting
  the opposite of the decision record is the most expensive kind of stale, because it is
  read on every turn and outranks what the agent would otherwise find by looking.

All counts in this ADR are `wc -l`, matching the gate. A count that differs from the one
being enforced is a number that starts an argument rather than settling one.

## The measurement's known gap

The budget covers what the **repository** controls. It cannot see user-level skills and
subagents installed on a developer's machine, which the M0 probe confirmed are also always-on
and which no repository check can reach.

So the enforced number is a floor on the true always-on set, not the whole of it. This is
recorded rather than solved because the alternative — pretending repository-scoped
enforcement is complete — would make the check misleading in exactly the way ADR-010 objected
to. A developer with a large personal skill library is carrying more always-on context than
this gate reports, and that is invisible to CI by construction.

## Alternatives rejected

- **Set the total at 150.** Would make `AGENTS.md`'s own sub-budget unreachable, since the
  rules already consume 26. A budget that cannot be spent as documented is a bug.
- **Set it at today's 133, with no headroom.** Forces a deletion for the very next line
  added, including the M2 subagents that are already planned. A budget that blocks planned
  work on day one gets raised on day two, which teaches that it can be raised.
- **Derive it from a context-window fraction.** Looks principled and is not: the degradation
  evidence is about adherence over long contexts generally, and does not support a specific
  line count for a specific model. It would be a number nobody can produce honestly (P8).

## Revisit when

The discovery matrix is re-run and changes what is always-on, per ADR-010's own trigger; or
when the total has sat at the limit for a quarter with every addition displacing something
useful, which would be evidence the ceiling is too low rather than the content too fat.
