#!/usr/bin/env python3
"""Decide whether a set of tasks may be dispatched to parallel worktrees (M4-11).

PROVISIONAL. Moves into the binary at `M1-08`.

The rule is parallel reads, serial writes ([05 §6](../../docs/design/05-workflows.md)):
explorers in parallel are encouraged, two writing agents in one worktree are forbidden, and
two writing agents in *separate* worktrees are permitted at `internal` tier and below only
when their `touches` are disjoint — checked mechanically, before dispatch, not discovered at
merge time. Every "just run five agents" workflow that ends in a merge disaster ends there
because nothing performed this check.

The disjointness test is **sound, not complete**: it can refuse two scopes that would in fact
never have collided, and it will not permit two that would. That asymmetry is chosen. A false
refusal costs one narrowed `touches` line; a false permission costs two agents making
conflicting implicit decisions about the same file, which is the failure the whole rule exists
to prevent.

It is a *pattern* intersection rather than a file-set intersection, and that distinction is
the reason this is worth writing down. Expanding both scopes against the working tree and
intersecting the results looks equivalent and is not: `src/**` and `src/auth/**` share no file
in a repository where `src/auth/` does not exist yet, and they collide the moment the task
creates it. Comparing what the patterns *can* match catches that; comparing what they match
today does not.

Usage:
    check-parallel.py T-a3f8 T-91c2 [...]      may these run in parallel?
    check-parallel.py --root <path> ...        against a fixture tree

Exit 0 permitted, 1 refused, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import re
import sys
from functools import lru_cache
from pathlib import Path

# Ordered. Where the ceiling sits is `parallelism.max_tier` in config.yml and is deliberately
# not repeated here: a policy with two definitions has two answers the day one is edited.
TIERS = ["prototype", "internal", "production", "regulated"]

DISPATCHABLE = {"todo", "doing"}

PASS, REFUSED, COULD_NOT_RUN = 0, 1, 2


class CouldNotRun(Exception):
    """Distinct from a refusal. A check that cannot run must never look like one that passed,
    and must not look like one that failed either."""


@lru_cache(maxsize=None)
def segments_can_match(a: str, b: str) -> bool:
    """Can one path *segment* satisfy both patterns at once?

    `*` and `?` only; `/` never reaches here because the caller splits on it first, which is
    what keeps `*` from crossing a directory boundary.
    """

    @lru_cache(maxsize=None)
    def walk(i: int, j: int) -> bool:
        if i == len(a) and j == len(b):
            return True
        if i == len(a):
            return all(c == "*" for c in b[j:])
        if j == len(b):
            return all(c == "*" for c in a[i:])
        if a[i] == "*":
            return walk(i + 1, j) or walk(i, j + 1)
        if b[j] == "*":
            return walk(i, j + 1) or walk(i + 1, j)
        if a[i] == "?" or b[j] == "?" or a[i] == b[j]:
            return walk(i + 1, j + 1)
        return False

    return walk(0, 0)


def split(pattern: str) -> tuple[str, ...]:
    """A trailing `/` means the directory's contents, which is what an author writing
    `docs/` means and not what the matcher would otherwise do with it."""
    pattern = pattern.strip()
    if pattern.endswith("/"):
        pattern += "**"
    return tuple(part for part in pattern.strip("/").split("/") if part)


@lru_cache(maxsize=None)
def patterns_overlap(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Does some path exist that both globs match?

    `**` spans any number of segments including none, so it branches: consume nothing, or
    consume one segment of the other side and ask again.
    """
    if not a and not b:
        return True
    if not a:
        return all(part == "**" for part in b)
    if not b:
        return all(part == "**" for part in a)
    if a[0] == "**":
        return patterns_overlap(a[1:], b) or patterns_overlap(a, b[1:])
    if b[0] == "**":
        return patterns_overlap(a, b[1:]) or patterns_overlap(a[1:], b)
    return segments_can_match(a[0], b[0]) and patterns_overlap(a[1:], b[1:])


def frontmatter(path: Path) -> dict[str, list[str]]:
    """Read without PyYAML, for the same reason the hooks do: this runs wherever it is
    invoked from, and a missing third-party import must not become a verdict."""
    fields: dict[str, list[str]] = {}
    current: str | None = None
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise CouldNotRun(f"{path.name} has no frontmatter")
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("  - "):
            if current:
                fields[current].append(line[4:].strip().strip("\"'"))
            continue
        match = re.match(r"^([a-z_]+):(.*)$", line)
        if not match:
            continue
        current = match.group(1)
        value = match.group(2).strip()
        fields[current] = [] if value in ("", "[]") else [value.strip("\"'")]
    return fields


def load_task(root: Path, task_id: str) -> dict[str, list[str]]:
    for path in (root / "aios" / "tasks").rglob(f"{task_id}.md"):
        return frontmatter(path)
    raise CouldNotRun(f"no task file for {task_id}")


def policy(root: Path) -> tuple[str, str]:
    """The project's tier, and the highest tier at which parallel worktrees are permitted.

    Read line-wise rather than through PyYAML for the same reason the hooks do: this has to
    run wherever it is invoked from, and a missing third-party import must not become a
    verdict about whether two agents may run.
    """
    config = root / "aios" / "config.yml"
    if not config.is_file():
        raise CouldNotRun(f"{config} does not exist")
    current = ceiling = ""
    for line in config.read_text(encoding="utf-8").splitlines():
        if line.startswith("tier:"):
            current = line.split(":", 1)[1].strip().strip("\"'")
        elif line.strip().startswith("max_tier:"):
            ceiling = line.split(":", 1)[1].strip().strip("\"'")
    if not current:
        raise CouldNotRun("config.yml declares no tier")
    if not ceiling:
        raise CouldNotRun("config.yml declares no parallelism.max_tier")
    return current, ceiling


def check(root: Path, task_ids: list[str]) -> list[str]:
    if len(task_ids) < 2:
        raise CouldNotRun("parallel dispatch needs at least two tasks")

    refusals: list[str] = []

    current, ceiling = policy(root)
    if current not in TIERS or ceiling not in TIERS:
        raise CouldNotRun(f"unknown tier in {current!r}/{ceiling!r}")
    if TIERS.index(current) > TIERS.index(ceiling):
        refusals.append(
            f"tier is {current}; parallel worktrees are permitted at {ceiling} and below. "
            f"Two unreviewed branches at this tier double the review surface the tier "
            f"exists to bound.")

    duplicates = {task_id for task_id in task_ids if task_ids.count(task_id) > 1}
    if duplicates:
        refusals.append(f"{', '.join(sorted(duplicates))} named more than once; a task "
                        f"collides with itself in every file it touches.")

    tasks = {task_id: load_task(root, task_id) for task_id in set(task_ids)}

    for task_id, fields in sorted(tasks.items()):
        status = (fields.get("status") or [""])[0]
        if status not in DISPATCHABLE:
            refusals.append(f"{task_id} is {status or 'statusless'}, not dispatchable.")
        if not [entry for entry in fields.get("touches", []) if entry.strip()]:
            refusals.append(
                f"{task_id} declares no touches, so nothing about it can be proven "
                f"disjoint. The declaration is what makes parallel dispatch checkable at "
                f"all; a task without one may run, but not beside another.")

    ordered = sorted(set(task_ids))
    for index, left in enumerate(ordered):
        for right in ordered[index + 1:]:
            blocked = tasks[left].get("blocked_by", []) + tasks[right].get("blocked_by", [])
            if right in blocked or left in blocked:
                refusals.append(f"{left} and {right} are ordered by blocked_by; they are "
                                f"sequential work, whatever their scopes say.")
            for a in tasks[left].get("touches", []):
                for b in tasks[right].get("touches", []):
                    if patterns_overlap(split(a), split(b)):
                        refusals.append(
                            f"{left} and {right} overlap: {a!r} and {b!r} can match the "
                            f"same path. Narrow one, or run them in sequence.")
    return refusals


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tasks", nargs="*", help="task IDs to dispatch together")
    parser.add_argument("--root", help="repository root, for tests")
    args = parser.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parents[2]

    try:
        refusals = check(root, args.tasks)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN
    except OSError as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if refusals:
        print("parallel dispatch refused:")
        for refusal in refusals:
            print(f"  {refusal}")
        return REFUSED

    print(f"{len(set(args.tasks))} tasks may run in parallel worktrees: scopes are disjoint.")
    print("Expect roughly an order of magnitude more token spend. This is an exception, "
          "not a default.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
