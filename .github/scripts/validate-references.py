#!/usr/bin/env python3
"""Resolve the references between requirements and tasks.

PROVISIONAL. Moves into `aios check` at M1-14, per ADR-006.

The division of labour: validate-requirements.py and validate-tasks.py each check one file
against its own schema. This checks the things no single file can know — whether what it
points at exists, and whether an identifier is unique across the whole repository. A dangling
reference is the error shape that looks correct in every file and is wrong in aggregate.

The central rule is that **a `satisfies` resolving to no active requirement is a hard error,
not a skip**. This is the anti-invention control. A task satisfying nothing live is work
somebody made up, which is the observed failure where an agent generates plausible tasks no
requirement asked for and the backlog outgrows anyone's ability to audit it. Skipping such a
task would hide exactly the thing worth seeing.

Exit codes: 0 valid, 1 violations, 2 could not run.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aios_state import (
    REQ_ID, SUPERSEDED, TASK_ID, CouldNotRun, load_requirements, load_tasks, relative,
    state_dir,
)

violations: list[str] = []


def check_ids_unique(requirements: list[dict], tasks: list[dict]) -> None:
    seen: dict[str, str] = {}
    for req in requirements:
        at = f"{relative(req['file'])}:{req['line']}"
        if req["id"] in seen:
            violations.append(f"{req['id']}: defined at both {seen[req['id']]} and {at}")
        else:
            seen[req["id"]] = at
    for task in tasks:
        task_id = str(task["data"].get("id") or "")
        if not task_id:
            continue
        at = relative(task["path"])
        if task_id in seen:
            violations.append(f"{task_id}: defined at both {seen[task_id]} and {at}")
        else:
            seen[task_id] = at


def check_satisfies(tasks: list[dict], requirements: list[dict]) -> None:
    by_id = {req["id"]: req for req in requirements}
    for task in tasks:
        where = relative(task["path"])
        for req_id in task["data"].get("satisfies") or []:
            if not isinstance(req_id, str) or not REQ_ID.match(req_id):
                continue  # shape is validate-tasks.py's job
            req = by_id.get(req_id)
            if req is None:
                violations.append(
                    f"{where}: satisfies {req_id}, which does not exist. A task satisfying "
                    f"nothing is work nobody asked for.")
            elif req["status"] != "active":
                status = req["status"] or "(none)"
                violations.append(
                    f"{where}: satisfies {req_id}, whose status is {status!r}. "
                    f"Only an active requirement can justify work.")


def check_superseded(requirements: list[dict]) -> None:
    """A supersession trail that leads nowhere loses the history it exists to preserve."""
    known = {req["id"] for req in requirements}
    for req in requirements:
        match = SUPERSEDED.match(req["status"])
        if match and match.group(1) not in known:
            violations.append(
                f"{relative(req['file'])}:{req['line']} {req['id']}: superseded-by names "
                f"{match.group(1)}, which does not exist")


def check_task_refs(tasks: list[dict]) -> None:
    known = {str(t["data"].get("id")) for t in tasks if t["data"].get("id")}
    for task in tasks:
        where = relative(task["path"])
        for field in ("blocked_by", "parent"):
            value = task["data"].get(field)
            if value is None:
                continue
            for dep in (value if isinstance(value, list) else [value]):
                if not isinstance(dep, str) or not TASK_ID.match(dep):
                    continue  # shape is validate-tasks.py's job
                if dep not in known:
                    violations.append(f"{where}: {field} names {dep}, which does not exist")


# Link resolution used to live here and ran over requirement and task files only — about a
# twentieth of the markdown in this repository, and not the part an agent reads every turn. It
# moved to `check-memory.py` (M5-01) rather than being copied, so the rule still has exactly
# one implementation and now covers the instruction layer as well.


def main() -> int:
    # Overridable so the gate can be exercised against deliberately broken fixtures. The
    # argument names a directory holding requirements/ and tasks/, mirroring the state dir.
    base = Path(sys.argv[sys.argv.index("--state") + 1]) if "--state" in sys.argv else None
    try:
        requirements = load_requirements(base / "requirements" if base else state_dir("requirements"))
        tasks = load_tasks(base / "tasks" if base else state_dir("tasks"))
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    readable = [t for t in tasks if t["error"] is None]

    check_ids_unique(requirements, readable)
    check_superseded(requirements)
    check_satisfies(readable, requirements)
    check_task_refs(readable)

    for violation in violations:
        print(f"  violation: {violation}")
    print(f"\n{len(requirements)} requirement(s), {len(readable)} readable task(s), "
          f"{len(violations)} violation(s).")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
