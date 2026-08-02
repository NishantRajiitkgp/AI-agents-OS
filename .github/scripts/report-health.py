#!/usr/bin/env python3
"""`aios health` (M5-06). Monthly, Report-class.

PROVISIONAL. Moves into the binary at `M1-08`.

Four questions, and the design is explicit that the fourth is the one that invalidates the
other three if it goes wrong.

**Is it earning its keep** — median start-to-merge, rejection rate, gate failure rate by class,
rework rate.

**Is it decaying** — always-on line count over time, rules deleted versus added, overrides per
month, stale documents, ignored advisories, markdown volume against source volume.

**Is it learning** — incidents that produced a control ÷ total incidents. The design calls this
the single best indicator that this is an operating system rather than a filing system, and it
is the reason `M5-11` made the control field mandatory: the metric is only meaningful because
the schema will not accept an incident without an answer.

**Is the human still in the loop** — review debt, and median review time against diff size. If
review time flattens while diff size grows, the human has stopped reading, and every quality
claim in the design is void. Not "degraded". Void.

**Every metric reports what it cannot measure rather than omitting it.** A dashboard of the
four things that happen to be computable, with the eight that are not left off, reads as a
healthy system. This repository can currently measure five of thirteen — it has no merge
history, no CI runs and no reviews — and the report says so line by line, because a gap that
is visible gets closed and a gap that is invisible becomes the shape of the tool.

Exit 0 always, unless it could not run. A report that can fail is a gate.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import yaml

PASS, COULD_NOT_RUN = 0, 2

UNAVAILABLE = "not measurable yet"


def frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    try:
        data = yaml.safe_load(text[3:end]) if end != -1 else None
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def learning(root: Path) -> dict:
    """Incidents that produced a control, over total incidents."""
    incidents = sorted((root / "aios" / "incidents").glob("*.md"))
    with_control = [p for p in incidents
                    if str(frontmatter(p.read_text(encoding="utf-8")).get("control") or
                           "").strip()]
    if not incidents:
        return {"value": None, "why": "no incidents recorded"}
    return {"value": round(len(with_control) / len(incidents), 2),
            "detail": f"{len(with_control)} of {len(incidents)} incidents produced a control"}


def blocking_incidents(root: Path) -> list[str]:
    found = []
    for path in sorted((root / "aios" / "incidents").glob("*.md")):
        if frontmatter(path.read_text(encoding="utf-8")).get("blocks_work") is True:
            found.append(path.name)
    return found


def volume(root: Path) -> dict:
    """Markdown against source. Rising without bound is the shape of a system that documents
    instead of building."""
    def count(patterns: tuple[str, ...]) -> int:
        total = 0
        for pattern in patterns:
            for path in root.glob(pattern):
                if any(p in {".git", "node_modules", "__pycache__"} for p in path.parts):
                    continue
                total += len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        return total

    prose = count(("**/*.md",))
    source = count(("**/*.py", "**/*.rs", "**/*.mjs"))
    return {"markdown_lines": prose, "source_lines": source,
            "ratio": round(prose / source, 2) if source else None}


def gates(root: Path) -> dict:
    data = yaml.safe_load((root / "aios" / "gates.yml").read_text(encoding="utf-8")) or {}
    by_class: dict[str, int] = {}
    for gate in data.get("gates") or []:
        kind = gate.get("class", "unknown")
        # A gate whose class varies by tier (M3-02) carries a mapping rather than a name.
        # Counting it under one of its tiers would make the mix look more settled than it is.
        label = "varies by tier" if isinstance(kind, dict) else str(kind)
        by_class[label] = by_class.get(label, 0) + 1
    return by_class


def script(root: Path, name: str, *args: str) -> str | None:
    result = subprocess.run([sys.executable, str(root / ".github" / "scripts" / name), *args],
                            capture_output=True)
    if result.returncode == 2:
        return None
    return (result.stdout + result.stderr).decode("utf-8", "replace")


def commits(root: Path) -> int:
    result = subprocess.run(["git", "-C", str(root), "rev-list", "--count", "--all"],
                            capture_output=True)
    if result.returncode:
        return 0
    return int(result.stdout.decode().strip() or 0)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    if not (root / "aios").is_dir():
        print(f"could not run: {root} is not an aios repository", file=sys.stderr)
        return COULD_NOT_RUN

    history = commits(root)
    needs_history = (f"{UNAVAILABLE}: needs merge history, and this repository has "
                     f"{history} commit(s)")
    needs_ci = f"{UNAVAILABLE}: needs CI run history"
    needs_reviews = f"{UNAVAILABLE}: needs completed human reviews"

    always_on = script(root, "check-always-on.py")
    total = None
    if always_on and (match := re.search(r"ALWAYS-ON TOTAL\s+(\d+)", always_on)):
        total = int(match.group(1))

    report = {
        "earning_its_keep": {
            "median_start_to_merge": needs_history,
            "rejection_rate": needs_reviews,
            "gate_failure_rate_by_class": needs_ci,
            "rework_rate": needs_history,
        },
        "decaying": {
            "always_on_lines": total,
            "rules_deleted_vs_added": (needs_history if history < 2 else
                                       "see check-growth.py, which reports both per window"),
            "overrides_per_month": needs_history,
            "stale_documents": script(root, "check-docs.py") and
                               len(re.findall(r"::warning::", script(root, "check-docs.py") or "")),
            "ignored_advisories": needs_ci,
            "markdown_vs_source": volume(root),
            "gates_by_class": gates(root),
        },
        "learning": {
            "incidents_that_produced_a_control": learning(root),
            "incidents_blocking_work": blocking_incidents(root),
        },
        "human_in_the_loop": {
            "review_debt": needs_reviews,
            "median_review_time_vs_diff_size": needs_reviews,
        },
    }

    if args.format == "json":
        print(json.dumps(report, indent=2, default=str))
        return PASS

    print(f"aios health — {date.today().isoformat()}\n")
    measurable = unmeasurable = 0
    for section, metrics in report.items():
        print(f"{section.replace('_', ' ').upper()}")
        for name, value in metrics.items():
            if isinstance(value, str) and value.startswith(UNAVAILABLE):
                unmeasurable += 1
                print(f"  {name:<38} —  {value}")
            else:
                measurable += 1
                print(f"  {name:<38} {value}")
        print()

    print(f"{measurable} metric(s) measurable, {unmeasurable} not yet. The gaps are printed "
          f"rather than omitted: a dashboard of only what happens to be computable reads as a "
          f"healthy system.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
