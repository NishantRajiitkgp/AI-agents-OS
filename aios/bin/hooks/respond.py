"""The one place that knows how each tool wants to be answered.

PROVISIONAL. Moves into the binary with the rest of the hook logic (ADR-006, Q-005).

M4-07's shape: hook *logic* lives here in `aios/bin/hooks/`, and each tool's settings file
holds a registration line pointing at it. Logic in one place drifts against itself; two
copies of a deny list drift against each other, and the copy nobody is looking at is the one
that goes stale.

That leaves exactly one thing that genuinely differs between tools, and this module is it.
The rest of a hook script is tool-agnostic and must stay that way.

## Why a branch and not one mechanism

Both tools' documentation says exit code 2 blocks. In Cursor it does not: a probe fired,
exited 2, and the write completed anyway
([record](../probe/results/hook-event-2026-08-01.md)). So:

- **Cursor** — `{"permission": "deny", "user_message": ..., "agent_message": ...}` on stdout,
  exit 0. Measured.
- **Claude Code** — exit code 2 with the reason on stderr. Documented, **not measured**,
  because Claude Code is not installed here (ADR-009). It is written to the documented
  contract and labelled as unverified rather than left out; leaving it out would mean the
  first person with Claude Code installed gets no control at all, which is worse than one
  that may need a correction. `M4-13` measures it.

The discriminator is `cursor_version`, present on every measured Cursor event and absent from
Claude Code's documented payload. Unknown callers get the Cursor shape *and* exit 0 — an
unrecognised tool must not be denied by accident, which is the fail-closed outage this
repository already had once.
"""

from __future__ import annotations

import json
import sys

CURSOR, CLAUDE, UNKNOWN = "cursor", "claude", "unknown"


def which_tool(event: dict) -> str:
    if event.get("cursor_version"):
        return CURSOR
    if event.get("transcript_path") or event.get("session_id"):
        return CLAUDE
    return UNKNOWN


def allow(event: dict, note: str | None = None) -> int:
    """Permit. Every tool treats exit 0 with no denial as permission."""
    if which_tool(event) != CLAUDE:
        payload = {"permission": "allow"}
        if note:
            payload["agent_message"] = note
        print(json.dumps(payload))
    elif note:
        print(note, file=sys.stderr)
    return 0


def deny(event: dict, user_message: str, agent_message: str) -> int:
    """Refuse, in whichever way the calling tool actually honours."""
    if which_tool(event) == CLAUDE:
        # Exit 2 is the documented block, and stderr is what reaches the agent.
        print(agent_message, file=sys.stderr)
        return 2
    print(json.dumps({"permission": "deny", "user_message": user_message,
                      "agent_message": agent_message}))
    return 0
