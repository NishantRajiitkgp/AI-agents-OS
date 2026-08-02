#!/usr/bin/env python3
"""Measure the feedback-speed budgets, and decide what exceeding one costs.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

06 §6 sets three ceilings — pre-commit under 5s, `aios check` under 60s, the pull-request run
under 10min — on the grounds that fast feedback is one of the capabilities that flips AI's
effect on stability from negative to positive. That makes latency a requirement, not an
optimisation, and a requirement nobody measures is a preference.

Class by tier, like SAST, and for the same reason: at prototype the honest thing is to measure
and watch, because a repository that has never been timed has no idea what it costs. Blocking
on a number nobody has seen yet would mean the first red build is the first measurement.

  prototype   report    measure, print, never block
  internal    advisory  the same, said louder
  production  ratchet   block if worse than the recorded baseline, beyond its tolerance
  regulated   contract  block on any breach of the absolute budget

The tolerance in the ratchet tier is not slack for its own sake. Wall-clock time on a shared
runner varies by tens of percent between identical runs, and a ratchet that fails on that is a
gate people learn to re-run rather than read — which is exactly how a gate becomes noise while
still looking green.

Exit codes: 0 acceptable at this tier · 1 blocked · 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative

TIERS = ("prototype", "internal", "production", "regulated")
CLASS_BY_TIER = {"prototype": "report", "internal": "advisory",
                 "production": "ratchet", "regulated": "contract"}
ACCEPTABLE, BLOCKED, CANNOT_RUN = 0, 1, 2

GATE_SCRIPTS = ("validate-config", "validate-requirements", "validate-tasks",
                "validate-references", "validate-gates", "check-ratchets",
                "check-dependencies", "check-overrides", "check-demotions")


def paths(root: Path) -> dict[str, dict]:
    """The three paths 06 §6 names, and what each actually runs.

    `check` runs the gates and the suite — the same commands CI runs, because D-040 makes the
    equivalence a hard requirement. Timing a curated subset would produce a number that is
    fast and means nothing.
    """
    scripts = root / ".github" / "scripts"
    return {
        "pre_commit": {
            "budget": "pre_commit_seconds",
            "what": "secrets scan over the working tree",
            "commands": [[sys.executable, str(scripts / "scan-secrets.py")]],
        },
        "check": {
            "budget": "check_seconds",
            "what": "every gate script, then the whole test suite",
            "commands": ([[sys.executable, str(scripts / f"{name}.py")]
                          for name in GATE_SCRIPTS]
                         + [[sys.executable, str(scripts / "run-tests.py")]]),
        },
        "ci_pr": {
            "budget": "ci_pr_seconds",
            "what": "the whole pull-request run, reported by the workflow",
            "commands": None,  # supplied with --ci-seconds; nothing here can time a CI job
        },
    }


def measure(commands: list[list[str]], root: Path) -> float:
    began = time.perf_counter()
    for command in commands:
        subprocess.run(command, cwd=root, capture_output=True)
    return time.perf_counter() - began


def baselines(root: Path) -> dict[str, dict]:
    path = root / "aios" / "ratchets.yml"
    if not path.is_file():
        return {}
    document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {str(entry.get("id")): entry for entry in document.get("ratchets") or []}


def resolve_tier(root: Path, override: str | None) -> str:
    if override:
        return override
    tier = (yaml.safe_load((root / "aios" / "config.yml").read_text(encoding="utf-8"))
            or {}).get("tier")
    if tier not in TIERS:
        raise CouldNotRun(f"tier is {tier!r}, which is not one of {', '.join(TIERS)}")
    return str(tier)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--tier", choices=TIERS, help="override the configured tier")
    parser.add_argument("--only", action="append", default=[],
                        help="measure only these paths")
    parser.add_argument("--ci-seconds", type=float,
                        help="duration of the pull-request run, from the workflow")
    parser.add_argument("--out", type=Path, help="write measurements as JSON")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        tier = resolve_tier(root, args.tier)
        config = yaml.safe_load(
            (root / "aios" / "config.yml").read_text(encoding="utf-8")) or {}
        budgets = config.get("budgets") or {}
        defined = paths(root)
        recorded = baselines(root)
    except (CouldNotRun, OSError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    wanted = args.only or list(defined)
    unknown = [name for name in wanted if name not in defined]
    if unknown:
        print(f"could not run: no such path(s): {', '.join(unknown)}", file=sys.stderr)
        return CANNOT_RUN

    gate_class = CLASS_BY_TIER[tier]
    measurements: dict[str, dict] = {}
    over_budget: list[str] = []
    regressed: list[str] = []

    for name in wanted:
        detail = defined[name]
        budget = budgets.get(detail["budget"])
        if budget is None:
            print(f"could not run: budgets.{detail['budget']} is not configured",
                  file=sys.stderr)
            return CANNOT_RUN

        if name == "ci_pr":
            if args.ci_seconds is None:
                print(f"  {name}: not measured — nothing outside Actions can time a CI job. "
                      f"The workflow supplies it with --ci-seconds.")
                continue
            seconds = float(args.ci_seconds)
        else:
            seconds = measure(detail["commands"], root)

        measurements[name] = {"seconds": round(seconds, 1), "budget": budget,
                              "what": detail["what"]}
        verdict = "within" if seconds <= budget else "OVER"
        print(f"  {name}: {seconds:.1f}s against a {budget}s budget — {verdict} "
              f"({detail['what']})")
        if seconds > budget:
            over_budget.append(name)

        entry = recorded.get(f"{name}_seconds")
        if entry and entry.get("baseline") is not None:
            allowance = float(entry["baseline"]) * (
                1 + float(entry.get("tolerance_percent", 0)) / 100)
            if seconds > allowance:
                regressed.append(
                    f"{name}: {seconds:.1f}s is worse than the baseline "
                    f"{entry['baseline']}s plus its "
                    f"{entry.get('tolerance_percent', 0)}% tolerance")

    if args.out:
        args.out.write_text(json.dumps(measurements, indent=2), encoding="utf-8")
        print(f"\nwrote {relative(args.out)}")

    print(f"\nFeedback speed is {gate_class} at tier {tier}.")

    if gate_class in ("report", "advisory"):
        if over_budget:
            print(f"Over budget: {', '.join(over_budget)}. Reported, not blocking — a "
                  f"repository that has never been timed has no idea what it costs, and the "
                  f"first red build should not also be the first measurement.")
        return ACCEPTABLE

    if gate_class == "ratchet":
        for line in regressed:
            print(f"  violation: {line}")
        if regressed:
            return BLOCKED
        if not any(f"{name}_seconds" in recorded for name in measurements):
            print("could not run: this tier ratchets feedback speed, but no baseline is "
                  "recorded. Measure it in CI before raising the tier.", file=sys.stderr)
            return CANNOT_RUN
        return ACCEPTABLE

    if over_budget:
        print(f"  violation: over budget at a contract tier: {', '.join(over_budget)}")
        return BLOCKED
    return ACCEPTABLE


if __name__ == "__main__":
    raise SystemExit(main())
