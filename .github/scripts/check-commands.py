#!/usr/bin/env python3
"""Keep slash commands thin, and keep them in one place.

PROVISIONAL. Moves into the binary at `M1-08`.

A slash command is a wrapper. The moment one grows a condition, a loop, or a second step, it
becomes an implementation living in a file with no tests, in a directory nobody greps, and its
behaviour diverges from the command it was supposed to be a shortcut for. What makes that
worth a gate rather than a convention is that the drift is invisible: the command keeps
working, it just stops meaning what its name says.

Four rules, each from a way this has gone wrong somewhere:

- **One invocation per command.** No shell operators, no conditionals. If it needs two steps,
  the second step belongs in the thing being wrapped, where it can be tested.
- **The target exists.** A wrapper around a missing script is a command that fails at the
  moment someone reaches for it, which is the worst moment to discover it.
- **One directory.** `.claude/commands/` was measured to feed Cursor's `/` picker as well
  ([probe](../../aios/bin/probe/results/probe-2026-07-31.md)), so a `.cursor/commands/` copy
  would be the duplicated fact this milestone exists to prevent.
- **The first body line is prose.** Also measured: Cursor shows the command *body* in the
  picker, not the frontmatter `description`. So the first line is user-visible whether or not
  its author realised, and a command whose first line is code shows code to the user.

Usage:
    check-commands.py                check this repository
    check-commands.py --dir <path>   check a fixture tree

Exit 0 pass, 1 fail, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SHARED = ".claude/commands"
DUPLICATE = ".cursor/commands"

# Anything that turns one invocation into a program.
OPERATORS = ("&&", "||", ";", "|", "`", "$(", "if ", "for ", "while ", "then", "&")

FENCE = re.compile(r"^```")
REFERENCE = re.compile(r"[\w./-]+\.(py|sh|ps1|mjs|js|ts)\b")


def frontmatter_and_body(text: str) -> tuple[str | None, list[str]]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None, lines
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return "\n".join(lines[1:index]), lines[index + 1:]
    return None, lines


def check_command(path: Path, root: Path) -> list[str]:
    where = path.relative_to(root).as_posix()
    problems: list[str] = []
    text = path.read_text(encoding="utf-8")

    front, body = frontmatter_and_body(text)
    if front is None:
        problems.append(f"{where}: no YAML frontmatter")
    elif not re.search(r"^description:\s*\S", front, re.M):
        problems.append(f"{where}: frontmatter has no description")

    blocks, current, inside = [], [], False
    prose_first = None
    for line in body:
        if FENCE.match(line.strip()):
            if inside:
                blocks.append(current)
                current = []
            inside = not inside
            continue
        if inside:
            current.append(line)
        elif prose_first is None and line.strip():
            prose_first = line.strip()
    if inside:
        problems.append(f"{where}: an unclosed code fence")

    if prose_first is None:
        problems.append(
            f"{where}: the body starts with code. Cursor shows the body in the picker rather "
            f"than the frontmatter description, so the first line is user-visible.")

    if len(blocks) != 1:
        problems.append(
            f"{where}: {len(blocks)} code block(s), expected exactly 1. A command is one "
            f"invocation; anything more is an implementation in a file with no tests.")
        return problems

    commands = [line for line in blocks[0] if line.strip()]
    if len(commands) != 1:
        problems.append(
            f"{where}: {len(commands)} command line(s), expected exactly 1. If it needs a "
            f"second step, that step belongs in the thing being wrapped.")
        return problems

    command = commands[0]
    for operator in OPERATORS:
        if operator in command:
            problems.append(
                f"{where}: the invocation contains {operator!r}. That is logic, and logic in "
                f"a command file is untested by construction.")
            break

    reference = REFERENCE.search(command)
    if reference is None:
        problems.append(f"{where}: the invocation names no script to run")
    elif not (root / reference.group(0)).is_file():
        problems.append(f"{where}: {reference.group(0)} does not exist. A wrapper around a "
                        f"missing script fails at the moment someone reaches for it.")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", help="repository root, for tests")
    args = parser.parse_args()

    root = Path(args.dir) if args.dir else Path(__file__).resolve().parents[2]
    shared = root / SHARED
    if not shared.is_dir():
        print(f"could not run: {shared} does not exist", file=sys.stderr)
        return 2

    problems: list[str] = []
    commands = sorted(shared.glob("*.md"))
    for path in commands:
        problems += check_command(path, root)

    duplicate = root / DUPLICATE
    if duplicate.is_dir() and any(duplicate.glob("*.md")):
        names = sorted(p.name for p in duplicate.glob("*.md"))
        problems.append(
            f"{DUPLICATE} holds command file(s) {names}. Cursor was measured reading "
            f"{SHARED}, so a second copy is a fact in two tool directories — which is the "
            f"bug, not the redundancy.")

    if problems:
        for problem in problems:
            print(f"  violation: {problem}")
        print(f"\n{len(commands)} command file(s), {len(problems)} violation(s).")
        return 1

    print(f"{len(commands)} command file(s), each one invocation, all in {SHARED}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
