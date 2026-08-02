#!/usr/bin/env python3
"""The standards schema (M5-12).

PROVISIONAL. Moves into the binary at `M1-08`.

A standards file holds conventions a linter cannot express. That sentence is the whole schema,
and every rule here follows from taking it literally.

Every rule declares either `Enforced by:` naming a real check, or `Unenforceable:` giving the
reason. There is no third option, because the third option in practice is prose that sounds
like a rule, is enforced by nobody, and is followed until the first deadline.

Where a rule *is* enforced, its prose is capped at two lines pointing at the check. Longer
than that and the file becomes a second, informal statement of what the linter already says
exactly — and when the two drift, people believe the prose.

**A file whose rules are all enforced fails.** That reads like a bug and is the point: if every
rule in it is mechanically checked, the file is a description of the linter, and the linter is
already the description of the linter. Delete it. This is the one gate in the repository whose
pass condition is a file not existing, and M5 is the milestone about whether this system can
shrink.

Format, mirroring the requirement files:

    ## STYLE-1 — Commit messages name the change, not the file
    **Enforced by:** hygiene.yml step "Commit subjects are imperative"
    Prose, at most two lines when enforced.

Exit 0 pass, 1 fail, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2

HEADING = re.compile(r"^##\s+([A-Z][A-Z0-9]*-\d+)\s+—\s+(.+)$")
ENFORCED = re.compile(r"^\*\*Enforced by:\*\*\s*(.+)$")
UNENFORCEABLE = re.compile(r"^\*\*Unenforceable:\*\*\s*(.+)$")
PROSE_LINES_WHEN_ENFORCED = 2
MINIMUM_REASON = 25


def rules(text: str) -> list[dict]:
    """Split a standards file into rules. A heading opens one; the next heading closes it."""
    found: list[dict] = []
    for number, line in enumerate(text.splitlines(), start=1):
        match = HEADING.match(line)
        if match:
            found.append({"id": match.group(1), "title": match.group(2).strip(),
                          "line": number, "body": []})
        elif found:
            found[-1]["body"].append(line)
    return found


def check_rule(rule: dict) -> list[str]:
    problems = []
    enforced = unenforceable = None
    prose = []
    for line in rule["body"]:
        if (match := ENFORCED.match(line)):
            enforced = match.group(1).strip()
        elif (match := UNENFORCEABLE.match(line)):
            unenforceable = match.group(1).strip()
        elif line.strip():
            prose.append(line)

    if enforced and unenforceable:
        problems.append("declares both Enforced by and Unenforceable; one is not true")
    elif not enforced and not unenforceable:
        problems.append("declares neither 'Enforced by' nor 'Unenforceable'. A rule nobody "
                        "checks and nobody has admitted cannot be checked is prose that "
                        "sounds like a rule")
    elif unenforceable and len(unenforceable) < MINIMUM_REASON:
        problems.append(f"'Unenforceable: {unenforceable}' does not say why. The reason is "
                        "what stops the field becoming the way around the schema")
    elif enforced and len(prose) > PROSE_LINES_WHEN_ENFORCED:
        problems.append(f"is enforced and carries {len(prose)} lines of prose; the cap is "
                        f"{PROSE_LINES_WHEN_ENFORCED}. Past that the file restates what the "
                        f"check already says, and when the two drift people believe the prose")
    return problems


def check_file(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    found = rules(text)
    if not found:
        return ["contains no rules; an empty standards file is a file to keep up to date for "
                "no reason"]

    problems = []
    seen: dict[str, int] = {}
    for rule in found:
        for problem in check_rule(rule):
            problems.append(f"{rule['id']} (line {rule['line']}) {problem}")
        if rule["id"] in seen:
            problems.append(f"{rule['id']} is defined twice, at lines {seen[rule['id']]} "
                            f"and {rule['line']}")
        seen[rule["id"]] = rule["line"]

    enforced = [r for r in found
                if any(ENFORCED.match(line) for line in r["body"])]
    if len(enforced) == len(found):
        problems.append(f"every one of its {len(found)} rules is mechanically enforced, so "
                        f"the file is a description of the checks. Delete it — the checks are "
                        f"already that description, and this copy is the one that goes stale")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, help="standards directory")
    args = parser.parse_args()

    directory = args.dir or Path(__file__).resolve().parents[2] / "aios" / "standards"
    if not directory.is_dir():
        print(f"could not run: no {directory}", file=sys.stderr)
        return COULD_NOT_RUN

    files = sorted(directory.rglob("*.md"))
    violations = 0
    for path in files:
        for problem in check_file(path):
            print(f"  violation: {path.name}: {problem}")
            violations += 1

    if violations:
        print(f"\n{violations} violation(s) across {len(files)} standards file(s).")
        return FAIL

    if not files:
        # Not a failure. A repository with no conventions a linter cannot express is the
        # target state, not a gap — and saying so keeps the empty directory from reading as
        # an oversight somebody later fills in to be helpful.
        print("no standards files. Every convention here is either checked or not yet needed.")
    else:
        print(f"{len(files)} standards file(s) conform.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
