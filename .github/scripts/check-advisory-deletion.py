#!/usr/bin/env python3
"""Delete Advisory checks that are ignored 20 times running (M3-12).

PROVISIONAL. Becomes `aios prune advisories` when the binary exists (ADR-006).

An Advisory check reports and never blocks. That is a reasonable class for a heuristic, and a
terrible one for a check nobody reads: it costs CI time, it prints a warning into every log,
and its presence lets everyone believe the thing it looks for is being watched. The counter
exists because "we should look at that" is not a state anyone leaves.

Ignored means the check reported a finding and the pull request merged with the finding still
there. Not "the check ran and passed" — a clean advisory is doing its job. Twenty consecutive
ignored findings is the threshold, and it proposes deletion rather than deleting: the answer
is sometimes to promote the check to Ratchet instead, and a script cannot tell the difference
between a check nobody values and one everybody has been meaning to fix.

This is the sibling of the demotion counter (M3-08). That one demotes a Contract gate that
keeps being overridden; this one deletes an Advisory that keeps being ignored. Both encode the
same idea from opposite ends — a gate whose class does not match how people actually treat it
is lying, and the register should be corrected rather than the people.

**It reports zero today, and that is honest rather than passing.** The history it reads is CI
run history, and this repository has none: there are no commits, no pull requests and no
finished workflow runs. The mechanism is here and tested against fixtures so that it starts
counting from the first real run rather than being written after somebody notices the logs.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config

PASS, PROPOSE, COULD_NOT_RUN = 0, 1, 2

CONSECUTIVE_LIMIT = 20


def advisory_gates(root: Path, tier: str) -> list[str]:
    """Every gate that resolves to advisory at the active tier.

    Resolved rather than declared, because a gate whose class varies by tier is Advisory only
    at some of them, and deleting one for being ignored at prototype would remove a check that
    blocks at production.
    """
    data = yaml.safe_load((root / "aios" / "gates.yml").read_text(encoding="utf-8")) or {}
    ids = []
    for gate in data.get("gates") or []:
        declared = gate.get("class")
        resolved = declared.get(tier) if isinstance(declared, dict) else declared
        if resolved == "advisory":
            ids.append(gate["id"])
    return sorted(ids)


def consecutive_ignored(history: list[dict], gate_id: str) -> int:
    """How many merged pull requests in a row carried an unaddressed finding from this gate.

    Counts backwards from the most recent and stops at the first run where the gate was clean
    or its finding was addressed. A streak that was broken once is not a streak: the point is
    to find checks nobody is acting on now, not to hold a grudge about last quarter.
    """
    streak = 0
    for run in reversed(history):
        findings = run.get("findings") or {}
        state = findings.get(gate_id)
        if state == "ignored":
            streak += 1
        elif state in ("clean", "addressed", None):
            # `None` — the gate did not run — breaks the streak rather than extending it. A
            # gate that was switched off for ten runs has not been ignored ten times; nobody
            # was shown anything to ignore.
            break
    return streak


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="repository root; discovered if omitted")
    parser.add_argument("--history", help="JSON file of run history, for tests")
    args = parser.parse_args()

    try:
        root = Path(args.root) if args.root else find_config().parent.parent
        config = yaml.safe_load(
            (root / "aios" / "config.yml").read_text(encoding="utf-8")) or {}
        tier = config.get("tier", "prototype")
        advisories = advisory_gates(root, tier)
    except (CouldNotRun, OSError, KeyError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    history: list[dict] = []
    if args.history:
        try:
            history = json.loads(Path(args.history).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"could not run: {args.history}: {exc}", file=sys.stderr)
            return COULD_NOT_RUN

    if not history:
        print(f"{len(advisories)} advisory check(s) at tier {tier}, and no run history to "
              f"judge them by.")
        print(f"This repository has no finished pull-request runs yet, so nothing has had the "
              f"chance to be ignored {CONSECUTIVE_LIMIT} times. Reporting zero here is a "
              f"statement about the history, not a clean bill of health for the checks.")
        return PASS

    proposals = []
    for gate_id in advisories:
        streak = consecutive_ignored(history, gate_id)
        if streak >= CONSECUTIVE_LIMIT:
            proposals.append((gate_id, streak))

    for gate_id, streak in proposals:
        print(f"  {gate_id}: reported a finding that merged unaddressed {streak} time(s) in a "
              f"row.")
        print(f"      Either it is not worth running, or it is worth blocking on. Both are "
              f"edits to aios/gates.yml; leaving it Advisory is the one answer the evidence "
              f"rules out.")

    if proposals:
        print(f"\n{len(proposals)} advisory check(s) proposed for deletion or promotion.")
        print("Proposed, not done. A script cannot tell a check nobody values from one "
              "everybody has been meaning to fix, and deleting the second would remove the "
              "only record that the problem exists.")
        return PROPOSE

    print(f"{len(advisories)} advisory check(s) at tier {tier}, none ignored "
          f"{CONSECUTIVE_LIMIT} times running across {len(history)} run(s).")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
