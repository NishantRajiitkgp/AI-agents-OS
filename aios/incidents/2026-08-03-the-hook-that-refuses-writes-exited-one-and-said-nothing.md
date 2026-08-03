---
date: 2026-08-03
detected_by: >-
  the editor, refusing four consecutive writes with an exit code and no other information
control: >-
  check-mode.py cannot exit non-zero from an unhandled path, and writes a traceback to
  .aios-hook-error.log when it fails, because its stderr reaches nobody
blocks_work: false
---

# 2026-08-03 — The control that refuses writes refused them all, and could not say why

**Severity:** low in effect, and it is the third incident in this repository with this shape.
**Detected by:** four consecutive `Write` calls refused with
`Hook "python aios/bin/hooks/check-mode.py" failed with exit code 1`.

## What happened

`check-mode.py` is registered `preToolUse` with `failClosed: true`, so when it exits non-zero
the editor refuses the write. It began exiting 1 partway through a working session. Editing
files became impossible; the commit that was in progress had to be made by piping the message
into `git commit -F -` instead of writing a file.

Exit 1 is not a decision this script has. Its decisions are 0 for allow, 0 with a JSON denial
for a refusal Cursor honours, and 2 for the Claude Code shape. Exit 1 is what Python does when
an exception escapes `main`.

## Why it took so long to get anywhere

Everything available to look at said the hook was fine.

Run by hand against a synthetic event, it exited 0 in about 300 milliseconds, five times
running, against a 10-second timeout — so neither a hang nor a slow machine. Its two guarded
regions, reading the event and deciding, both convert a failure into *allow with a warning*,
which is the policy the two earlier incidents produced. And the invocation that failed had
written the lease file, so it had run past the middle of `decide` before dying.

What was left is the part nobody had guarded: answering. `respond.allow` and `respond.deny`
were called outside every `try`, as was the module-level entry point, and an exception in
either is indistinguishable from a refusal — the editor reports a number either way.

The deeper problem is that the hook's stderr goes nowhere a person can read. The editor
surfaces the exit code and discards the rest, so a traceback, if there was one, was written to
a stream with no reader. Three incidents here now have the same root: a control that fails
invisibly and reports the failure as a refusal.

## Resolution

Two changes, both about the failure rather than the cause.

The reply is wrapped, and the module entry point has a last-resort handler that logs and exits
0. After this the script has no path to a non-zero exit that is not a deliberate Claude Code
denial, which is what `failClosed: true` was always assuming and never true.

And when it fails it appends a traceback to `.aios-hook-error.log` beside the repository. A
file is the only channel out. It is git-ignored, because it is a fact about one machine's
afternoon and not about the project.

## What this does not fix

**The cause is still unknown.** Nothing was captured before the guard existed, and the fault
has not recurred since. If it returns, the log will name it; if it returns and the log stays
empty, the cause is not an exception at all — the process is being killed, or the interpreter
is failing to start — and that is a different investigation with a different first step. That
distinction is the whole value of the change, and it is worth being plain that a containment
improvement is not a diagnosis.

**`failClosed: true` is still the setting**, and it is still right. This hook's matcher is
`Write`, so a failure leaves the terminal working and the repository repairable — the property
`.cursor/hooks.json` chose it for, and the reason `deny-commands.py` is registered the other
way. What the incident shows is not that fail-closed was wrong; it is that a fail-closed
control has to be *total*, and this one had three exits it had never accounted for.

## The one that got away twice

While diagnosing this, the hook was run by hand with an invented session id — twice — and each
run took the write lease in the real repository under that invented identity, refusing the next
genuine edit until the file was deleted. That is
[2026-08-02](2026-08-02-a-test-took-the-write-lease-in-the-real-repository.md) exactly, from a
different direction: the earlier one was a test doing it, this was a person debugging. The
control that incident produced protects the test suite. Nothing protects a terminal, and the
honest fix is a way to exercise the hook that cannot touch the real lease — which is a task,
not a paragraph here.
