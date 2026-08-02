#!/usr/bin/env python3
"""The incident schema (M5-11).

PROVISIONAL. Moves into the binary at `M1-08`.

One field carries this whole file: **the control the incident produced**. Without it an
incident log is a list of regrets — a place where things that went wrong are written down,
read once, and prevent nothing. With it, a bug caught in review is worth one fix and a bug
that produces a gate is worth every future instance of itself. That ratio is the difference
between an operating system and a filing system, and `aios health` reports it directly.

`no_control_because` exists because sometimes there genuinely is no practical control, and a
schema that will not accept that answer gets a fictional control instead. What it will not
accept is silence.

Incidents are append-only. Editing one is not correcting the record, it is losing it: the
value of "we believed X on the day, and X was wrong" is entirely in it having been written
before anyone knew. Enforcement of that lives in `check-overrides.py`, which already watches
this directory for edits to override records; this validates shape, not history.

Exit 0 pass, 1 fail, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

import yaml

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2

FILENAME = re.compile(r"^(\d{4}-\d{2}-\d{2})-[a-z0-9-]+\.md$")
KNOWN = {"date", "control", "no_control_because", "blocks_work", "during", "detected_by"}
REQUIRED = {"date", "detected_by"}
MINIMUM_CONTROL = 30


def frontmatter(text: str) -> tuple[dict | None, str]:
    if not text.startswith("---"):
        return None, "no YAML frontmatter"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "frontmatter is not closed"
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError as exc:
        return None, f"frontmatter is not valid YAML ({exc})"
    return (data if isinstance(data, dict) else None,
            "" if isinstance(data, dict) else "frontmatter is not a mapping")


def check(path: Path, today: date) -> list[str]:
    problems = []
    name = path.name

    match = FILENAME.match(name)
    if not match:
        problems.append("filename must be <YYYY-MM-DD>-<slug>.md, which is what makes the "
                        "directory sort chronologically without an index to maintain")

    data, why = frontmatter(path.read_text(encoding="utf-8"))
    if data is None:
        return problems + [why]

    for field in sorted(REQUIRED - set(data)):
        problems.append(f"missing required field {field!r}")
    for field in sorted(set(data) - KNOWN):
        problems.append(f"unknown field {field!r}; the field list is closed so a typo is a "
                        f"failure rather than a field nobody reads")

    control = str(data.get("control") or "").strip()
    excuse = str(data.get("no_control_because") or "").strip()
    if control and excuse:
        problems.append("declares both a control and a reason there is none; one of them is "
                        "not true")
    elif not control and not excuse:
        problems.append("declares no control and no reason for having none. An incident that "
                        "produced nothing is a regret, not a record — say what now prevents "
                        "recurrence, or say plainly why nothing practical does")
    elif len(control or excuse) < MINIMUM_CONTROL:
        problems.append(f"the control is {len(control or excuse)} characters. Name what it "
                        f"is and where it lives, or the field is a checkbox")

    if "blocks_work" in data and not isinstance(data["blocks_work"], bool):
        problems.append("blocks_work must be true or false; it stops `aios next` from handing "
                        "out work, so it cannot be a string that is truthy by accident")

    stamp = data.get("date")
    if isinstance(stamp, date):
        if stamp > today:
            problems.append(f"dated {stamp}, which is in the future")
        if match and match.group(1) != stamp.isoformat():
            problems.append(f"dated {stamp} but filed under {match.group(1)}")
    elif "date" in data:
        problems.append("date must be a YYYY-MM-DD date, not a string")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, help="incidents directory")
    parser.add_argument("--today", help="override the date, for tests")
    args = parser.parse_args()

    directory = args.dir or Path(__file__).resolve().parents[2] / "aios" / "incidents"
    if not directory.is_dir():
        print(f"could not run: no {directory}", file=sys.stderr)
        return COULD_NOT_RUN
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"could not run: {args.today!r} is not a date", file=sys.stderr)
        return COULD_NOT_RUN

    violations = 0
    incidents = sorted(p for p in directory.rglob("*.md"))
    with_control = 0
    for path in incidents:
        problems = check(path, today)
        for problem in problems:
            print(f"  violation: {path.name}: {problem}")
        violations += len(problems)
        data, _ = frontmatter(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and str(data.get("control") or "").strip():
            with_control += 1

    if violations:
        print(f"\n{violations} violation(s) across {len(incidents)} incident(s).")
        return FAIL

    if incidents:
        # Reported on success because it is the number the design cares about, and a number
        # nobody sees is a number nobody acts on.
        print(f"{len(incidents)} incident(s), {with_control} of which produced a control "
              f"({with_control * 100 // len(incidents)}%).")
    else:
        print("no incidents recorded.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
