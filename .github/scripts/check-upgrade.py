#!/usr/bin/env python3
"""`aios upgrade` (M5-10). What changed in the template, and what it costs to take.

PROVISIONAL. Moves into the binary at `M1-08`.

A project clones this template and then diverges, which is expected and fine: **the template is
a starting point, not a dependency.** Nothing here is pushed. A project pins a template version
and may decline anything, permanently, without explaining itself.

Every change is one of two kinds, and the split is the useful part:

- **mechanical** — a gate script fixed, a CLI bug, a message reworded. Nothing the project has
  decided is affected, so it can be applied without a conversation.
- **judgement** — a new gate, a schema change, a tightened default. This asks the project to
  accept a new constraint, and lands as a pull request with the rationale attached rather than
  as a diff that appears one morning.

Getting that boundary wrong in the safe direction costs a pull request nobody needed. Getting
it wrong in the other direction means an upgrade silently added a gate that starts failing
builds on a Friday, and the project never agreed to it. So anything ambiguous is judgement.

Reads a `CHANGELOG.md` in the template, whose entries carry the classification. Classification
lives with the change because only its author knows whether it alters a decision, and inferring
it from a diff would be guessing at exactly the point where guessing is expensive.

Exit 0 up to date or only mechanical changes pending, 1 judgement changes pending, 2 could not
run.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

CURRENT, JUDGEMENT_PENDING, COULD_NOT_RUN = 0, 1, 2

MECHANICAL, JUDGEMENT = "mechanical", "judgement"
ENTRY = re.compile(r"^##\s+(?P<version>\S+)\s*$", re.M)
CHANGE = re.compile(r"^-\s*\*\*(?P<kind>mechanical|judgement)\*\*\s*[—:-]\s*(?P<what>.+)$",
                    re.M | re.I)


def parse(text: str) -> list[dict]:
    """Changelog into versions, newest first, each with classified changes."""
    versions = []
    marks = list(ENTRY.finditer(text))
    for index, mark in enumerate(marks):
        body = text[mark.end():marks[index + 1].start() if index + 1 < len(marks) else len(text)]
        changes = [{"kind": m.group("kind").lower(), "what": m.group("what").strip()}
                   for m in CHANGE.finditer(body)]
        unclassified = [line for line in body.splitlines()
                        if line.strip().startswith("- ") and not CHANGE.match(line.strip())]
        versions.append({"version": mark.group("version"), "changes": changes,
                         "unclassified": unclassified})
    return versions


def newer_than(versions: list[dict], pinned: str) -> list[dict]:
    """Everything above the pin, in changelog order.

    Compared by position rather than by parsing version numbers: the changelog is already in
    order, and a version scheme this does not recognise would otherwise silently return
    nothing — a tool reporting "up to date" because it could not read the file.
    """
    names = [v["version"] for v in versions]
    if pinned not in names:
        raise LookupError(f"pinned version {pinned!r} is not in the changelog "
                          f"(it has {', '.join(names[:5])}…)")
    return versions[:names.index(pinned)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--changelog", type=Path, help="template changelog")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    changelog = args.changelog or (root / "CHANGELOG.md")

    try:
        config = yaml.safe_load((root / "aios" / "config.yml").read_text(encoding="utf-8"))
        pinned = str((config.get("template") or {}).get("version") or "").strip()
    except (OSError, AttributeError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if not pinned:
        print("could not run: aios/config.yml pins no template version, so there is no "
              "baseline to compare against", file=sys.stderr)
        return COULD_NOT_RUN
    if not changelog.is_file():
        print(f"could not run: no template changelog at {changelog}. Nothing is fetched "
              f"implicitly; upgrading is something a project does on purpose.", file=sys.stderr)
        return COULD_NOT_RUN

    try:
        versions = newer_than(parse(changelog.read_text(encoding="utf-8")), pinned)
    except LookupError as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    mechanical = [(v["version"], c) for v in versions for c in v["changes"]
                  if c["kind"] == MECHANICAL]
    judgement = [(v["version"], c) for v in versions for c in v["changes"]
                 if c["kind"] == JUDGEMENT]
    unclassified = [(v["version"], line) for v in versions for line in v["unclassified"]]

    if not versions:
        print(f"Pinned at {pinned}, which is the newest. Nothing to apply.")
        return CURRENT

    print(f"Pinned at {pinned}. {len(versions)} newer version(s).\n")
    for version, change in mechanical:
        print(f"  mechanical  {version}  {change['what']}")
    for version, change in judgement:
        print(f"  judgement   {version}  {change['what']}")
    for version, line in unclassified:
        # Treated as judgement, deliberately. The safe direction costs a pull request nobody
        # needed; the other silently adds a gate the project never agreed to.
        print(f"  judgement   {version}  {line.strip()[2:]} (unclassified, so treated as "
              f"judgement)")

    print(f"\n{len(mechanical)} mechanical change(s) can be applied without a conversation.")
    if judgement or unclassified:
        print(f"{len(judgement) + len(unclassified)} ask the project to accept something new "
              f"and land as a pull request with the rationale. Declining any of them "
              f"permanently is a supported answer — the template is a starting point, not a "
              f"dependency.")
        return JUDGEMENT_PENDING
    return CURRENT


if __name__ == "__main__":
    raise SystemExit(main())
