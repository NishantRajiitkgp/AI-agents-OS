#!/usr/bin/env python3
"""Documentation classification (M5-03) and the staleness sweep (M5-04).

PROVISIONAL. Moves into the binary at `M1-08`.

Every document is exactly one of four things, and a document that is none of them does not get
written:

- **generated** — never hand-edited; regeneration is verified in CI.
- **checked** — a mechanical guard protects it from going stale.
- **dated and owned** — carries an owner and a review date, because nothing mechanical can
  tell whether it is still true.
- **immutable** — ADRs and incidents. Superseded, never edited.

The classes are not a taxonomy for its own sake. They are the exhaustive list of *ways a
document can be prevented from rotting*, and the reason the fourth exists is that "someone will
notice" is not one of them. Forcing the choice at writing time is what makes the cost of a new
document visible while it is still cheap not to write it.

Most documents here are classified by **where they live**, not by a header. A per-file marker
would be a second place to keep in sync, and this repository already has an incident about two
implementations of one fact. `docs/decisions/` is immutable because it is the ADR directory —
that is not a convention a file needs to restate. Explicit frontmatter overrides the location,
which is what a new directory or an exception needs.

**Staleness (M5-04)** falls out of the third class. Past the review date, report. Past double
the interval, block — but only at `production` tier and above, because at `prototype` the right
response to a stale document is often to delete it, and a gate that blocks the build cannot be
answered with a deletion at three in the morning.

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

GENERATED, CHECKED, DATED, IMMUTABLE = "generated", "checked", "dated-and-owned", "immutable"
CLASSES = {GENERATED, CHECKED, DATED, IMMUTABLE}

# Location is the classification. Longest prefix wins, so a subdirectory can differ from its
# parent without either of them saying so twice.
BY_LOCATION = {
    "docs/decisions/": IMMUTABLE,
    "aios/incidents/": IMMUTABLE,
    "docs/design/": IMMUTABLE,
    "docs/runbooks/": DATED,
    "aios/requirements/": CHECKED,
    "aios/tasks/": CHECKED,
    "aios/standards/": CHECKED,
    "aios/bin/probe/results/": IMMUTABLE,
    "aios/bin/probe/": CHECKED,
    ".claude/": CHECKED,
    ".cursor/": CHECKED,
    "AGENTS.md": CHECKED,
    "CLAUDE.md": CHECKED,
    "README.md": CHECKED,
    "aios/glossary.md": CHECKED,
    "aios/open-questions.md": CHECKED,
    "docs/architecture.md": DATED,
}

SKIP = (".git/", "node_modules/", "tests/fixtures/")

DEFAULT_REVIEW_MONTHS = 6


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def classify(relative: str, data: dict) -> tuple[str | None, str]:
    """Its class, and where that came from."""
    declared = str(data.get("doc_class") or "").strip()
    if declared:
        return (declared if declared in CLASSES else None), "frontmatter"
    matches = [prefix for prefix in BY_LOCATION if relative.startswith(prefix)]
    if matches:
        longest = max(matches, key=len)
        return BY_LOCATION[longest], f"location ({longest})"
    return None, "nothing"


def months_between(earlier: date, later: date) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def check_dated(relative: str, data: dict, today: date, tier: str) -> list[tuple[bool, str]]:
    """Returns (blocking, message) pairs. Report past the date, block past double."""
    problems: list[tuple[bool, str]] = []
    owner = str(data.get("owner") or "").strip()
    review_by = data.get("review_by")

    if not owner:
        problems.append((True, f"{relative}: dated-and-owned with no owner. An unowned review "
                               f"date is a date nobody is going to act on"))
    if not isinstance(review_by, date):
        problems.append((True, f"{relative}: dated-and-owned with no review_by date"))
        return problems

    if review_by >= today:
        return problems

    overdue = months_between(review_by, today)
    interval = int(data.get("review_months") or DEFAULT_REVIEW_MONTHS)
    doubled = overdue >= interval

    blocking = doubled and tier in ("production", "regulated")
    detail = (f"{relative}: review_by was {review_by}, {overdue} month(s) ago")
    if doubled:
        detail += (f" — past double its {interval}-month interval. "
                   + ("Blocking at this tier." if blocking
                      else "Reported rather than blocking at this tier, where deleting it is "
                           "often the right answer and a blocked build cannot be answered "
                           "with a deletion."))
    problems.append((blocking, detail))
    return problems


def documents(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.md")
                  if not any(part in {".git", "node_modules", "__pycache__"}
                             for part in path.parts)
                  and not str(path.relative_to(root)).replace("\\", "/").startswith(SKIP))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--today", help="override the date, for tests")
    parser.add_argument("--tier", help="override the tier, for tests")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    try:
        config = yaml.safe_load((root / "aios" / "config.yml").read_text(encoding="utf-8"))
        tier = args.tier or config["tier"]
        today = date.fromisoformat(args.today) if args.today else date.today()
    except (OSError, KeyError, TypeError, ValueError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    blocking: list[str] = []
    reported: list[str] = []
    counts: dict[str, int] = {}

    for path in documents(root):
        relative = path.relative_to(root).as_posix()
        data = frontmatter(path.read_text(encoding="utf-8", errors="replace"))
        kind, source = classify(relative, data)

        if kind is None:
            blocking.append(
                f"{relative}: unclassified. Every document is generated, checked, "
                f"dated-and-owned, or immutable — those are the four ways a document is kept "
                f"from rotting, and a document that is none of them will. Put it somewhere "
                f"classified, or declare `doc_class:` in frontmatter."
                + (f" It declares doc_class: {data.get('doc_class')!r}, which is not one of "
                   f"them." if source == "frontmatter" else ""))
            continue

        counts[kind] = counts.get(kind, 0) + 1
        if kind == DATED:
            for blocks, message in check_dated(relative, data, today, tier):
                (blocking if blocks else reported).append(message)

    for message in reported:
        print(f"::warning::{message}")
    for message in blocking:
        print(f"  violation: {message}")

    summary = ", ".join(f"{count} {kind}" for kind, count in sorted(counts.items()))
    if blocking:
        print(f"\n{len(blocking)} violation(s). Classified: {summary}.")
        return FAIL
    print(f"Every document is classified: {summary}."
          + (f" {len(reported)} past review, reported at tier {tier}." if reported else ""))
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
