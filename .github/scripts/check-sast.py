#!/usr/bin/env python3
"""Decide what static-analysis findings mean at this repository's tier.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

SAST is the one row in 06 §3 that passes through all four classes in order — Advisory,
Ratchet, Contract, Contract — which makes it the row that most needs the tier mechanism to be
real rather than declared. A workflow step is static and cannot follow the tier, so the
analyser uploads findings and this decides what they cost:

  prototype   advisory  report them, never block
  internal    ratchet   block only if there are more than the measured baseline
  production  contract  block on any high-severity finding
  regulated   contract  the same

Severity comes from the SARIF `security-severity` property, which is a CVSS-style number.
7.0 is the conventional high boundary and is what "SAST (high severity)" in 06 §3 means.

Exit codes: 0 acceptable at this tier · 1 blocked · 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative

TIERS = ("prototype", "internal", "production", "regulated")
CLASS_BY_TIER = {"prototype": "advisory", "internal": "ratchet",
                 "production": "contract", "regulated": "contract"}
HIGH = 7.0
RATCHET_ID = "sast_high_findings"


def resolve_tier(root: Path, override: str | None) -> str:
    if override:
        return override
    path = root / "aios" / "config.yml"
    if not path.is_file():
        raise CouldNotRun(f"no configuration at {relative(path)}, so no tier to resolve")
    config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    tier = config.get("tier")
    if tier not in TIERS:
        raise CouldNotRun(f"tier is {tier!r}, which is not one of {', '.join(TIERS)}")
    return str(tier)


def severity_of(result: dict, rules: dict[str, dict]) -> float:
    """A finding's severity, taken from its rule when the result does not carry one."""
    properties = result.get("properties") or {}
    rule = rules.get(str(result.get("ruleId", "")), {})
    raw = (properties.get("security-severity")
           or (rule.get("properties") or {}).get("security-severity"))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def high_findings(path: Path) -> list[tuple[str, float, str]]:
    if not path.is_file():
        raise CouldNotRun(f"no SARIF at {relative(path)}, so nothing was analysed")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CouldNotRun(f"{relative(path)} is not valid SARIF: {exc}")

    findings: list[tuple[str, float, str]] = []
    for run in document.get("runs") or []:
        driver = ((run.get("tool") or {}).get("driver") or {})
        rules = {str(rule.get("id")): rule for rule in driver.get("rules") or []}
        for result in run.get("results") or []:
            severity = severity_of(result, rules)
            if severity < HIGH:
                continue
            where = "unknown"
            for location in result.get("locations") or []:
                physical = (location.get("physicalLocation") or {})
                where = ((physical.get("artifactLocation") or {}).get("uri")) or where
                break
            findings.append((str(result.get("ruleId", "?")), severity, where))
    return findings


def baseline(root: Path) -> int | None:
    path = root / "aios" / "ratchets.yml"
    if not path.is_file():
        return None
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for entry in document.get("ratchets") or []:
        if entry.get("id") == RATCHET_ID:
            return int(entry.get("baseline"))
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sarif", type=Path, required=True, help="SARIF file to read")
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--tier", choices=TIERS, help="override the configured tier")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        tier = resolve_tier(root, args.tier)
        findings = high_findings(args.sarif)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    gate_class = CLASS_BY_TIER[tier]
    for rule, severity, where in findings:
        print(f"  finding: {rule} ({severity}) in {where}")
    print(f"\n{len(findings)} high-severity finding(s); "
          f"SAST is {gate_class} at tier {tier}.")

    if gate_class == "advisory":
        print("Advisory at this tier: reported, not blocking. The trend data exists from "
              "day one, so raising the tier is not a leap into the unknown.")
        return 0

    if gate_class == "ratchet":
        previous = baseline(root)
        if previous is None:
            # Refusing is the point. Promoting to a tier where SAST ratchets, without ever
            # having measured it, would silently ratchet against nothing.
            print(f"could not run: tier {tier} ratchets SAST, but no {RATCHET_ID} baseline "
                  f"is recorded. Measure it before raising the tier.", file=sys.stderr)
            return 2
        if len(findings) > previous:
            print(f"\n{len(findings)} findings is worse than the baseline {previous}.")
            return 1
        return 0

    if findings:
        print("\nContract at this tier: this blocks and cannot be waived.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
