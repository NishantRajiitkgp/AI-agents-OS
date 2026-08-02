# ADR-007 — The `.claude/` adapter tree is deferred until a second tool can verify it

**Status:** accepted
**Date:** 2026-07-31
**Arose from:** `M0-03`, tool unavailable

## Context

Only Cursor is available on the target machine. Claude Code is not installed and may or may not
be later.

[D-001](../design/10-decision-register.md#d-001--tool-agnostic-core-with-thin-adapters)
locates the adapter layer's entire value in cross-tool portability, and rejected "Cursor-native
only" because the market leader has changed twice. That reasoning is about vendor risk over time
and does not depend on owning two tools today, so it survives intact.

What does not survive is the `.claude/` tree itself. Building a vendor adapter that can never be
exercised produces exactly the artifact
[D-005](../design/10-decision-register.md#d-005--probe-the-adapter-discovery-matrix-instead-of-documenting-it)
exists to prevent: something authoritative-looking and unverified. The whole reason that decision
replaced a prose discovery matrix with a probe was that unverifiable claims about tool behaviour
go stale while still being believed.

## Decision

The **core stays tool-agnostic**: `AGENTS.md` at root, nested `AGENTS.md` for path scoping, and
all logic in `aios/bin/` as binary subcommands. Those are the cross-tool primitives and they are
unaffected.

**No `.claude/` directory ships at M1.** `.cursor/` holds only genuinely Cursor-specific settings
and stays near-empty exactly as D-001 requires.

## Consequences

1. **D-001 is not superseded.** It is honoured in the part that carries its value — the core — and
   deferred in the part that cannot currently be checked. No ADR supersedes it and none should.

2. **The probe keeps its `.claude/` markers.** Whether *Cursor* reads that tree is still worth
   measuring, because it determines how the adapter gets built when a second tool arrives. The
   files stay staged for `M0-02`.

3. **Subagent placement is now probe-dependent.** `03 §3.6` puts `explorer` and `verifier` in
   `.claude/agents/`. The provisional Protocol A reading suggests Cursor does not read that
   location, so `M4-01` and `M4-02` must place them wherever the probe says Cursor actually
   looks — not where the design assumed. If that provisional reading is confirmed, this is a
   correction to `03 §3.6`, not an implementation detail.

4. **Accepted risk: retrofitting costs more than building now.** The mitigation is structural
   rather than hopeful — the core carries all the content, so an adapter that only ever points at
   it is cheap to add later. That is precisely why D-001 forbids adapters from holding knowledge.

5. This is the same deletion-by-default posture that
   [09 §4](../design/09-maintenance-and-evolution.md#4-tracking-the-host-tools)
   requires quarterly. Applying it at construction time rather than only at maintenance time is
   consistent, and cheaper.

## Alternatives rejected

- **Build the `.claude/` tree anyway on D-001's reasoning.** Ships an adapter nobody has ever
  exercised. D-041 rejected "support all major ecosystems from day one" for the identical reason:
  a matrix mostly unexercised is therefore untrustworthy.
- **Go Cursor-native and drop tool-agnosticism.** Requires superseding D-001 and accepts vendor
  lock-in in a market that has changed leaders twice. It also buys very little, since the core
  primitives are cross-tool standards that Cursor reads anyway — the lock-in would be paid for
  no saving.

## Revisit when

Any second tool becomes available — Claude Code or otherwise. At that point run the full probe
and build the adapter against measured behaviour rather than against this document. Until then
`M0-03` stays open as a deferral, and the Claude Code column of the discovery matrix reads
**`not measured`**, which is a different fact from `no` and must never be collapsed into it.
