#!/usr/bin/env python3
"""`aios board` (M5-08). The work, rendered.

PROVISIONAL. Moves into the binary at `M1-08`.

Written to stdout, regenerated on demand, and gitignored if ever written to a file. That last
part is the whole design: **a generated view can be wrong for a moment; a stored one can be
wrong forever.** A board file committed to the repository is a second source of truth about
task state that drifts from the task files the instant anyone forgets to regenerate it — and
it will look authoritative while it does, because it is checked in.

The board is derived entirely from `aios/tasks/`. It stores nothing, caches nothing, and has
no state of its own to disagree with.

Exit 0 always, unless it could not run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from aios_state import CouldNotRun, load_tasks, state_dir

PASS, COULD_NOT_RUN = 0, 2

# Column order is the state machine's order, so a board read left to right is work read in the
# direction it moves. `waiting` and `dropped` sit apart because they are not progress.
COLUMNS = ["todo", "doing", "review", "done"]
ASIDE = ["waiting", "dropped"]


def blocked_by_open(task: dict, by_id: dict[str, dict]) -> list[str]:
    """Blocked is derived, never stored (P3). Storing it lets it disagree with itself."""
    return [dep for dep in (task["data"].get("blocked_by") or [])
            if by_id.get(dep, {}).get("data", {}).get("status") != "done"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--width", type=int, default=96)
    args = parser.parse_args()

    try:
        directory = (args.root / "aios" / "tasks") if args.root else state_dir("tasks")
        tasks = [t for t in load_tasks(directory) if t["error"] is None]
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    by_id = {t["data"].get("id"): t for t in tasks}
    grouped: dict[str, list[dict]] = {}
    for task in tasks:
        grouped.setdefault(task["data"].get("status", "todo"), []).append(task)

    print(f"aios board — {len(tasks)} task(s), generated, stored nowhere\n")

    for column in COLUMNS + ASIDE:
        entries = grouped.get(column) or []
        if not entries and column in ASIDE:
            continue
        print(f"{column.upper()}  ({len(entries)})")
        for task in sorted(entries, key=lambda t: (-(t["data"].get("priority") or 0),
                                                   t["data"].get("id") or "")):
            data = task["data"]
            blocked = blocked_by_open(task, by_id)
            flags = []
            if blocked:
                flags.append(f"blocked by {', '.join(blocked)}")
            if data.get("waiting_on"):
                flags.append(f"waiting on {data['waiting_on']}")
            if (data.get("risk") or "") == "high":
                flags.append("high risk")
            title = str(data.get("title") or "")[:args.width - 30]
            print(f"  {data.get('id', '?'):<10} p{data.get('priority', '-')} {title}")
            if flags:
                print(f"  {'':<10} {' · '.join(flags)}")
        print()

    if not tasks:
        print("No readable tasks. The board is a view; there is nothing behind it yet.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
