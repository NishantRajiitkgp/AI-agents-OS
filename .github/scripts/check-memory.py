#!/usr/bin/env python3
"""Memory hygiene as a build failure (M5-01).

PROVISIONAL. Moves into the binary at `M1-08`.

The failure this exists to catch has one shape: an instruction that was true when it was
written and is not true now. Nothing about a stale instruction looks wrong. It reads exactly
like a correct one, and an agent follows it exactly as confidently, which is why it has to be
caught mechanically rather than noticed. This repository has already produced the failure
twice — links broke when the tree was flattened, and a rule kept naming a stack the repository
had stopped presuming.

Most of what [04 §6](../../docs/design/04-state-and-tasks.md) lists is already enforced and is
deliberately not re-implemented here: the budgets are ratchets, the task line cap and the
status vocabulary are `validate-tasks.py`, the ID graph is `validate-references.py`, and
`enforced_by` resolution is `validate-config.py`. A second implementation of a check is a
second answer to the same question, which is the whole argument of D-040.

What was left unowned is **path references**, and it is the largest surface of the four. Link
resolution previously lived in `validate-references.py` and ran over requirement and task files
only — roughly a twentieth of the markdown here, and not the part agents read on every turn.
It moved here rather than being copied, so the rule still has one implementation; it now just
covers everything.

Two things are checked rather than one, because they rot differently:

- **Markdown links**, which break on a move and are invisible until someone clicks.
- **Backticked paths in prose**, which break the same way and are never clicked at all. These
  are what an agent actually acts on: `aios/tasks/` in a sentence is an instruction to look
  there, and it is worth no less than a link.

A glob is checked down to its literal prefix — `aios/tasks/**` asserts that `aios/tasks/`
exists — because that is the part a rename invalidates and the rest is by construction unknown.

Usage:
    check-memory.py                 check this repository
    check-memory.py --root <path>   check a fixture tree
    check-memory.py --survey        list every unresolved reference, grouped, and exit 0

Exit 0 pass, 1 fail, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import collections
import re
import sys
from datetime import date
from pathlib import Path

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2

# Two tiers, because links and prose fail differently and a single rule over both produces
# nonsense on one of them.
#
# **Links are navigation.** A broken one is broken wherever it is, including in a document
# nobody may edit — an ADR whose link no longer resolves does not become correct by being
# immutable, it becomes a dead end. So links are checked everywhere in scope.
#
# **Prose is narration, and in an append-only record it is history.** An incident that says
# `probe-nested/AGENTS.md` is describing a file that existed when it was written and was
# deliberately removed afterwards. That is not staleness, and demanding it resolve would
# either falsify the record or resurrect the file. So prose is checked only where a reader is
# being *instructed*, which is the set below.
# The line is what a tool *loads* as instruction, plus the conventions and procedures an agent
# is expected to follow. Every sentence in these is a directive. `docs/architecture.md` is not
# here despite being documentation about this system: it explains, and explanation includes
# describing what other projects do — a sentence about "a `tasks.md` with checkboxes" is
# correct prose about somebody else's repository, and flagging it would be the checker
# demanding the documentation lie.
INSTRUCTIONS = [
    "AGENTS.md", "CLAUDE.md", "README.md",
    ".cursor/rules/**/*.mdc", ".claude/**/*.md",
    "aios/standards/**/*.md", "aios/glossary.md", "aios/open-questions.md",
    "docs/runbooks/**/*.md",
]

# Checked for links only. `task.md` is here because it is a plan rather than an instruction —
# and its links are checked precisely because they have broken before, when the tree was
# flattened and every relative path in it moved at once.
NAVIGATION = INSTRUCTIONS + [
    "task.md", "docs/architecture.md",
    "aios/requirements/**/*.md", "aios/tasks/**/*.md",
    "aios/incidents/**/*.md", "aios/bin/**/*.md",
    "docs/decisions/**/*.md",
]

# `docs/design/` is in neither, and the reason is not squeamishness about false positives: it
# is the pre-OS design set, it does not ship in a clone (ADR-004), and it is written as worked
# examples about a hypothetical project. Asserting that illustrations exist would train people
# to create files to satisfy a checker.

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
TICKED = re.compile(r"`([^`\n]+)`")
SUFFIXES = (".md", ".mdc", ".py", ".yml", ".yaml", ".rs", ".json", ".toml", ".mjs", ".txt",
            ".ps1", ".sh", ".lock")

# A reference that names no particular file. `<task-id>` is a placeholder, `$ARGUMENTS` is a
# substitution, and a bare extension is a file *type*.
PLACEHOLDER = re.compile(r"[<>${}]")



class CouldNotRun(Exception):
    pass


def literal_prefix(reference: str) -> str:
    """The part of a glob a rename can invalidate. `aios/tasks/**` → `aios/tasks`."""
    parts = []
    for part in reference.split("/"):
        if any(char in part for char in "*?["):
            break
        parts.append(part)
    return "/".join(parts)


def links(text: str) -> set[str]:
    return {target.split("#", 1)[0] for target in LINK.findall(text)
            if not target.startswith(("http://", "https://", "#", "mailto:"))} - {""}


def prose(text: str) -> set[str]:
    """Backticked tokens that name a file or directory rather than describe one.

    The exclusions are all things this repository actually writes: `/aios-check` is a slash
    command, `actions/checkout@v4` is an action reference, `.ps1` on its own is a file *type*,
    and `<task-id>` is a placeholder. None of them is a path, and treating them as one
    produces the kind of noise that gets a check switched off.
    """
    found = set()
    for token in TICKED.findall(text):
        token = token.strip().split("#", 1)[0]
        if not token or " " in token or token.startswith(("/", ".ps1", "@")):
            continue
        if "@" in token or PLACEHOLDER.search(token):
            continue
        if token.startswith(".") and "/" not in token and token.count(".") == 1:
            continue  # a bare extension
        if "/" in token or token.endswith(SUFFIXES):
            found.add(token)
    return found


def resolves(root: Path, source: Path, reference: str, by_name: bool) -> bool:
    """Relative to the file, then to the repository root, then — for prose — by name.

    The first two are conventions this repository uses in equal measure: a link in an ADR is
    written relative to the ADR, and `aios/tasks/` in AGENTS.md is written from the root.

    The third exists because prose names things the way people say them. A sentence about
    `check-ratchets.py` is a correct sentence, and demanding `.github/scripts/check-ratchets.py`
    every time would make the writing worse to satisfy a checker. Resolving a bare name
    anywhere in the tree still catches what matters: the file being renamed or deleted while
    the sentence goes on naming it.
    """
    for base in (source.parent, root):
        candidate = (base / reference).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError:
            # Escapes the repository, and is therefore unresolved rather than exempt. Nothing
            # here is checked against the filesystem outside the project, and the usual cause
            # of one is one `../` too many — which is exactly what moving a directory
            # produces, and exactly what broke every relative path in this repository once.
            continue
        if candidate.exists():
            return True
    if by_name and "/" not in reference.strip("/"):
        # The slash test is a fast path and nothing more: the name comparison below cannot
        # match a reference containing one, so dropping the guard would walk the whole tree to
        # reach the same answer. A mutation that removes it is equivalent, not surviving —
        # worth writing down, because "a mutant lived" and "the mutant made no difference" are
        # the same observation until someone checks which.
        name = reference.strip("/")
        return any(path.name == name for path in root.rglob(name)
                   if ".git" not in path.parts)
    return False


def expand(root: Path, patterns: list[str]) -> list[Path]:
    paths: set[Path] = set()
    for pattern in patterns:
        if any(char in pattern for char in "*?"):
            paths.update(p for p in root.glob(pattern) if p.is_file())
        elif (root / pattern).is_file():
            paths.add(root / pattern)
    return sorted(paths)


def check_paths(root: Path) -> list[tuple[Path, str]]:
    instructions = set(expand(root, INSTRUCTIONS))
    unresolved = []
    for source in expand(root, NAVIGATION):
        text = source.read_text(encoding="utf-8", errors="replace")
        references = {reference: False for reference in links(text)}
        if source in instructions:
            for reference in prose(text):
                references.setdefault(reference, True)
        for reference, by_name in sorted(references.items()):
            if PLACEHOLDER.search(reference):
                continue
            target = literal_prefix(reference) if any(
                char in reference for char in "*?[") else reference
            if not target or ("/" not in target and not target.endswith(SUFFIXES)):
                continue
            if not resolves(root, source, target, by_name):
                unresolved.append((source, reference))
    return unresolved


# Review dates were checked here first and moved to `check-docs.py` at M5-04, which owns the
# dated-and-owned class and grades the response by tier. Two implementations of one rule give
# two answers the day one is edited, and this file's own header argues that at length.


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="repository root, for tests")
    parser.add_argument("--survey", action="store_true",
                        help="group unresolved references by area and exit 0")
    parser.add_argument("--today", help="override the date, for tests")
    args = parser.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parents[2]
    if not (root / "aios").is_dir():
        print(f"could not run: {root} is not an aios repository", file=sys.stderr)
        return COULD_NOT_RUN

    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"could not run: {args.today!r} is not a date", file=sys.stderr)
        return COULD_NOT_RUN

    unresolved = check_paths(root)

    if args.survey:
        grouped = collections.Counter(
            source.parent.relative_to(root).as_posix() or "." for source, _ in unresolved)
        for area, count in grouped.most_common():
            print(f"{count:4}  {area}")
        for source, reference in unresolved:
            print(f"      {source.relative_to(root).as_posix()} -> {reference}")
        print(f"\n{len(unresolved)} unresolved across {len(expand(root, NAVIGATION))} file(s) in scope.")
        return PASS

    for source, reference in unresolved:
        print(f"  violation: {source.relative_to(root).as_posix()} names "
              f"{reference}, which does not exist")
    total = len(unresolved)
    if total:
        print(f"\n{total} stale reference(s). An instruction naming something that is not "
              f"there reads exactly like one that is.")
        return FAIL

    print(f"{len(expand(root, NAVIGATION))} instruction file(s): "
          f"every path named in them exists.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
