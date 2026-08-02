#!/usr/bin/env python3
"""Three overrides of one Contract gate in thirty days demotes it to Ratchet.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

D-017, and the mechanism 06 §2 claims no surveyed framework has. A gate being overridden
repeatedly is *already* not blocking; it is blocking dishonestly, and teaching everyone that
overrides are routine. Demoting it makes that true out loud, and preserves the credibility of
the gates that remain.

The counting window is any thirty-day span anchored at an override's own date — not the thirty
days before today. A gate that demotes on Tuesday and not on Wednesday, with nobody having
changed anything, has a verdict that depends on when CI happened to run, and a rule like that
cannot be argued with in review.

Demotion is automatic *and* a reviewable commit, which sounds contradictory and is not: this
computes the demotion and `--apply` writes it, but a human commits it. Until that commit
exists the gate fails, so the demotion cannot be quietly declined. Same shape as the ratchet
baselines, deliberately.

The security subset (07) never demotes — an important control does not become optional because
it is inconvenient. It is not silenced either: crossing the threshold is still recorded, since
a security gate overridden three times means either the gate or the code is wrong.

Exit codes: 0 clean · 1 violation · 2 could not run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative

WINDOW_DAYS = 30
THRESHOLD = 3
TIERS = ("prototype", "internal", "production", "regulated")
CLEAN, VIOLATION, CANNOT_RUN = 0, 1, 2

failures: list[str] = []


def fail(where: str, message: str) -> None:
    failures.append(f"  violation: {where}: {message}")


def load(path: Path) -> dict:
    if not path.is_file():
        raise CouldNotRun(f"no file at {relative(path)}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotRun(f"{relative(path)} is not valid YAML: {exc}")


def resolve_tier(root: Path, override: str | None) -> str:
    if override:
        return override
    tier = load(root / "aios" / "config.yml").get("tier")
    if tier not in TIERS:
        raise CouldNotRun(f"tier is {tier!r}, which is not one of {', '.join(TIERS)}")
    return str(tier)


def gate_table(root: Path, tier: str) -> dict[str, dict]:
    document = load(root / "aios" / "gates.yml")
    table: dict[str, dict] = {}
    for entry in document.get("gates") or []:
        declared = entry.get("class")
        resolved = declared.get(tier) if isinstance(declared, dict) else declared
        table[str(entry.get("id"))] = {
            "class": resolved,
            "security": bool(entry.get("security")),
            "title": entry.get("title"),
        }
    return table


def overrides(root: Path) -> list[dict]:
    """Read override records through check-overrides.py rather than re-parsing them.

    Two readers of one format drift, and the drift shows up as a counter that disagrees with
    the gate about what an override is — which is the failure this whole subsystem is for.
    """
    script = Path(__file__).resolve().parent / "check-overrides.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(root), "--list"],
        capture_output=True, text=True)
    if result.returncode == CANNOT_RUN:
        raise CouldNotRun(f"override records could not be read: {result.stderr.strip()}")
    try:
        records = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise CouldNotRun(f"check-overrides.py --list produced no record list: {exc}")
    for record in records:
        try:
            record["_date"] = dt.date.fromisoformat(record["date"])
        except ValueError:
            raise CouldNotRun(f"override record {record.get('path')} has an unusable date")
    return records


def crossings(records: list[dict]) -> dict[str, dict]:
    """Per gate, the worst thirty-day window and the records that made it."""
    by_gate: dict[str, list[dict]] = {}
    for record in records:
        by_gate.setdefault(record["gate"], []).append(record)

    worst: dict[str, dict] = {}
    for gate, entries in by_gate.items():
        entries.sort(key=lambda r: r["_date"])
        best: list[dict] = []
        for index, anchor in enumerate(entries):
            window = [other for other in entries[index:]
                      if (other["_date"] - anchor["_date"]).days < WINDOW_DAYS]
            if len(window) > len(best):
                best = window
        if len(best) >= THRESHOLD:
            worst[gate] = {"count": len(best),
                           "first": best[0]["_date"], "last": best[-1]["_date"],
                           "records": [entry["path"] for entry in best]}
    return worst


def check(root: Path, tier: str) -> tuple[dict, dict]:
    gates = gate_table(root, tier)
    ledger = load(root / "aios" / "demotions.yml")
    recorded = {str(entry.get("gate")): entry for entry in ledger.get("demotions") or []}
    exempted = {str(entry.get("gate")): entry for entry in ledger.get("exempt_crossings") or []}
    crossed = crossings(overrides(root))

    for gate, detail in sorted(crossed.items()):
        info = gates.get(gate)
        if info is None:
            fail(f"demotion [{gate}]", "overrides name a gate absent from aios/gates.yml")
            continue
        where = f"demotion [{gate}]"
        summary = (f"{detail['count']} overrides between {detail['first']} and "
                   f"{detail['last']}")

        if info["security"]:
            if gate not in exempted:
                fail(where, f"{summary} crossed the threshold. It is in the security subset "
                            f"so it does not demote, but the crossing must still be recorded "
                            f"in exempt_crossings — exemption from demotion is not exemption "
                            f"from being noticed.")
            if info["class"] != "contract":
                fail(where, f"is in the security subset but is {info['class']} at tier "
                            f"{tier}. A security gate must not have been demoted.")
            continue

        if gate not in recorded:
            fail(where, f"{summary}, which is {THRESHOLD} or more in {WINDOW_DAYS} days, but "
                        f"no entry exists in aios/demotions.yml. Run --apply and commit it.")
        if info["class"] == "contract":
            fail(where, f"{summary} but it is still contract at tier {tier}. A gate overridden "
                        f"this often is already not blocking; leaving it contract is the "
                        f"dishonest state D-017 exists to end.")

    for gate, entry in sorted(recorded.items()):
        if gate not in crossed:
            fail(f"demotion [{gate}]",
                 f"is recorded as demoted, but its overrides never reached {THRESHOLD} in "
                 f"{WINDOW_DAYS} days. A demotion nobody earned is a gate switched off.")
        for field in ("gate", "demoted_on", "from", "to", "triggered_by", "report", "closed"):
            if field not in entry:
                fail(f"demotion [{gate}]", f"missing required field {field!r}")
        if entry.get("to") != "ratchet":
            fail(f"demotion [{gate}]", "D-017 demotes to ratchet, not to anything weaker")

    for gate in sorted(exempted):
        if gate not in crossed:
            fail(f"demotion [{gate}]",
                 "is recorded as an exempt crossing but never crossed the threshold")
        elif not gates.get(gate, {}).get("security"):
            fail(f"demotion [{gate}]",
                 "is recorded as exempt but is not in the security subset")

    return crossed, gates


def apply(root: Path, crossed: dict, gates: dict, today: dt.date) -> None:
    """Write what the counter computed. A human commits it; that is the review."""
    path = root / "aios" / "demotions.yml"
    document = load(path)
    demotions = list(document.get("demotions") or [])
    exempt = list(document.get("exempt_crossings") or [])
    known = {str(entry.get("gate")) for entry in demotions}
    known_exempt = {str(entry.get("gate")) for entry in exempt}
    written = 0

    for gate, detail in sorted(crossed.items()):
        info = gates.get(gate)
        if info is None:
            continue
        if info["security"]:
            if gate in known_exempt:
                continue
            exempt.append({
                "gate": gate, "noticed_on": today.isoformat(),
                "count": detail["count"], "window": f"{detail['first']}..{detail['last']}",
                "triggered_by": detail["records"],
                "report": (f"{gate} was overridden {detail['count']} times in under "
                           f"{WINDOW_DAYS} days. It is exempt from demotion (07), so it "
                           f"remains Contract. Either the gate is miscalibrated or the code "
                           f"keeps being wrong in the same way; a human must decide which."),
                "closed": False})
            written += 1
            continue
        if gate in known:
            continue
        demotions.append({
            "gate": gate, "demoted_on": today.isoformat(),
            "from": "contract", "to": "ratchet",
            "window": f"{detail['first']}..{detail['last']}",
            "triggered_by": detail["records"],
            "report": (f"{gate} was overridden {detail['count']} times in under "
                       f"{WINDOW_DAYS} days and is demoted to Ratchet. It was already not "
                       f"blocking; this makes that explicit. Closing this report requires "
                       f"deciding whether the gate was wrong or the work was."),
            "closed": False})
        written += 1

    document["demotions"] = demotions
    document["exempt_crossings"] = exempt
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True, width=95),
                    encoding="utf-8")
    print(f"wrote {written} entry(s) to {relative(path)}. "
          f"Flip the class in aios/gates.yml and commit both.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--tier", choices=TIERS, help="override the configured tier")
    parser.add_argument("--today", help="ISO date, for tests")
    parser.add_argument("--apply", action="store_true",
                        help="write the computed demotions for a human to commit")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        tier = resolve_tier(root, args.tier)
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
        crossed, gates = check(root, tier)
        if args.apply:
            apply(root, crossed, gates, today)
            return CLEAN
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    for line in failures:
        print(line)
    if failures:
        print(f"\n{len(failures)} demotion violation(s).")
        return VIOLATION
    print(f"no gate is being overridden routinely: {len(crossed)} gate(s) at or over "
          f"{THRESHOLD} overrides in {WINDOW_DAYS} days, all recorded.")
    return CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
