---
date: 2026-08-01
detected_by: >-
  the second edit to the hook being refused by the first
control: >-
  the preToolUse matcher stays scoped to Write, leaving Shell available as the recovery path;
  a fail-closed control gates one tool, never all of them
blocks_work: false
---

# 2026-08-01 — Editing the hook blocked every write, and the escape hatch held

**Severity:** total loss of the write tool for the agent, self-inflicted, caught on the next
action, repaired from the same session without external help.
**Detected by:** the very next edit failing, with the hook naming itself in the message.

## What happened

`M4-07` moves each hook's response into a shared module so both tools can register the same
script. The change to `check-mode.py` was two edits: one replacing the call, one adding the
import. The first landed. **The second was refused by the hook the first edit had just
broken.**

Between the two, `main()` called `respond.allow(...)` while `respond` was still the name of a
local function taking one argument. The hook raised, produced no output, and `failClosed: true`
did what it promises:

```
Tool blocked because this hook is configured to fail closed.
Hook "python aios/bin/hooks/check-mode.py" returned no output.
```

Every subsequent write was refused, including the one that would have fixed it.

## Why it did not become an outage

**The matcher is `Write`.** `Shell` was never gated, so the repair went through the terminal:
one Python one-liner removed the shadowing function and inserted the import, and a direct
invocation of the hook confirmed it answered before any tool call depended on it again.

That was not luck. `M4-03` scoped the matcher deliberately, and recorded the reason in
`.cursor/hooks.json` at the time: *a control whose failure mode locks you out of fixing it is
not a safety control.* This is that sentence being cashed. The design decision was made
against an imagined version of this incident and survived the real one.

## What is worth keeping

**A hook that governs the tool used to edit it is load-bearing for its own maintenance.** This
class of failure has no equivalent in a CI check: a broken CI script fails a build, whereas a
broken client hook removes the ability to repair itself. The properties that made it
survivable are worth stating as requirements rather than as accidents:

1. The matcher is as narrow as the control allows, so at least one tool is always ungated.
2. The ungated tool can edit files. `Shell` can, which is why gating `Write` alone is safe and
   gating both would not be.
3. The hook can be invoked directly, with a payload, without the editor — which is how it was
   confirmed fixed rather than hoped fixed.

**`failClosed: true` was right again.** The second time this repository has taken an outage
from it, and the second time it was the correct setting: the alternative is a control that
disappears without telling anyone. Both incidents were caused by registering or editing a
control without running it once, not by the setting.

## The control this produces

**A hook is invoked directly, with a real payload, immediately after any edit to it — before
the next tool call that depends on it.** One command. It would have caught this in the gap
between the two edits, and it would have caught both faults in the
[July incident](2026-07-31-fail-closed-hook-blocked-every-command.md).

This is deliberately not a CI gate. CI cannot observe an editor's hook on a developer's
machine, and a test that imports the script would not have caught this — the module imported
cleanly, and the fault was a name collision only reachable through `main()`. What catches it is
running the thing. `tests/test_hook_registration.py` now invokes `check-mode.py` as a
subprocess with a real event, which is the closest a test can get.

## What this does not fix

The edit that broke the hook was applied by the same tool the hook governs, and nothing
prevents that ordering. A safer sequence exists — unregister, edit, verify, re-register — and
it is three steps where one currently suffices. It is not adopted, because a procedure nobody
follows under time pressure is worse than a control that fails loudly and is repairable in one
command, which is what this is.
