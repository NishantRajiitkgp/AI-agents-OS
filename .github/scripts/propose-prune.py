#!/usr/bin/env python3
"""`aios prune` (M5-07). Monthly deletion proposals.

PROVISIONAL. Moves into the binary at `M1-08`.

Keeping something costs a little attention every day forever and nobody notices. Deleting it
risks one visible mistake that someone is blamed for. That asymmetry is why every repository
of this kind grows monotonically, and it is a fact about people rather than about tooling — so
the tooling has to push the other way.

The push is: **deletion is proposed by default, on a schedule, and reversible through git.**
Nobody has to be the person who suggested removing something. The proposal already exists; the
human either accepts it or records why not.

Candidates:

- rules with no violation in 90 days and no enforcement
- advisories ignored 20 consecutive times (`M3-12` owns the counter)
- documents past double their review interval that nothing links to
- requirements deferred for over a year
- tasks sitting in `todo` for over 90 days

**Rejections are recorded**, and a thing rescued three times stops being proposed. Without that
the monthly report becomes the same list forever, and a list that never changes is a list
nobody reads — which would leave the tool technically running and practically off.

This proposes. It never deletes. A tool that removes things on a timer is a different and much
worse tool, and the reversibility argument only holds while a human is the one acting.

Exit 0 always, unless it could not run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path

import yaml

PASS, COULD_NOT_RUN = 0, 2

RESCUES_BEFORE_LEAVING_ALONE = 3
DEFERRED_DAYS = 365
TODO_DAYS = 90


def load_rejections(root: Path) -> dict[str, list[dict]]:
    path = root / "aios" / "prune-rejections.yml"
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("rejected") or {}


def first_seen(root: Path, relative: str) -> date | None:
    """When the file entered the repository, from git rather than from a field.

    A `created_at` field would be a second place to keep a fact git already holds, and would
    be writable by the party the age check is about.
    """
    result = subprocess.run(
        ["git", "-C", str(root), "log", "--diff-filter=A", "--format=%as", "--", relative],
        capture_output=True)
    if result.returncode:
        return None
    stamps = result.stdout.decode("utf-8", "replace").split()
    return date.fromisoformat(stamps[-1]) if stamps else None


def stale_tasks(root: Path, today: date) -> list[dict]:
    found = []
    for path in sorted((root / "aios" / "tasks").rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        try:
            data = yaml.safe_load(text[3:end]) if end != -1 else {}
        except yaml.YAMLError:
            continue
        if not isinstance(data, dict) or data.get("status") != "todo":
            continue
        relative = path.relative_to(root).as_posix()
        born = first_seen(root, relative)
        if born and (today - born).days > TODO_DAYS:
            found.append({"kind": "task", "what": relative,
                          "why": f"in todo for {(today - born).days} days. Either it is not "
                                 f"going to be done, or it is not a task"})
    return found


def deferred_requirements(root: Path, today: date) -> list[dict]:
    found = []
    for path in sorted((root / "aios" / "requirements").rglob("*.md")):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8")
        for block in text.split("\n## ")[1:]:
            identifier = block.split("\u2014")[0].split()[0].strip()
            if "**Status:** deferred" not in block:
                continue
            born = first_seen(root, relative)
            if born and (today - born).days > DEFERRED_DAYS:
                found.append({"kind": "requirement", "what": f"{relative}#{identifier}",
                              "why": f"deferred for over {DEFERRED_DAYS} days. A year is long "
                                     f"enough that 'not now' has become 'no'"})
    return found


def stale_documents(root: Path) -> list[dict]:
    """Past double their interval *and* linked from nothing. Both halves matter: a document
    nobody reads and nobody links to is the case where deletion costs nothing."""
    result = subprocess.run(
        [sys.executable, str(root / ".github" / "scripts" / "check-docs.py"),
         "--tier", "prototype"], capture_output=True)
    output = (result.stdout + result.stderr).decode("utf-8", "replace")
    found = []
    for line in output.splitlines():
        if "::warning::" not in line or "past double" not in line:
            continue
        relative = line.split("::warning::", 1)[1].split(":", 1)[0].strip()
        linked = subprocess.run(
            ["git", "-C", str(root), "grep", "-l", "--fixed-strings", Path(relative).name],
            capture_output=True)
        readers = [line for line in linked.stdout.decode("utf-8", "replace").splitlines()
                   if line.strip() and not line.strip().endswith(relative)]
        if not readers:
            found.append({"kind": "document", "what": relative,
                          "why": "past double its review interval and nothing links to it"})
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--today")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    if not (root / "aios").is_dir():
        print(f"could not run: {root} is not an aios repository", file=sys.stderr)
        return COULD_NOT_RUN
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        print(f"could not run: {args.today!r} is not a date", file=sys.stderr)
        return COULD_NOT_RUN

    rejections = load_rejections(root)
    proposals: list[dict] = []
    for candidate in (stale_tasks(root, today) + deferred_requirements(root, today)
                      + stale_documents(root)):
        rescued = rejections.get(candidate["what"]) or []
        if len(rescued) >= RESCUES_BEFORE_LEAVING_ALONE:
            continue
        candidate["rescued"] = len(rescued)
        proposals.append(candidate)

    if args.format == "json":
        print(json.dumps({"proposals": proposals}, indent=2))
        return PASS

    if not proposals:
        print("Nothing to propose. Either everything here is earning its place, or the "
              "repository is too young for anything to have stopped — with 0 commits it is "
              "the second.")
        return PASS

    print(f"{len(proposals)} deletion proposal(s). Each is a pull request a human accepts or "
          f"declines; nothing is removed by this tool.\n")
    for proposal in proposals:
        rescued = (f" (rescued {proposal['rescued']}× already)" if proposal["rescued"] else "")
        print(f"  {proposal['kind']:<12} {proposal['what']}{rescued}")
        print(f"  {'':<12} {proposal['why']}\n")
    print(f"Declining one costs a line in aios/prune-rejections.yml. After "
          f"{RESCUES_BEFORE_LEAVING_ALONE} rescues it stops being proposed — a list that "
          f"never changes is a list nobody reads.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
