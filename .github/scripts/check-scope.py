#!/usr/bin/env python3
"""Check a diff against the declared write scope of the task it belongs to.

PROVISIONAL. Moves into `aios check` at M1-14, per ADR-006.

The point is not to stop the agent touching files it did not foresee — often it must. The
point is that expanding scope becomes an explicit, reviewable edit to the task file, visible
in the same pull request, instead of an unremarked extra hunk in a 400-line diff. Reviewers
reliably miss the second and reliably notice the first (04 §3.5, D-011).

Two things follow from that, and both are easy to get wrong:

  The unused-scope figure is reported even when nothing escaped. A task declaring `src/**`
  and touching two files has passed the check while defeating its purpose, and only the
  unused figure makes that visible.

  The class depends on tier (06 §3): Advisory at `prototype`, Contract from `internal` up.
  This repository is `prototype`, so the gate reports here and blocks elsewhere. A check that
  silently behaved as Contract everywhere would be a different control than the one designed.

Exit codes: 0 in scope (or Advisory), 1 escaped at Contract tier, 2 could not run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from aios_state import (
    TASK_ID, CouldNotRun, load_config, load_tasks, relative, state_dir,
)

CONTRACT_TIERS = {"internal", "production", "regulated"}
TASK_IN_TEXT = re.compile(r"T-[0-9a-f]{4}(?:[0-9a-f]{2})?")
DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+)$")


def glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a path glob to a regex.

    fnmatch is not usable here: its `*` crosses directory separators, so `src/*` would match
    `src/a/b/c.py` and a lazily scoped task would look precisely scoped.
    """
    if pattern.endswith("/"):
        pattern += "**"
    out: list[str] = []
    i, n = 0, len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def changed_paths(diff: str) -> list[str]:
    """Every path the diff writes to, including deletions and both sides of a rename."""
    paths: set[str] = set()
    for line in diff.splitlines():
        match = DIFF_HEADER.match(line)
        if match:
            paths.update(p for p in match.groups() if p != "/dev/null")
        elif line.startswith(("+++ ", "--- ")):
            target = line[4:].strip()
            if target not in ("/dev/null", "") and target[:2] in ("a/", "b/"):
                paths.add(target[2:])
    return sorted(paths)


def resolve_task(tasks: list[dict], explicit: str | None, branch: str | None,
                 paths: list[str]) -> dict:
    """Identify the task this diff belongs to, or refuse.

    Refusing beats guessing. Attributing a diff to the wrong task would check it against the
    wrong scope, and a scope check that passes for the wrong reason is worse than none.
    """
    by_id = {str(t["data"].get("id")): t for t in tasks if t["data"].get("id")}

    if explicit:
        if explicit not in by_id:
            raise CouldNotRun(f"--task {explicit} names no task file")
        return by_id[explicit]

    if branch:
        found = [t for t in TASK_IN_TEXT.findall(branch) if t in by_id]
        if len(set(found)) == 1:
            return by_id[found[0]]
        if len(set(found)) > 1:
            raise CouldNotRun(f"branch {branch!r} names several tasks: {sorted(set(found))}")

    # Matched on filename rather than full path. A task ID is unique repository-wide and the
    # filename is required to equal it, so the basename identifies the task regardless of what
    # paths.state_dir is called or where the diff was generated from.
    names = {Path(p).name for p in paths}
    touched_tasks = [t for t in tasks
                     if t["path"].name in names and t["data"].get("id")]
    if len(touched_tasks) == 1:
        return touched_tasks[0]
    if len(touched_tasks) > 1:
        raise CouldNotRun(
            "the diff changes several task files "
            f"({[relative(t['path']) for t in touched_tasks]}), so the task is ambiguous. "
            "Name it with --task.")

    raise CouldNotRun(
        "cannot tell which task this diff belongs to. Name it with --task, put the ID in the "
        "branch name, or let the diff include the task file it is working.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", help="read the diff from this file instead of stdin")
    parser.add_argument("--task", help="the task ID this diff implements")
    parser.add_argument("--branch", help="branch name, used to infer the task ID")
    parser.add_argument("--tier", help="override the configured tier")
    parser.add_argument("--tasks-dir", help="override the tasks directory")
    args = parser.parse_args()

    try:
        diff = (open(args.diff, encoding="utf-8").read() if args.diff else sys.stdin.read())
    except OSError as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    try:
        tier = args.tier or load_config().get("tier", "prototype")
        directory = Path(args.tasks_dir) if args.tasks_dir else state_dir("tasks")
        tasks = [t for t in load_tasks(directory) if t["error"] is None]
        paths = changed_paths(diff)
        if not paths:
            print("empty diff, nothing to check.")
            return 0
        task = resolve_task(tasks, args.task, args.branch, paths)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    task_id = str(task["data"]["id"])
    declared = [g for g in (task["data"].get("touches") or []) if isinstance(g, str)]
    matchers = [(g, glob_to_regex(g)) for g in declared]

    # The task's own file is always in scope. Status transitions and the verification record
    # are written into it, so a task that had to declare itself would be declaring the
    # bookkeeping of every task, and forgetting to would make every task escape its own scope.
    own_file = relative(task["path"])
    own_name = task["path"].name

    escaped: list[str] = []
    used: set[str] = set()
    for path in paths:
        if Path(path).name == own_name:
            continue
        hit = [glob for glob, rx in matchers if rx.match(path)]
        if hit:
            used.update(hit)
        else:
            escaped.append(path)

    unused = [glob for glob in declared if glob not in used]
    contract = tier in CONTRACT_TIERS

    print(f"Task {task_id} at tier {tier!r} — scope is "
          f"{'Contract' if contract else 'Advisory'} here.")
    print(f"{len(paths)} path(s) changed against {len(declared)} declared glob(s).")

    if unused:
        share = round(100 * len(unused) / len(declared)) if declared else 0
        print(f"\n  unused scope: {len(unused)} of {len(declared)} declared glob(s) "
              f"({share}%) matched nothing:")
        for glob in unused:
            print(f"    {glob}")
        print("  Declared scope that goes unused is scope that was guessed. It makes the "
              "review surface\n  larger than the change, which is the cost `touches` exists "
              "to avoid.")

    if not escaped:
        print("\nno paths escaped the declared scope.")
        return 0

    print(f"\n  {len(escaped)} path(s) outside the declared scope:")
    for path in escaped:
        print(f"    {path}")
    print(f"\n  Amend {own_file} to declare these paths, in this same pull request. Widening "
          f"scope\n  is permitted; doing it silently is not. That edit is the review signal.")

    if contract:
        print(f"\nContract gate at tier {tier!r}: this blocks the merge.")
        return 1
    print(f"\nAdvisory at tier {tier!r}: reported, not blocking. This would block from "
          f"'internal' up.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
