#!/usr/bin/env python3
"""Resolve the autonomy level for a task, and hold the table's invariants.

PROVISIONAL. Moves into the binary at `M1-08`.

Autonomy is `risk` × `tier` (05 §4, D-025). Always-stop is right as a default and wrong as an
absolute: treating a typo fix like an auth rewrite is how a review gate becomes a rubber
stamp, and the person who types `Next` forty times is not reading the fortieth diff.

Two jobs, deliberately in one place:

- **Resolve** a level, so the hook and CI answer the question identically.
- **Check the table**, because a policy table is data and data drifts. `risk: high` never
  reaches A2 is an invariant asserted here, separately from the numbers it constrains — a
  table that both stated the rule and was the only check on it could repeal the rule by being
  edited.

Usage:
    check-autonomy.py                      validate the table
    check-autonomy.py --task T-950a        resolve, and print the level and its chain limit
    check-autonomy.py --format json        machine-readable

Exit 0 pass, 1 fail, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, load_config, load_tasks, relative, state_dir

LEVELS = ("A0", "A1", "A2")
RISKS = ("low", "medium", "high")
TIERS = ("prototype", "internal", "production", "regulated")

ROW = re.compile(r"^(?P<tier>\w+):\s+" + r"\s+".join(
    rf"{risk}=(?P<{risk}>A\d)" for risk in RISKS) + r"$")

# How many tasks may begin without a human. A0 is zero rather than one: the approval is what
# permits the first, so an A0 task with no approval has not been permitted anything. Once
# approved it is A1 — one task, then the diff review, which is A0's second checkpoint.
CHAIN = {"A0": 0, "A1": 1}


def parse_table(rows: list[str]) -> tuple[dict[tuple[str, str], str], list[str]]:
    table: dict[tuple[str, str], str] = {}
    problems: list[str] = []
    for row in rows:
        match = ROW.match(str(row).strip())
        if not match:
            problems.append(
                f"autonomy.levels: {row!r} is not `<tier>: low=<level> medium=<level> "
                f"high=<level>`")
            continue
        tier = match.group("tier")
        if tier not in TIERS:
            problems.append(f"autonomy.levels: {tier!r} is not one of {list(TIERS)}")
            continue
        for risk in RISKS:
            level = match.group(risk)
            if level not in LEVELS:
                problems.append(
                    f"autonomy.levels: {tier} {risk} is {level!r}, not one of {list(LEVELS)}")
                continue
            table[(tier, risk)] = level
    return table, problems


def check_table(table: dict[tuple[str, str], str]) -> list[str]:
    problems = []

    for tier in TIERS:
        for risk in RISKS:
            if (tier, risk) not in table:
                problems.append(
                    f"autonomy.levels: no level for {tier} {risk}. Every cell needs one; a "
                    f"missing cell would be resolved by a default, and a default here is a "
                    f"policy nobody wrote down.")

    # The invariant, stated independently of the table it constrains.
    for tier in TIERS:
        if table.get((tier, "high")) == "A2":
            problems.append(
                f"autonomy.levels: {tier} high is A2. `risk: high` never reaches A2 at any "
                f"tier (D-025). A2 exists for trivial work; high-risk work is what the review "
                f"attention it frees up is for.")

    # Risk should not buy autonomy, and neither should a stricter tier.
    for tier in TIERS:
        levels = [table.get((tier, risk)) for risk in RISKS]
        if any(a is None for a in levels):
            continue
        if not all(levels[i] >= levels[i + 1] for i in range(len(levels) - 1)):
            problems.append(
                f"autonomy.levels: {tier} does not tighten as risk rises ({levels}). Higher "
                f"risk must never permit more autonomy than lower risk in the same tier.")
    for risk in RISKS:
        levels = [table.get((tier, risk)) for tier in TIERS]
        if any(a is None for a in levels):
            continue
        if not all(levels[i] >= levels[i + 1] for i in range(len(levels) - 1)):
            problems.append(
                f"autonomy.levels: {risk} does not tighten as the tier rises ({levels}). A "
                f"stricter tier must never permit more autonomy than a looser one.")

    return problems


def chain_limit(level: str, configured: int, approved: bool = False) -> int:
    if level == "A0":
        return 1 if approved else 0
    return CHAIN.get(level, configured)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", help="resolve the level for this task ID")
    parser.add_argument("--config", help="config file, for tests")
    parser.add_argument("--dir", help="tasks directory, for tests")
    parser.add_argument("--format", choices=("human", "json"), default="human")
    args = parser.parse_args()

    try:
        if args.config:
            try:
                config = yaml.safe_load(Path(args.config).read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError) as exc:
                raise CouldNotRun(f"{args.config}: {exc}") from exc
        else:
            config = load_config()
        autonomy = config.get("autonomy") or {}
        rows = autonomy.get("levels") or []
        configured = autonomy.get("chain_limit")
        tier = config.get("tier")
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    table, problems = parse_table(rows)
    problems += check_table(table)
    if not isinstance(configured, int) or isinstance(configured, bool) or configured < 1:
        problems.append(f"autonomy.chain_limit: {configured!r} is not a positive integer")

    if problems:
        for problem in problems:
            print(f"  violation: {problem}")
        print(f"\n{len(problems)} violation(s).")
        return 1

    if not args.task:
        print(f"autonomy table is complete and consistent: {len(table)} cells, tier {tier!r}, "
              f"chain limit {configured}.")
        return 0

    try:
        directory = Path(args.dir) if args.dir else state_dir("tasks")
        tasks = {task["data"].get("id"): task for task in load_tasks(directory)}
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    task = tasks.get(args.task)
    if task is None:
        print(f"no task {args.task!r}", file=sys.stderr)
        return 2

    risk = task["data"].get("risk")
    level = table.get((tier, risk))
    if level is None:
        print(f"could not run: no level for tier {tier!r} risk {risk!r}", file=sys.stderr)
        return 2

    limit = chain_limit(level, configured)
    if args.format == "json":
        print(json.dumps({"task": args.task, "tier": tier, "risk": risk, "level": level,
                          "chain_limit": limit, "path": relative(task["path"])}))
    else:
        print(f"{args.task}: tier {tier} × risk {risk} → {level}, "
              f"{limit} task(s) without a human.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
