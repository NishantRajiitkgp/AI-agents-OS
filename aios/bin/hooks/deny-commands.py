#!/usr/bin/env python3
"""Refuse commands on the deny list, as a `preToolUse` hook matching Shell calls.

Registered against `preToolUse`, not `beforeShellExecution`. The first attempt used the latter
and refused every command in the editor, because its documented `{command, cwd, sandbox}` on
stdin was not what arrived — stdin was empty. `M4-03` then measured `preToolUse` carrying the
command at `tool_input.command`, so the deny list rides the event shape that was observed
rather than the one that was documented. Both shapes are still accepted, so re-registering it
cannot silently turn it into a hook that allows everything.


PROVISIONAL. Becomes `aios hook before-shell` when the binary exists (ADR-006). It is Python
rather than a shell script for the reason ADR-006 records: PowerShell script execution is
blocked by Group Policy on the development machine, so a .ps1 hook would silently never run.

Cursor's IDE agent has no repo-level command deny list, so a hook is the only checked-in
artifact that can refuse a command there at all (ADR-012). Registered in `.cursor/hooks.json`
with `failClosed: true`, so a crash, a timeout or malformed output blocks rather than passes.

This layer is Advisory. It catches the obvious slip; it does not contain a determined agent,
and it is not what makes the system safe. See ADR-012 for why polishing these patterns is the
wrong place to spend effort.

Two modes:
  (no arguments)      hook protocol — reads a JSON event on stdin, writes a JSON decision
  --command "..."     check one command; exit 1 if denied, 0 if allowed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

# The config loader lives with the other provisional scripts. Importing it rather than
# re-reading config.yml here keeps one definition of where configuration is found — the same
# reason the validators share a parser. Both halves move into the binary together.
sys.path.insert(0, str(ROOT / ".github" / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

try:
    import respond
    from aios_state import CouldNotRun, load_config
except ImportError as exc:  # pragma: no cover - only if the tree is broken
    # Allow, for the reason given at the same decision further down: this hook matches Shell,
    # and a broken tree that refuses every command cannot be repaired from the terminal.
    print(json.dumps({"permission": "allow"}))
    print(f"aios deny list could not load, so it did not apply: {exc}", file=sys.stderr)
    raise SystemExit(0)


def patterns() -> list[tuple[str, re.Pattern[str]]]:
    """Compile the deny list, skipping nothing silently.

    A pattern that does not compile is fatal. The alternative — dropping it and carrying on —
    produces a deny list that is quietly shorter than the one in the file, which is the exact
    failure mode where a control looks present and is not.
    """
    raw = load_config().get("deny_commands") or []
    compiled: list[tuple[str, re.Pattern[str]]] = []
    for entry in raw:
        if not isinstance(entry, str):
            raise CouldNotRun(f"deny_commands entry is not a string: {entry!r}")
        try:
            compiled.append((entry, re.compile(entry, re.IGNORECASE)))
        except re.error as exc:
            raise CouldNotRun(f"deny_commands entry {entry!r} is not a valid regex: {exc}")
    return compiled


def first_match(command: str) -> str | None:
    for source, rx in patterns():
        if rx.search(command):
            return source
    return None


def decide(command: str) -> tuple[bool, str | None]:
    if not command.strip():
        return True, None
    hit = first_match(command)
    return hit is None, hit


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", help="check one command instead of reading an event")
    args = parser.parse_args()

    if args.command is not None:
        try:
            allowed, hit = decide(args.command)
        except CouldNotRun as exc:
            print(f"could not run: {exc}", file=sys.stderr)
            return 2
        if allowed:
            print("allowed")
            return 0
        print(f"denied by deny_commands entry: {hit}")
        return 1

    event: dict = {}
    try:
        # A line, not to end-of-stream. `read()` waits for EOF, which never arrives if the
        # caller holds the pipe open — measured, and the cause of an outage recorded in
        # aios/incidents/2026-08-02. Stripped of the BOM Cursor prefixes, also measured.
        raw = sys.stdin.buffer.readline().decode("utf-8-sig").strip()
        event = json.loads(raw) if raw else {}
        # Two shapes, because the hook was written against `beforeShellExecution` and is
        # registered against `preToolUse`. M4-03 measured the latter carrying the command at
        # `tool_input.command`; accepting both means re-registering it does not silently turn
        # it into a hook that allows everything.
        command = str((event.get("tool_input") or {}).get("command")
                      or event.get("command") or "")
        allowed, hit = decide(command)
    except (json.JSONDecodeError, UnicodeDecodeError, CouldNotRun) as exc:
        # Allow, loudly. This reverses the earlier decision to deny here, and the reversal was
        # forced by watching it happen: a half-written config.yml made this hook undecidable,
        # every shell command in the editor was refused, and the config could only be repaired
        # through the editor's write tool because the terminal was gone. That is the M2-08
        # outage a second time, in the one place hooks.json predicted it — a Shell matcher has
        # no repair path through the shell.
        #
        # Denying here would be right for a control that is the containment. This one is not:
        # ADR-012 puts it at Advisory, because a repo-level list cannot narrow what a developer
        # has already permitted, and server-side required review is what actually contains an
        # agent. Trading away the ability to fix a broken repository to harden a layer that was
        # never load-bearing is a bad trade, and the failure is not silent — it prints.
        print(f"aios deny list could not evaluate, so it did not apply: {exc}", file=sys.stderr)
        return respond.allow(event)

    if allowed:
        return respond.allow(event)

    return respond.deny(
        event,
        f"Blocked by the aios deny list: {hit}",
        f"This command matches the deny list entry {hit!r} in aios/config.yml and was "
        f"refused. Do not attempt a variation that evades the pattern. If the task genuinely "
        f"requires it, stop and say so — this is one of the conditions where halting and "
        f"reporting is the correct action.")


if __name__ == "__main__":
    raise SystemExit(main())
