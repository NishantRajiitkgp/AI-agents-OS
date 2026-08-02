#!/usr/bin/env python3
"""Measure the always-on context set, and enforce the budget on it.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

ADR-010 established that four things are in context on every turn in Cursor: `AGENTS.md`,
every `.cursor/rules/*.mdc` marked `alwaysApply`, every skill **description**, and every
subagent **description**. ADR-011 set the total at 200 lines with 150 reserved for AGENTS.md.

This file exists because that definition had drifted into two implementations. The workflow
step counted all four; `check-ratchets.py` counted only the first two. They agreed on 143
lines and would have kept agreeing right up until the first subagent was added — at which
point the ratchet would have reported "held" while the set it claims to watch grew. AGENTS.md
names that hazard exactly: two implementations of one gate can disagree. So there is one
implementation, and both callers use it.

Bodies are not counted. A subagent's body loads when it is invoked; only its description is
resident, which is what makes a subagent a cheap thing to add and an expensive thing to
describe.

Exit codes: 0 within budget · 1 over · 2 could not run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative

ALWAYS_APPLY = re.compile(r"^alwaysApply:\s*true\s*$", re.MULTILINE)
FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*:")
WITHIN, OVER, CANNOT_RUN = 0, 1, 2


def frontmatter(text: str) -> list[str]:
    """The lines between the first pair of `---` fences, or nothing."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return []
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return lines[1:index]
    return []


def description_lines(text: str) -> int:
    """Lines the `description` field occupies in the frontmatter, including continuations.

    Counted as lines rather than parsed as YAML because it is lines that are charged against
    the budget, and a folded scalar's line count is not recoverable once YAML has folded it.
    """
    counting, total = False, 0
    for line in frontmatter(text):
        if line.startswith("description:"):
            counting, total = True, total + 1
            continue
        if counting:
            # A sibling key ends the field; anything else is a continuation of it.
            if FIELD.match(line):
                break
            total += 1
    return total


def contributors(root: Path) -> list[tuple[str, int]]:
    """Every always-on contributor and its line count, in the order ADR-010 lists them."""
    found: list[tuple[str, int]] = []

    agents = root / "AGENTS.md"
    if not agents.is_file():
        raise CouldNotRun(f"no {relative(agents)}")
    found.append(("AGENTS.md", len(agents.read_text(encoding="utf-8").splitlines())))

    rules = root / ".cursor" / "rules"
    if rules.is_dir():
        for rule in sorted(rules.glob("*.mdc")):
            text = rule.read_text(encoding="utf-8")
            if ALWAYS_APPLY.search("\n".join(frontmatter(text))):
                found.append((f"{relative(rule)} (alwaysApply)", len(text.splitlines())))

    # Skills nest a level deeper than subagents: `.claude/skills/<name>/SKILL.md` against
    # `.claude/agents/<name>.md`.
    described = sorted((root / ".claude" / "skills").glob("*/SKILL.md"))
    described += sorted((root / ".claude" / "agents").glob("*.md"))
    for path in described:
        count = description_lines(path.read_text(encoding="utf-8"))
        if count:
            found.append((f"{relative(path)} (description)", count))
    return found


def measure(root: Path) -> int:
    return sum(count for _, count in contributors(root))


def measure_agents_md(root: Path) -> int:
    return len((root / "AGENTS.md").read_text(encoding="utf-8").splitlines())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        config = yaml.safe_load(
            (root / "aios" / "config.yml").read_text(encoding="utf-8")) or {}
        budgets = config.get("budgets") or {}
        total_budget = budgets["always_on_lines"]
        agents_budget = budgets["agents_md_lines"]
        found = contributors(root)
    except (CouldNotRun, OSError, KeyError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    for label, count in found:
        print(f"  {label:<52} {count:4d}")
    total = sum(count for _, count in found)
    agents = dict(found)["AGENTS.md"]
    print(f"  {'ALWAYS-ON TOTAL':<52} {total:4d}  (budget {total_budget})")

    status = WITHIN
    if agents > agents_budget:
        print(f"::error::AGENTS.md is {agents} lines; its sub-budget is {agents_budget}.")
        status = OVER
    if total > total_budget:
        print(f"::error::Always-on context is {total} lines; the budget is {total_budget}.")
        print("Past the budget, an addition requires a deletion. Raising the ceiling means")
        print("superseding ADR-011, which is deliberate friction, not an obstacle.")
        status = OVER
    return status


if __name__ == "__main__":
    raise SystemExit(main())
