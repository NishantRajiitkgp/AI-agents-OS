---
date: 2026-07-31
detected_by: >-
  every shell command in the editor being refused at once
control: >-
  the hook was unregistered until its input contract could be measured, which M2-10 then did;
  fail-closed controls are not registered against an unverified event shape
blocks_work: false
---

# 2026-07-31 — A fail-closed hook blocked every shell command in the editor

**Severity:** total loss of shell execution for the agent, twice, for two different reasons.
Self-inflicted, caught within seconds, and reverted from the same session.
**Detected by:** the very next command failing. There was no ambiguity and no silent period —
which is the one genuinely good property of what happened.

## What happened

`M2-08` required a command deny list at the tool layer. Research into Cursor's configuration
surface established that the IDE agent has no repo-level deny list, and that the only
checked-in artifact able to refuse a command is a `beforeShellExecution` hook in
`.cursor/hooks.json` ([ADR-012](../../docs/decisions/ADR-012-command-denial-is-asymmetric-across-tools.md)).
The hook was written, registered with `failClosed: true`, and the next shell command was
refused.

Two faults, discovered in sequence:

1. **The interpreter was named `python3`.** That name does not exist on this Windows machine.
   The hook produced no output, and `failClosed` did precisely what it promises: refused the
   command. Every command.
2. **With the interpreter corrected, the hook ran and received empty stdin**, rather than the
   documented `{command, cwd, sandbox}` event. It could not decide, returned a deny by
   design, and again refused every command.

The registration was withdrawn. The deny list, the matcher and its tests are unaffected and
remain in place; only the Cursor registration is gone.

## Why it mattered more than a broken script

Fault 1 is an ordinary portability bug and is the less interesting of the two.

Fault 2 is the one worth keeping. The hook's input contract came from **documentation, not
from measurement**, and the observed behaviour did not match it. That is the same mistake
[ADR-009](../../docs/decisions/ADR-009-adapter-layer-rebuilt-on-measurement.md) exists to
record: the entire adapter layer had to be rebuilt in M0 because assumptions about what
Cursor reads were wrong on contact with the tool. Two milestones later, the same assumption
was made again about a different Cursor surface, and was wrong again.

There is a pattern here worth naming, because it is now four for four. Every time this
repository has assumed a tool or environment behaviour instead of measuring it — PowerShell
execution policy, nested `AGENTS.md` discovery, the reachability of the Rust toolchain, and
now the hook event contract — the assumption has been wrong. The design's own principle
already says this. The failure is not knowing it; it is that knowing it did not stop the
fourth one.

A secondary observation: `failClosed: true` was the correct setting and it worked exactly as
intended. The outage was not caused by fail-closed. It was caused by registering a control
whose contract was unverified, and fail-closed is what made that visible in one second rather
than as a silently absent guardrail discovered months later. The right lesson is not "fail
open"; it is "do not register a fail-closed control you have not run once".

## Resolution

The hook is unregistered. `.cursor/hooks.json` now carries the explanation inline, including
an explicit instruction not to re-register without measuring first, and not to "fix" it by
setting `failClosed: false` — a fail-open hook converts any breakage into a control that is
silently absent, which is worse than the outage.

The deny list still has a real enforcement point: Claude Code's `.claude/settings.json`
`permissions.deny`, where the contract is known and the format is a data file rather than a
protocol.

## The control this produces

**A hook is run once, by hand, against a real event before it is registered.** The check is
one invocation and it would have caught both faults. `M2-10` now exists to measure Cursor's
actual `beforeShellExecution` event shape, and the registration waits on it.

This does not become a CI gate, and the reason is worth stating rather than glossing: CI
cannot observe what an editor sends to a hook on a developer's machine. The measurement is a
probe, like M0's, and the honest note is that probes are weaker than gates because they are
point-in-time. The compensating control is that the probe is re-run on the same schedule as
the M0 adapter matrix, since tool behaviour is exactly the thing that changes underneath.

## Addendum, 2026-08-01: fault 2 was probably not an empty stdin

`M4-03` needed a hook that refuses a *write*, so the event was finally measured rather than
read: [the record](../bin/probe/results/hook-event-2026-08-01.md). Cursor sends a complete,
well-formed JSON event on stdin — and **prefixes it with a UTF-8 byte-order mark**.

A strict UTF-8 parse raises on that BOM. A hook that handles "I could not parse this" as "I
received nothing" reports an empty stdin, which is what was recorded above, and then a
fail-closed hook refuses everything, which is what was seen. The payload was there the whole
time; the hook could not read it.

This does not change the lesson, it sharpens it. The contract really was different from the
documented one, and measuring really would have caught it — but what was wrong was one byte
of encoding, not a missing protocol. Two of this repository's four measurement failures are
now encoding faults, the other being the mojibake round-trip on the same day, and the fix
here is the one already used in `render-review-packet.py` for the same reason: `utf-8-sig`.

The original text above is left as written. It was an accurate account of what was observed
at the time, and an incident record that gets edited to look prescient stops being evidence.

## What this does not fix

Nothing prevents the same class of error for the *next* undocumented tool surface. The
general defence is the one the repository already had and did not apply here: when a tool's
behaviour is load-bearing, measure it before building on it, and record the measurement where
the next person will find it. The measurements live in `aios/bin/probe/results/`, and the
`beforeShellExecution` event shape belongs there once M2-10 has taken it.
