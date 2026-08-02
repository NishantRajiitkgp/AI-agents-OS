# ADR-009 — The adapter layer, rebuilt on measurement

**Status:** accepted. **Supersedes [ADR-007](ADR-007-claude-adapter-deferred.md).**
**Date:** 2026-07-31
**Decides:** `M0-04`. Reopens [D-001](../design/10-decision-register.md#d-001--tool-agnostic-core-with-thin-adapters).

## Context

M0's probe measured what Cursor actually loads. Three things the design assumed turned out to be
wrong, and the measurements are in
[`probe/results/probe-2026-07-31.md`](../../aios/bin/probe/results/probe-2026-07-31.md).

1. **Nested `AGENTS.md` is not read by Cursor at all.** `03 §3.2` calls it "the portable
   path-scoping primitive." It was absent across three sessions spanning two hours — agent-edited,
   user-opened, and idle. A file written in the same minute *was* eventually picked up, which
   serves as a positive control ruling out indexing lag.

2. **`.cursor/rules/` glob rules work exactly as path scoping should.** `03 §3.2` calls this "the
   *wrong* place" for path-scoped rules and expects the directory to "stay nearly empty." The
   mechanism the design rejected is the one that functions.

3. **`.claude/` is not a Claude-Code-only tree.** Cursor reads skills, commands, and subagent
   definitions from it. ADR-007 deferred the whole tree on the grounds that a single-tool setup
   could not verify it; that premise is false.

## Decision

1. **Path-scoped knowledge lives in `.cursor/rules/*.mdc` with globs, holding content directly.**
   Nested `AGENTS.md` is not used.
2. **The `.claude/` tree ships.** `.claude/agents/` holds `explorer` and `verifier` as `03 §3.6`
   specifies — that section was right and the earlier contrary reading was an artefact of
   indexing lag.
3. **Root `AGENTS.md` remains the always-on core.** Measured to work; unchanged.

Direct content rather than a pointer: a pointer-style rule *was* measured to work, but from a
single sample by an agent that knew it was being probed, and it depends on the agent choosing to
act. Direct content is mechanical. `P2 > P1` in the design's own tiebreaker ordering — when
something can be either written or checked, check it.

## Consequences

- **`.cursor/rules/` is no longer near-empty, and the health signal built on that is retired.**
  `03 §3.2` offers "a nearly-empty vendor directory is the sign the adapter layer is working" as a
  diagnostic. It would now report failure while the layer works correctly, so it must be deleted
  rather than reinterpreted — a metric that has inverted is worse than no metric.
- **Path-scoped content is Cursor-specific and will duplicate when a second tool arrives.**
  Accepted and deferred on ADR-007's surviving logic: do not pay for portability you cannot
  verify. The pointer approach is the escape hatch, and it should be re-measured properly —
  unprimed, and more than once — at that point rather than adopted on this run's evidence.
- **D-001 is reopened, not superseded.** Its core claim holds for root `AGENTS.md` and fails for
  path-scoped content, and the measurement covers one tool. Reopening is the honest state.
- **Glob rules attach reactively.** They fire when the agent works a path, not at session start —
  measured present when the agent edited the file and absent when the file was merely open. So a
  path-scoped constraint is available when a file is touched but **not when the approach is being
  planned**. Anything that must shape the approach belongs in root `AGENTS.md` or in a gate.
- ADR-007 is superseded in full.

## Alternatives rejected

- **The pointer approach** — a glob rule containing only a path, with content in a nested file.
  Preserves one-home-per-fact and keeps the adapter a pure pointer, which is exactly what D-001
  wants. Rejected on evidence quality, not on principle: one observation, from a primed agent,
  measuring a behaviour `P1` specifically says is unreliable.
- **Drop path scoping entirely.** Gives up a capability that measurably works, and pushes
  everything into the always-on budget.
- **Keep nested `AGENTS.md` anyway**, on the grounds that it is portable and may work in other
  tools. This would ship a mechanism measured to do nothing in the only tool available — a rule
  that silently has no effect, which is the worst category of rule because it looks like a control.

## Revisit when

A second tool becomes available. At that point re-run the full probe, re-measure the pointer
approach properly, and decide whether the duplication cost of decision 1 has become real.
