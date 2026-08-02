---
date: 2026-08-02
detected_by: >-
  the write hook refusing an ordinary edit, reported as exit code 1
control: >-
  both hooks read a line rather than to end-of-stream, decide() cannot escape as an exception,
  and anything invoking a hook names a root it owns
blocks_work: false
---

# A test took the write lease in the real repository

**Date:** 2026-08-02 · **During:** `M5-01` · **Detected by:** the fail-closed write hook
refusing an ordinary edit

## What happened

A routine edit to `task.md` was refused. The editor reported the `preToolUse` hook as having
**failed with exit code 1**, and that reading sent the diagnosis in the wrong direction for
some time: a refusal exits 0 and carries a JSON denial, so this looked like the control
crashing.

It was not that either, and the intermediate conclusion written here first — that Cursor
renders a denial as an exit-1 failure — was wrong. Releasing the lease made one retry succeed,
which looked conclusive; the block then recurred with the lease held by the writing session
itself, the state in which the hook demonstrably allows. Run directly, with the same event and
the same on-disk state, it exited 0 five times out of five.

**The hook was not failing. It was hanging.** The measured contract records the payload as
"one JSON object, BOM-prefixed, CRLF-**terminated**", and terminated says nothing about the
pipe being closed. `read_event` called `sys.stdin.buffer.read()`, which waits for
end-of-stream. Given a caller that writes the line and holds the pipe open, that wait never
ends: measured side by side on identical input, `read()` was still running after four seconds
where `readline()` returned in 0.3. The 10-second timeout then fired and the editor reported
an exit code, which is a truthful description of the process and a misleading description of
the fault — it names a crash, and the hook had not crashed.

Two better-looking hypotheses were measured and killed on the way past, which is cheaper than
reasoning about them: the hook costs 0.5s against its timeout, and a 140KB whole-file payload
changes neither the timing nor the result. The read itself was the last thing anyone thought
to test, having been "measured" once and treated as settled ever since.

What was actually being refused was correct. `.aios-writer` — the one-writer-per-worktree lease
added hours earlier in `M4-11` — was held by a session that had never existed as an agent. The
test suite had put it there, and the diagnostic runs chasing it then did the same under their
own session ids, which is why it recurred.

`tests/test_hook_registration.py` invoked `check-mode.py` with `cwd=ROOT` and no root override.
Every other test that runs a hook passes `CURSOR_PROJECT_DIR` pointed at a temporary directory;
this one did not, so the hook resolved the **real repository**, found no lease, and took one in
the name of a synthetic test event. From then on the genuine session looked like a second
concurrent agent and was refused, correctly, by a rule doing exactly what it was written to do.

## Why it is worth recording

The bug is ordinary — a test with a side effect on the thing it tests. Two things about it are
not.

**The control was right and the input was wrong.** Nothing in `M4-11` misbehaved. That is the
harder failure to find, because every instinct points at the code that just changed and the
code that just changed was correct.

**A fail-closed hook was able to exit non-zero at all.** `check-mode.py` guarded its input
parsing and not its decision, so any exception inside `decide()` escaped, and `failClosed: true`
converts that into every write in the editor being refused until someone reads a stack trace.
This repository has now produced that outage twice before —
[once](2026-07-31-fail-closed-hook-blocked-every-command.md) from an unverified input contract
and [once](2026-08-01-editing-the-hook-blocked-every-write.md) from editing the hook mid-task.
Three times is a design defect, not three accidents.

## Controls

1. **`test_hook_registration.py` runs the hook against a scratch copy**, never the repository.
   The rule generalises: anything invoking a hook names a root it owns.
2. **`decide()` is wrapped.** An exception now produces allow-and-report, the same policy the
   unreadable-input path already had. A control that cannot decide says so; it does not convert
   its own defect into an outage. The guard is deliberately broad, because the failure it
   prevents is worse than the enforcement it skips — and the skip is announced rather than
   silent.
3. **Both hooks read a line, not to end-of-stream.** Tested two ways, because the behavioural
   test can only show the hook returns today: one test holds the pipe open and fails if the
   process is still alive, and one asserts `read()` has not come back. This almost certainly
   also explains the [first fail-closed
   outage](2026-07-31-fail-closed-hook-blocked-every-command.md), which was attributed at the
   time to an interpreter path and an unverified input contract — the contract was verified,
   and the half nobody checked was who closes the pipe.

## What is still true

The lease itself was not weakened. Two writing agents in one worktree are still refused, and
the residual gap recorded in `M4-11` — an agent that pauses longer than the window can be
displaced — is unchanged. What changed is that a *defect* in the control can no longer present
as a repository nobody can write to.
