#!/usr/bin/env python3
"""The traceability map and the orphan reports (M5-05).

PROVISIONAL. Moves into the binary at `M1-08`.

Three questions, none of which blocks a build:

- Which requirements have no test?
- Which tests trace to no requirement?
- Which requirements have no task, and were never explicitly deferred?

**They report rather than block, and that is a decision rather than timidity.** In each case
the right fix is sometimes to change the requirement. A gate that blocks presumes the code is
wrong, and a gate that presumes the code is wrong trains people to satisfy it dishonestly —
one throwaway test per requirement, a `@satisfies` comment on the nearest test that happens to
pass, a requirement quietly marked deferred to clear the report. Every one of those makes the
map worse while making the number better, which is the failure mode of every coverage metric
ever shipped.

Tests declare what they cover with `@satisfies <REQ-ID>`. The second use of that annotation is
worth as much as the traceability: it gives a failing test a *reason*. Not "assertion failed at
line 42" but "STATE-4 is violated" — which is the difference between a failure someone triages
and a failure someone understands.

Exit 0 always, unless it genuinely could not run. A report that can fail is a gate.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from aios_state import CouldNotRun, load_requirements, load_tasks, state_dir

PASS, COULD_NOT_RUN = 0, 2

SATISFIES = re.compile(r"@satisfies\s+([A-Z][A-Z0-9]*-\d+)")


def coverage(tests: Path) -> dict[str, list[str]]:
    """Requirement ID to the test files claiming it."""
    found: dict[str, list[str]] = {}
    if not tests.is_dir():
        return found
    for path in sorted(tests.rglob("*.py")):
        text = path.read_text(encoding="utf-8", errors="replace")
        for requirement in sorted(set(SATISFIES.findall(text))):
            found.setdefault(requirement, []).append(path.name)
    return found


def untraced(tests: Path) -> list[str]:
    """Test files claiming no requirement at all.

    Reported at file granularity rather than per test, because a file of gate-mechanics tests
    covering one requirement is normal and flagging each function would drown the signal.
    """
    if not tests.is_dir():
        return []
    return sorted(path.name for path in tests.rglob("*.py")
                  if not SATISFIES.search(path.read_text(encoding="utf-8", errors="replace")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    try:
        # `--root` names a tree directly; without it, discovery walks up from here as every
        # other gate does.
        requirements = load_requirements(
            root / "aios" / "requirements" if args.root else state_dir("requirements"))
        tasks = [t for t in load_tasks(
            root / "aios" / "tasks" if args.root else state_dir("tasks"))
            if t["error"] is None]
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    covered = coverage(root / "tests")
    claimed = {req for task in tasks for req in (task["data"].get("satisfies") or [])}
    known = {req["id"] for req in requirements}

    active = [r for r in requirements if r["status"] == "active"]
    no_test = [r["id"] for r in active if r["id"] not in covered]
    no_task = [r["id"] for r in active if r["id"] not in claimed]
    unknown = sorted(set(covered) - known)
    orphan_tests = untraced(root / "tests")

    if args.format == "json":
        print(json.dumps({
            "requirements": len(requirements), "active": len(active),
            "covered": {k: v for k, v in sorted(covered.items())},
            "requirements_without_a_test": no_test,
            "requirements_without_a_task": no_task,
            "tests_naming_an_unknown_requirement": unknown,
            "test_files_tracing_to_nothing": orphan_tests,
        }, indent=2))
        return PASS

    print(f"{len(requirements)} requirement(s), {len(active)} active, "
          f"{len(active) - len(no_test)} with a test.")

    for requirement in no_test:
        print(f"::warning::{requirement} has no test naming it. Add `@satisfies "
              f"{requirement}` to the test that covers it, or say why the requirement cannot "
              f"be tested as written.")
    for requirement in no_task:
        print(f"::warning::{requirement} is active and no task claims it. Either it is not "
              f"being built, in which case defer it and say so, or the task that builds it "
              f"is not declaring what it is for.")
    for requirement in unknown:
        print(f"::warning::a test names {requirement}, which is not a requirement. Either it "
              f"was renamed and the test was not, or it was never real.")
    if orphan_tests:
        print(f"::warning::{len(orphan_tests)} test file(s) trace to no requirement: "
              f"{', '.join(orphan_tests[:6])}"
              f"{'…' if len(orphan_tests) > 6 else ''}. Not necessarily wrong — a gate's own "
              f"mechanics are worth testing whether or not a requirement names them.")

    if not (no_test or no_task or unknown):
        print("Every active requirement has a test and a task.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
