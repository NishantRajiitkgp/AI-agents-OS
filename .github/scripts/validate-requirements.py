#!/usr/bin/env python3
"""Validate requirement area files against the requirement schema.

PROVISIONAL. Moves into `aios check` at M1-14, per ADR-006.

Scope is one file against its own schema. Whether a reference resolves, and whether an ID is
unique across the repository, is validate-references.py — no single file can know either.

Two severities, and the split is deliberate (04 §2.1):

  violations block. Structure, status vocabulary, mandatory reasons — objective, cheap to
  fix, and corrupting to everything downstream if allowed through.

  warnings do not block. EARS conformance and weasel words are style signals with a real
  false-positive rate. A requirement that resists EARS is usually saying something about the
  requirement; blocking there buys template-shaped nonsense written to satisfy a linter,
  which is worse than the prose it replaced.

Exit codes: 0 valid, 1 violations, 2 could not run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from aios_state import (
    SUPERSEDED, CouldNotRun, load_requirements, relative, state_dir,
)

EARS = [
    re.compile(r"^When\b.+,\s+the system shall\b", re.S),
    re.compile(r"^If\b.+,\s+then the system shall\b", re.S),
    re.compile(r"^While\b.+,\s+the system shall\b", re.S),
    re.compile(r"^Where\b.+,\s+the system shall\b", re.S),
    re.compile(r"^The system shall\b", re.S),
]

WEASEL = ["fast", "user-friendly", "appropriate", "etc.", "robust", "simple",
          "efficient", "seamless", "intuitive", "quickly", "properly", "reasonable",
          "as needed", "and so on"]

SIMPLE_STATUSES = {"active", "deferred", "dropped"}

violations: list[str] = []
warnings: list[str] = []


def check(section: dict, seen: dict[str, str]) -> None:
    where = relative(section["file"])
    at = f"{where}:{section['line']} {section['id']}"

    if section["area"] != section["file"].stem.upper():
        violations.append(
            f"{at}: area {section['area']} does not match the filename "
            f"({section['file'].stem.upper()})")

    if section["id"] in seen:
        violations.append(f"{at}: duplicate ID, already defined at {seen[section['id']]}")
    else:
        seen[section["id"]] = at

    fields, status = section["fields"], section["status"]
    if not status:
        violations.append(f"{at}: no Status")
    elif status in SIMPLE_STATUSES:
        if status in ("deferred", "dropped") and not fields.get("reason"):
            violations.append(f"{at}: status {status!r} requires a Reason")
        if status == "active" and not fields.get("rationale"):
            violations.append(f"{at}: an active requirement requires a Rationale")
    elif not SUPERSEDED.match(status):
        violations.append(
            f"{at}: status {status!r} is not one of active, deferred, dropped, "
            f"or 'superseded-by: <ID>'")

    if not section["clauses"]:
        violations.append(f"{at}: no requirement body")

    for clause in section["clauses"]:
        if not any(pattern.match(clause) for pattern in EARS):
            warnings.append(f"{at}: clause matches no EARS template — {clause[:60]}...")
        low = clause.lower()
        for word in WEASEL:
            if re.search(rf"(?<![\w-]){re.escape(word)}", low):
                warnings.append(f"{at}: weasel word {word!r} in a requirement clause")


def main() -> int:
    # Overridable so the gate can be exercised against deliberately broken fixtures.
    directory = (Path(sys.argv[sys.argv.index("--dir") + 1]) if "--dir" in sys.argv
                 else None)
    try:
        sections = load_requirements(directory or state_dir("requirements"))
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    files = {section["file"] for section in sections}
    for path in (directory or state_dir("requirements")).glob("*.md"):
        if path not in files:
            violations.append(f"{relative(path)}: no requirements found")

    seen: dict[str, str] = {}
    for section in sections:
        check(section, seen)

    for warning in warnings:
        print(f"  warning: {warning}")
    for violation in violations:
        print(f"  violation: {violation}")

    print(f"\n{len(files)} area file(s), {len(seen)} requirement(s), "
          f"{len(violations)} violation(s), {len(warnings)} warning(s).")
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
