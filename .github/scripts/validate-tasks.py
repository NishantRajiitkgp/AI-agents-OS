#!/usr/bin/env python3
"""Validate task files against the task schema.

PROVISIONAL. Moves into `aios check` at M1-14, per ADR-006.

Scope is one file against its own schema: field vocabulary, the state machine, the line cap.
Whether `satisfies` names a live requirement and whether `blocked_by` names a real task is
validate-references.py, because no single file can know either.

The field list is closed. An unknown field is an error rather than a warning, because the
failure it prevents is schema drift by accretion: a slot appears, agents fill it, and later
nobody can say which fields anything reads. Every field in the design was argued for
individually; anything else has not been.

Exit codes: 0 valid, 1 violations, 2 could not run.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aios_state import (
    REQ_ID, TASK_ID, CouldNotRun, load_config, load_tasks, relative, state_dir,
)

REQUIRED = {"id", "title", "status", "satisfies", "priority", "risk",
            "touches", "acceptance", "verify"}
OPTIONAL = {"blocked_by", "constraints", "parent", "waiting_on", "reason", "duplicate_check"}
KNOWN = REQUIRED | OPTIONAL

# Past `todo` the search should already have happened, so the record is required from the
# point work starts rather than at the point it is submitted — by then the duplicate is
# written and removing it costs more than the check would have.
NEEDS_DUPLICATE_CHECK = {"doing", "review", "done"}

# Named individually so the message can say what was cut and why, rather than "unknown".
# The difference is between someone re-adding it and someone learning why it is not there.
CUT = {
    "estimate", "story_points", "storypoints", "points", "complexity", "effort",
    "assignee", "owner", "sprint", "epic", "labels", "tags", "due_date", "due",
}

STATUSES = {"todo", "doing", "review", "done", "waiting", "dropped"}
RISKS = {"low", "medium", "high"}
LIST_FIELDS = ("satisfies", "touches", "acceptance", "verify", "blocked_by", "constraints",
               "duplicate_check")

violations: list[str] = []


def check(task: dict, cap: int) -> None:
    path, data = task["path"], task["data"]
    where = relative(path)

    if not TASK_ID.match(path.stem):
        violations.append(
            f"{where}: filename is not a task ID. Everything under tasks/ is a task file; "
            f"notes and scratch belong elsewhere.")

    if task["lines"] > cap:
        violations.append(
            f"{where}: {task['lines']} lines, cap is {cap}. A task needing more than that is "
            f"two tasks, or its context belongs in a requirement or an ADR.")

    if task["error"]:
        violations.append(f"{where}: {task['error']}")
        return

    for field in sorted(set(data) - KNOWN):
        if field in CUT:
            violations.append(
                f"{where}: field {field!r} was considered and deliberately cut. It is not a "
                f"field the schema forgot.")
        else:
            violations.append(f"{where}: unknown field {field!r}; the field list is closed")
    for field in sorted(REQUIRED - set(data)):
        violations.append(f"{where}: required field {field!r} is missing")

    task_id = str(data.get("id", ""))
    if not TASK_ID.match(task_id):
        violations.append(f"{where}: id {task_id!r} is not T- plus four or six hex characters")
    elif path.stem != task_id:
        violations.append(f"{where}: id {task_id!r} does not match the filename")

    status = data.get("status")
    if status is not None:
        if status not in STATUSES:
            violations.append(f"{where}: status {status!r} is not one of {sorted(STATUSES)}")
        elif status == "waiting" and not str(data.get("waiting_on") or "").strip():
            violations.append(
                f"{where}: status 'waiting' requires waiting_on. `waiting` exists only for "
                f"blockers outside the repository, which nothing can derive.")
        elif status == "dropped" and not str(data.get("reason") or "").strip():
            violations.append(f"{where}: status 'dropped' requires a reason")

    if "waiting_on" in data and status != "waiting":
        violations.append(f"{where}: waiting_on is set but status is {status!r}")

    # M4-04. Duplication rises and refactoring falls under AI assistance, and the counter is
    # looking before writing. A machine cannot make anyone search; it can refuse a task that
    # claims to be underway without a record of having done so.
    if status in NEEDS_DUPLICATE_CHECK:
        entries = [str(e).strip() for e in (data.get("duplicate_check") or []) if str(e).strip()]
        if not entries:
            violations.append(
                f"{where}: status {status!r} requires duplicate_check. Record what was "
                f"searched for and what it found before writing something that may already "
                f"exist. 'nothing found' is a valid entry; an absent field is not.")
        else:
            for entry in entries:
                if "—" not in entry and " - " not in entry:
                    violations.append(
                        f"{where}: duplicate_check entry {entry!r} does not say what was "
                        f"found. Use '<what was searched> — <what was found>', so the record "
                        f"is evidence rather than an assertion that looking happened.")

    priority = data.get("priority")
    if priority is not None and (not isinstance(priority, int) or isinstance(priority, bool)
                                or not 1 <= priority <= 3):
        violations.append(f"{where}: priority {priority!r} is not an integer from 1 to 3")

    risk = data.get("risk")
    if risk is not None and risk not in RISKS:
        violations.append(f"{where}: risk {risk!r} is not one of {sorted(RISKS)}")

    for field in LIST_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if not isinstance(value, list):
            violations.append(f"{where}: {field} must be a list")
            continue
        if field in REQUIRED and not value:
            violations.append(f"{where}: {field} must not be empty")
        for i, item in enumerate(value):
            if not isinstance(item, str) or not item.strip():
                violations.append(f"{where}: {field}[{i}] must be a non-empty string")

    for i, req in enumerate(data.get("satisfies") or []):
        if isinstance(req, str) and not REQ_ID.match(req):
            violations.append(f"{where}: satisfies[{i}] {req!r} is not a requirement ID")
    for i, dep in enumerate(data.get("blocked_by") or []):
        if isinstance(dep, str) and not TASK_ID.match(dep):
            violations.append(f"{where}: blocked_by[{i}] {dep!r} is not a task ID")

    parent = data.get("parent")
    if parent is not None and not TASK_ID.match(str(parent)):
        violations.append(f"{where}: parent {parent!r} is not a task ID")

    if not task["body"].strip():
        violations.append(f"{where}: no body. The frontmatter says what; the body says why.")


def main() -> int:
    # Overridable so the gate can be exercised against deliberately broken fixtures.
    override = "--dir" in sys.argv
    try:
        directory = (Path(sys.argv[sys.argv.index("--dir") + 1]) if override
                     else state_dir("tasks"))
        cap = 60 if override else load_config().get("budgets", {}).get("task_file_lines", 60)
        tasks = load_tasks(directory)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    if "--cap" in sys.argv:
        cap = int(sys.argv[sys.argv.index("--cap") + 1])

    for task in tasks:
        check(task, cap)

    for violation in violations:
        print(f"  violation: {violation}")
    print(f"\n{len(tasks)} task file(s), {len(violations)} violation(s). Cap {cap} lines.")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
