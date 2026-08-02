#!/usr/bin/env python3
"""Instrument the verifier (M4-10).

PROVISIONAL. Becomes `aios health verifier` when the binary exists (ADR-006).

The verifier subagent (M4-02) reviews a diff against a task's acceptance criteria and returns
structured findings. Two numbers decide whether it is worth its context budget:

  findings per review   how much it says
  survival rate         how much of what it says causes an actual code change

The second is the one that matters, and it is the one nobody measures. A verifier producing
twelve findings per review of which none survives is worse than one producing none: it costs
tokens, it costs the reader's attention, and it manufactures the feeling that the diff was
reviewed. The failure mode being watched for is not a verifier that misses things — it is a
verifier that is fluent.

Survival is measured structurally, not by asking anyone. A finding names a file and a line; it
survived if a commit after the review touched that file within a window of that line. That is
a proxy and it is generous in one direction: an unrelated later edit to the same lines counts
as survival. It is deliberately not the other kind of generous — nothing here reads the
agent's own claim about whether its finding was useful, because self-report is worth least
exactly where this measurement is aimed.

**It reports nothing today, honestly.** No verifier review has run against a real diff in this
repository, because there are no pull requests. The parser and the arithmetic are here and
tested against fixtures so the first real review is counted rather than being the moment
somebody starts thinking about how to count.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from aios_state import CouldNotRun, find_config

PASS, COULD_NOT_RUN = 0, 2

# `- [blocking] src/main.rs:42 - acceptance criterion 2 is not satisfied`
FINDING = re.compile(
    r"^\s*-\s*\[(?P<severity>blocking|major|nit)\]\s+"
    r"(?P<file>[^\s:]+):(?P<line>\d+)\s*[-–—]\s*(?P<text>.+)$")

# How far from the named line a later edit still counts as addressing it. Small on purpose:
# a change forty lines away in the same file is a different change.
LINE_WINDOW = 10


def parse_findings(text: str) -> list[dict]:
    """Read the verifier's structured output.

    A line that looks like a finding but does not parse is returned as malformed rather than
    dropped. Silently skipping them would make a verifier that formats badly look like one
    that found nothing, and those need opposite responses.
    """
    findings = []
    for raw in text.splitlines():
        match = FINDING.match(raw)
        if match:
            findings.append({
                "severity": match.group("severity"),
                "file": match.group("file"),
                "line": int(match.group("line")),
                "text": match.group("text").strip(),
                "malformed": False,
            })
        elif re.match(r"^\s*-\s*\[", raw):
            findings.append({"severity": None, "file": None, "line": None,
                             "text": raw.strip(), "malformed": True})
    return findings


def survived(finding: dict, later_changes: list[dict]) -> bool:
    """Did a later change touch what this finding pointed at?"""
    if finding.get("malformed"):
        return False
    for change in later_changes:
        if change.get("file") != finding["file"]:
            continue
        for line in change.get("lines") or []:
            if abs(int(line) - finding["line"]) <= LINE_WINDOW:
                return True
    return False


def summarise(reviews: list[dict]) -> dict:
    per_review = []
    total = survivors = malformed = 0
    by_severity: dict[str, list[int]] = {}

    for review in reviews:
        findings = parse_findings(review.get("output", ""))
        later = review.get("later_changes") or []
        per_review.append(len(findings))
        for finding in findings:
            total += 1
            if finding["malformed"]:
                malformed += 1
                continue
            kept = survived(finding, later)
            survivors += 1 if kept else 0
            bucket = by_severity.setdefault(finding["severity"], [0, 0])
            bucket[0] += 1
            bucket[1] += 1 if kept else 0

    return {
        "reviews": len(reviews),
        "findings": total,
        "malformed": malformed,
        "survivors": survivors,
        "median_per_review": statistics.median(per_review) if per_review else 0,
        "survival_percent": round(survivors * 100 / total) if total else 0,
        "by_severity": by_severity,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="repository root; discovered if omitted")
    parser.add_argument("--reviews",
                        help="JSON file of recorded verifier reviews; defaults to "
                             "aios/measurements/verifier-reviews.json")
    args = parser.parse_args()

    try:
        root = Path(args.root) if args.root else find_config().parent.parent
    except (CouldNotRun, OSError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    path = Path(args.reviews) if args.reviews else (
        root / "aios" / "measurements" / "verifier-reviews.json")

    if not path.is_file():
        print("No verifier reviews recorded, so there is nothing to measure.")
        print(f"Expected at {path.relative_to(root) if path.is_absolute() and root in path.parents else path}.")
        print()
        print("This is the honest answer rather than a passing one. The verifier has never run "
              "against a real diff here — there are no pull requests — so its findings-per-"
              "review and survival rate are unknown, and the review packet says so instead of "
              "printing a zero that reads like a clean review.")
        return PASS

    try:
        reviews = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"could not run: {path}: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    stats = summarise(reviews)
    print(f"verifier, across {stats['reviews']} review(s):")
    print(f"  findings                {stats['findings']}")
    print(f"  median per review       {stats['median_per_review']}")
    print(f"  survived to a change    {stats['survivors']} ({stats['survival_percent']}%)")
    if stats["malformed"]:
        print(f"  malformed               {stats['malformed']} — findings that look like "
              f"findings and name no location, which cannot be acted on or measured")
    for severity, (count, kept) in sorted(stats["by_severity"].items()):
        rate = round(kept * 100 / count) if count else 0
        print(f"  {severity:<22}{count} finding(s), {rate}% survived")

    print()
    if stats["findings"] and stats["survival_percent"] < 20:
        print("Under a fifth of what it says causes a change. A verifier producing findings "
              "nobody acts on is not neutral — it spends context, it spends the reader's "
              "attention, and it produces the impression that the diff was reviewed. Consider "
              "narrowing what it is asked to look for before adding to it.")
    print("Survival is a proxy: a later edit near the named line counts, including one that "
          "had nothing to do with the finding. It is generous in that direction on purpose, "
          "so a low number is hard to argue with.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
