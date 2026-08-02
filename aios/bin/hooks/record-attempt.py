#!/usr/bin/env python
"""Record test outcomes, so the three-strikes stop is observed rather than self-reported.

PROVISIONAL. Moves into the binary with the rest of the hook logic (ADR-006, Q-005).

M4-06's most interesting hard stop is: **the same test has failed three times with three
different fixes**. Past three attempts the agent is guessing, and guessing near a test is one
hop from weakening it. The value of the rule is that it fires at the exact moment the
incentive to cheat appears — which means the count cannot be something the agent maintains
about itself. A counter you increment voluntarily is a counter you can decline to increment.

`postToolUse` is the only measured event carrying an outcome
([record](../probe/results/hook-event-2026-08-01.md)), so this runs there and writes a ledger
that `check-mode.py` reads before permitting the next write.

**The verdict comes from the output text, not the exit code.** The measurement showed
`exitCode` is the shell's, not the command's: a Python process exiting 1 inside a PowerShell
block reported 0. A detector trusting that field is wrong whenever the command is wrapped,
which is most of the time here.

Observes and records. Never denies — `postToolUse` cannot deny anything anyway, and the
refusal belongs at the write, which is the moment that matters.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

LEDGER = ".aios-attempts"

# A command that runs tests. Deliberately narrow: a false positive here stops real work, and
# the design's own warning about deny lists applies — a control that fires on `git status`
# gets switched off, taking the control with it.
TEST_COMMAND = re.compile(
    r"\b(unittest|pytest|jest|vitest|go\s+test|cargo\s+test|mocha|rspec|phpunit)\b")

# The runner's own verdict. Each of these is a runner saying it failed, in its own words.
FAILED = re.compile(
    r"\b(FAILED|FAIL:|ERROR:|AssertionError|\d+\s+failed|failures=[1-9]|test result:\s*FAILED)\b")
PASSED = re.compile(r"\b(OK|PASSED|\d+\s+passed|test result:\s*ok)\b")


def target(command: str) -> str:
    """What was under test, so failures of *different* tests do not accumulate together.

    The last path- or dotted-module-looking argument, falling back to the runner's name. It
    does not have to be perfect: over-grouping stops early, which is the safe direction, and
    under-grouping is what a bare runner name gives.
    """
    candidates = re.findall(r"[\w./\\-]*tests?[\w./\\-]*", command)
    if candidates:
        return max(candidates, key=len).replace("\\", "/").strip("./")
    match = TEST_COMMAND.search(command)
    return match.group(1) if match else "tests"


def main() -> int:
    try:
        # A line, not to end-of-stream. `read()` waits for EOF, which never arrives if the
        # caller holds the pipe open — measured, it hangs where `readline()` returns at once.
        # This one is fail-open, so a hang costs a lost observation rather than an outage, but
        # a hook that stalls the tool call it observes is its own problem.
        event = json.loads(sys.stdin.buffer.readline().decode("utf-8-sig").strip())
    except Exception:
        return 0  # an observer that cannot read its input records nothing and blocks nothing

    if event.get("tool_name") != "Shell":
        return 0

    command = (event.get("tool_input") or {}).get("command", "")
    if not TEST_COMMAND.search(command):
        return 0

    raw = event.get("tool_output") or ""
    try:
        output = json.loads(raw).get("output", "") if raw.startswith("{") else raw
    except Exception:
        output = raw

    if FAILED.search(output):
        verdict = "FAIL"
    elif PASSED.search(output):
        verdict = "PASS"
    else:
        return 0  # no verdict is not a pass; recording a guess would corrupt the count

    root = os.environ.get("CURSOR_PROJECT_DIR") or event.get("cwd") or os.getcwd()
    try:
        with (Path(root) / LEDGER).open("a", encoding="utf-8") as handle:
            handle.write(f"{verdict} {target(command)}\n")
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
