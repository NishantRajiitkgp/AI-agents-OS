#!/usr/bin/env python3
"""Every Contract override is a dated, reasoned, human-committed incident entry.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

A Contract gate blocks and cannot be waived by the agent (06 §1). It can be overridden by a
human, and the price of that is a permanent record: an incident file carrying frontmatter that
names the gate, the date, the approver and the reason. This checks that the record and the
override agree, in both directions —

  a commit claiming `Override: <gate>` with no record          is an unrecorded bypass
  a record appearing with no commit claiming it                is a record smuggled in
  a record naming a gate that does not exist                   counts nothing
  a record naming a gate that is not Contract here             overrides nothing
  an existing record edited or deleted                         is the list being rewritten

The last is the one worth stating plainly. "The agent cannot edit the override list" (06 §1)
is enforceable here because it is a property of the diff, not of who wrote it.

What is NOT enforceable here is the word *human*. An agent can type a `human:` trailer as
easily as a person can. This is the same shape as ADR-012: the local check is consistency and
recording, and the unforgeable half is server-side — required review on the pull request
(M2-02) and, later, commit signatures (M5-03). Claiming otherwise would be the exact failure
this file exists to prevent, so the trailer is checked and its weight is stated, not oversold.

Records are also the input to the demotion counter (M3-08): three in thirty days on one gate
demotes it. `--list` emits them as JSON so that counter never re-parses this format.

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

TIERS = ("prototype", "internal", "production", "regulated")
REQUIRED = ("override", "date", "approved_by", "reason")
MINIMUM_REASON = 40
CLEAN, VIOLATION, CANNOT_RUN = 0, 1, 2

failures: list[str] = []


def fail(where: str, message: str) -> None:
    failures.append(f"  violation: {where}: {message}")


def git(root: Path, *arguments: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *arguments],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise CouldNotRun(f"git {' '.join(arguments)} failed: {result.stderr.strip()}")
    return result.stdout


def resolve_class(entry: dict, tier: str) -> str | None:
    """A gate's class at one tier. The registry allows a scalar or a per-tier mapping."""
    declared = entry.get("class")
    if isinstance(declared, dict):
        return declared.get(tier)
    return declared


def registered_gates(root: Path, tier: str) -> dict[str, str | None]:
    path = root / "aios" / "gates.yml"
    if not path.is_file():
        raise CouldNotRun(f"no gate registry at {relative(path)}")
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    gates: dict[str, str | None] = {}
    for section in ("gates", "planned"):
        for entry in document.get(section) or []:
            if entry.get("id"):
                gates[str(entry["id"])] = resolve_class(entry, tier)
    return gates


def resolve_tier(root: Path, override: str | None) -> str:
    if override:
        return override
    path = root / "aios" / "config.yml"
    if not path.is_file():
        raise CouldNotRun(f"no configuration at {relative(path)}")
    tier = (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("tier")
    if tier not in TIERS:
        raise CouldNotRun(f"tier is {tier!r}, which is not one of {', '.join(TIERS)}")
    return str(tier)


def parse_frontmatter(text: str) -> tuple[dict | None, str, str | None]:
    """Most incidents carry no frontmatter at all, so its absence is silence, not a finding."""
    if not text.startswith("---\n"):
        return None, "", "no YAML frontmatter"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "", "frontmatter is not terminated"
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        return None, "", f"frontmatter is not valid YAML: {exc}"
    if not isinstance(data, dict):
        return None, "", "frontmatter is not a mapping"
    return data, text[end + 4:], None


def demoted_gates(root: Path) -> set[str]:
    """Gates that were Contract when overridden and have since been demoted (D-017).

    Without this, the demotion counter and the override gate contradict each other: three
    overrides demote a gate to Ratchet, and the records that caused the demotion then become
    violations for naming a gate that is no longer Contract. The record is a statement about
    the past, so it is judged against what the gate was, not what demoting it made it.
    """
    path = root / "aios" / "demotions.yml"
    if not path.is_file():
        return set()
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return set()
    return {str(entry.get("gate")) for entry in document.get("demotions") or []}


def validate(record: dict, gates: dict[str, str | None], tier: str, today: dt.date,
             demoted: set[str]) -> None:
    where = f"override [{relative(record['_path'])}]"
    missing = [field for field in REQUIRED if not record.get(field)]
    if missing:
        fail(where, f"missing required field(s): {', '.join(missing)}")
        return

    gate = str(record["override"])
    if gate not in gates:
        fail(where, f"names gate {gate!r}, which is not in aios/gates.yml. An override of a "
                    f"gate that does not exist records nothing and counts nothing.")
    elif gates[gate] != "contract" and gate not in demoted:
        fail(where, f"names gate {gate!r}, which is {gates[gate] or 'unclassified'} at tier "
                    f"{tier}, not contract. Only a Contract gate blocks, so only a Contract "
                    f"gate can be overridden.")

    raw = record["date"]
    date = raw if isinstance(raw, dt.date) else None
    if date is None:
        try:
            date = dt.date.fromisoformat(str(raw))
        except ValueError:
            fail(where, f"date {raw!r} is not ISO YYYY-MM-DD")
            return
    if date > today:
        fail(where, f"is dated {date}, which is in the future")

    if len(str(record["reason"]).strip()) < MINIMUM_REASON:
        fail(where, f"reason is under {MINIMUM_REASON} characters. A reason too short to "
                    f"explain the risk accepted is not a reason.")
    if not str(record.get("_body", "")).strip():
        fail(where, "has frontmatter but no body explaining what was overridden and why")


def incident_dir(root: Path) -> Path:
    return root / "aios" / "incidents"


def collect_records(root: Path) -> list[dict]:
    directory = incident_dir(root)
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        if not text.startswith("---\n"):
            continue
        data, body, error = parse_frontmatter(text)
        if error:
            fail(f"incident [{relative(path)}]", error)
            continue
        if not data or "override" not in data:
            continue
        data["_body"] = body
        data["_path"] = path
        found.append(data)
    return found


def declared_overrides(root: Path, commit_range: str) -> tuple[list[str], set[str], list[str]]:
    """(gate ids claimed, commits carrying a human trailer, all commit shas in range)."""
    raw = git(root, "log", "--format=%H%x1f%B%x1e", commit_range)
    claimed: list[str] = []
    human: set[str] = set()
    shas: list[str] = []
    for chunk in raw.split("\x1e"):
        if not chunk.strip():
            continue
        sha, _, message = chunk.strip().partition("\x1f")
        shas.append(sha)
        for line in message.splitlines():
            stripped = line.strip()
            if stripped.lower().startswith("override:"):
                claimed.append(stripped.split(":", 1)[1].strip())
            if stripped.lower().startswith("human:") and stripped.split(":", 1)[1].strip():
                human.add(sha)
    return claimed, human, shas


def changed(root: Path, commit_range: str) -> list[tuple[str, str]]:
    raw = git(root, "diff", "--name-status", commit_range)
    entries = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            entries.append((parts[0][0], parts[-1]))
    return entries


def at_base(root: Path, base: str, path: str) -> str | None:
    result = subprocess.run(["git", "-C", str(root), "show", f"{base}:{path}"],
                            capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else None


def check_range(root: Path, commit_range: str) -> None:
    base = commit_range.split("..")[0]
    claimed, human, _ = declared_overrides(root, commit_range)

    introduced: set[str] = set()
    for status, path in changed(root, commit_range):
        if not path.startswith("aios/incidents/"):
            continue
        before = at_base(root, base, path)
        was_override = bool(before) and "override" in (parse_frontmatter(before)[0] or {})
        now = read_at(root, path)
        is_override = bool(now) and "override" in (parse_frontmatter(now)[0] or {})

        if status == "A" and is_override:
            introduced.add(str((parse_frontmatter(now)[0] or {}).get("override")))
        if was_override and status in ("M", "D", "R"):
            fail(f"override [{path}]",
                 "an existing override record was modified or deleted. The record is the "
                 "whole price of the override; a list that can be edited is not a record.")
        if was_override and is_override and before != now:
            fail(f"override [{path}]", "an existing override record changed content")

    for gate in claimed:
        if gate not in introduced:
            fail("commit trailer",
                 f"claims `Override: {gate}` but no incident record for it was added in this "
                 f"range. This is the unrecorded bypass the gate exists to stop.")
    for gate in sorted(introduced):
        if gate not in claimed:
            fail("override record",
                 f"records an override of {gate!r} but no commit in this range declares "
                 f"`Override: {gate}`. A record nobody claimed is a record smuggled in.")

    if introduced and not human:
        fail("commit trailer",
             "an override was introduced but no commit in this range carries a `human:` "
             "trailer. Advisory only — see this file's header for why the trailer is not the "
             "control that makes an override human.")


def read_at(root: Path, path: str) -> str | None:
    full = root / path
    return full.read_text(encoding="utf-8") if full.is_file() else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--range", dest="commit_range",
                        help="base..head; without it, only records are validated")
    parser.add_argument("--tier", choices=TIERS, help="override the configured tier")
    parser.add_argument("--today", help="ISO date, for tests")
    parser.add_argument("--list", action="store_true", help="emit records as JSON")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        tier = resolve_tier(root, args.tier)
        gates = registered_gates(root, tier)
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
        records = collect_records(root)
        demoted = demoted_gates(root)
        for record in records:
            validate(record, gates, tier, today, demoted)
        if args.commit_range:
            check_range(root, args.commit_range)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    if args.list:
        # Pure data on stdout, diagnostics on stderr. The demotion counter parses this, and a
        # violation line carrying `[a/path]` was enough to make the JSON unreadable — a data
        # command that sometimes emits prose is not a data command.
        print(json.dumps([
            {"gate": str(r.get("override")), "date": str(r.get("date")),
             "approved_by": str(r.get("approved_by")), "path": relative(r["_path"])}
            for r in records], indent=2))
        for line in failures:
            print(line, file=sys.stderr)
        return VIOLATION if failures else CLEAN

    for line in failures:
        print(line)
    if failures:
        print(f"\n{len(failures)} override violation(s).")
        return VIOLATION
    print(f"overrides are consistent: {len(records)} record(s) at tier {tier}.")
    return CLEAN


if __name__ == "__main__":
    raise SystemExit(main())
