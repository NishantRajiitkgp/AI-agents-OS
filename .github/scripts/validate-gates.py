#!/usr/bin/env python3
"""Validate the gate registry: every check declares a class, and the class is not a lie.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

Two directions, and the second is the load-bearing one:

  1. Every registered gate declares a class from the closed vocabulary.
  2. Every check that runs is registered.

Without (2), omission is the way to avoid declaring a class, and the register describes only
the checks that volunteered. That is the same hole `validate-tasks.py` had when it globbed
`T-*.md` and silently ignored anything misnamed.

It also checks the declaration against the workflow. A gate declaring `advisory` while its
step fails the job is not advisory, and a class nothing enforces is decoration. The registry
is only worth having if disagreeing with reality is an error.

Exit codes: 0 valid · 1 violations · 2 could not run.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative

CLASSES = ("contract", "ratchet", "advisory", "report")
BLOCKING = ("step", "continue", "script")
BLOCKS = ("contract", "ratchet")
REQUIRED = ("id", "title", "class", "blocking", "workflow", "step")
TIERS = ("prototype", "internal", "production", "regulated")
NOT_RUN = "none"

violations: list[str] = []


def fail(where: str, message: str) -> None:
    violations.append(f"{where}: {message}")


def check_class_field(where: str, declared) -> dict[str, str] | None:
    """Normalise `class` to a tier→class mapping, rejecting anything partial.

    A scalar means the same class at every tier. A mapping must name all four: a partial one
    resolves to nothing at the tiers it omits, and a gate that silently does not apply at a
    tier is exactly what this register exists to prevent.
    """
    if isinstance(declared, str):
        if declared not in CLASSES and declared != NOT_RUN:
            fail(where, f"class {declared!r} is not one of {', '.join(CLASSES)}")
            return None
        return {tier: declared for tier in TIERS}

    if not isinstance(declared, dict):
        fail(where, "class must be one class or a mapping from tier to class")
        return None

    unknown = [tier for tier in declared if tier not in TIERS]
    if unknown:
        fail(where, f"class names unknown tier(s): {', '.join(sorted(unknown))}")
        return None

    missing = [tier for tier in TIERS if tier not in declared]
    if missing:
        fail(where, f"class does not say what it is at {', '.join(missing)}. A partial "
                    f"mapping leaves the gate undefined at those tiers.")
        return None

    for tier, value in declared.items():
        if value not in CLASSES and value != NOT_RUN:
            fail(where, f"class at {tier} is {value!r}, not one of "
                        f"{', '.join(CLASSES)} or {NOT_RUN}")
            return None
    return dict(declared)


def resolve_tier(root: Path) -> str:
    """The one key the whole table is driven by."""
    path = root / "aios" / "config.yml"
    if not path.is_file():
        raise CouldNotRun(f"no configuration at {relative(path)}, so no tier to resolve")
    try:
        config = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotRun(f"{relative(path)} is not parseable: {exc}")
    tier = config.get("tier")
    if tier not in TIERS:
        raise CouldNotRun(f"tier is {tier!r}, which is not one of {', '.join(TIERS)}")
    return str(tier)


def load_registry(root: Path) -> dict:
    path = root / "aios" / "gates.yml"
    if not path.is_file():
        raise CouldNotRun(f"no gate registry at {relative(path)}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotRun(f"{relative(path)} is not parseable: {exc}")


def load_workflow_steps(root: Path) -> dict[str, dict[str, dict]]:
    """Index every step of every workflow by (workflow file, step name)."""
    workflows: dict[str, dict[str, dict]] = {}
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        raise CouldNotRun(f"no workflows at {relative(directory)}")

    for path in sorted(directory.glob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CouldNotRun(f"{relative(path)} is not parseable: {exc}")

        steps: dict[str, dict] = {}
        for job in (document.get("jobs") or {}).values():
            for index, step in enumerate(job.get("steps") or []):
                if not isinstance(step, dict):
                    continue
                name = step.get("name")
                if name is None:
                    if "run" in step:
                        fail(path.name,
                             f"step {index + 1} runs a command with no name, so it cannot be "
                             f"registered and cannot declare a class")
                    continue
                steps[str(name)] = {
                    "runs": "run" in step,
                    "continue_on_error": bool(step.get("continue-on-error", False)),
                }
        workflows[path.name] = steps
    return workflows


def check_entries(registry: dict, workflows: dict[str, dict[str, dict]],
                  tier: str) -> set[tuple[str, str]]:
    """Validate each gate and return the (workflow, step) pairs it accounts for."""
    claimed: set[tuple[str, str]] = set()
    seen_ids: set[str] = set()

    for entry in registry.get("gates") or []:
        gate_id = entry.get("id", "<no id>")
        where = f"gates.yml [{gate_id}]"

        missing = [field for field in REQUIRED if not entry.get(field)]
        if missing:
            fail(where, f"missing required field(s): {', '.join(missing)}")
            continue

        if gate_id in seen_ids:
            fail(where, "duplicate gate id")
        seen_ids.add(gate_id)

        by_tier = check_class_field(where, entry["class"])
        blocking = entry["blocking"]
        if by_tier is None:
            continue
        if blocking not in BLOCKING:
            fail(where, f"blocking {blocking!r} is not one of {', '.join(BLOCKING)}")
            continue

        # A static step cannot express a class that moves with the tier. Allowing it would
        # make raising the tier a change to this register and to nothing else, when 06 §3's
        # claim is that raising a tier is a one-line config change and not a migration.
        varies = len(set(by_tier.values())) > 1
        if varies and blocking != "script":
            moves = ", ".join(f"{tier}={by_tier[tier]}" for tier in TIERS)
            fail(where, f"class varies by tier ({moves}) but blocking is {blocking!r}. A "
                        f"workflow step is static, so its class cannot follow the tier. Only "
                        f"'script' can.")

        gate_class = by_tier[tier]
        if gate_class == NOT_RUN and blocking == "step":
            fail(where, f"does not run at {tier} but its step fails the job, so it does")
        # The class must match how blocking is actually produced, at the active tier.
        if gate_class not in BLOCKS and gate_class != NOT_RUN and blocking == "step":
            fail(where, f"is {gate_class} at {tier} but its step fails the job, so it blocks")
        if gate_class in BLOCKS and blocking == "continue":
            fail(where, f"is {gate_class} at {tier} but carries continue-on-error, so it "
                        f"cannot block")
        if blocking == "script" and not entry.get("note"):
            fail(where, "blocking is 'script', which the workflow cannot verify, so it needs "
                        "a note saying what decides the class")

        for scope in (entry.get("threshold") or {}):
            if scope not in TIERS:
                fail(where, f"threshold names unknown tier {scope!r}")

        workflow, step = entry["workflow"], entry["step"]
        if workflow not in workflows:
            fail(where, f"names workflow {workflow}, which does not exist")
            continue
        if step not in workflows[workflow]:
            fail(where, f"names step {step!r} in {workflow}, which has no such step")
            continue

        claimed.add((workflow, step))

        # And against the workflow itself, so the registry cannot drift from what CI does.
        actual = workflows[workflow][step]["continue_on_error"]
        if blocking == "continue" and not actual:
            fail(where, f"declares blocking 'continue' but {step!r} has no continue-on-error")
        if blocking == "step" and actual:
            fail(where, f"declares blocking 'step' but {step!r} carries continue-on-error")

    for entry in registry.get("planned") or []:
        gate_id = entry.get("id", "<no id>")
        where = f"gates.yml [planned: {gate_id}]"
        if gate_id in seen_ids:
            fail(where, "duplicate gate id")
        seen_ids.add(gate_id)
        if "class" not in entry:
            fail(where, "missing required field(s): class")
        else:
            check_class_field(where, entry["class"])
        if not entry.get("pending"):
            fail(where, "is planned but names no task that implements it")

    for entry in registry.get("not_a_gate") or []:
        workflow, step = entry.get("workflow"), entry.get("step")
        where = f"gates.yml [not_a_gate: {step}]"
        if not entry.get("reason"):
            fail(where, "claims a step is not a check but gives no reason")
        if workflow not in workflows:
            fail(where, f"names workflow {workflow}, which does not exist")
        elif step not in workflows[workflow]:
            fail(where, f"names step {step!r} in {workflow}, which has no such step")
        else:
            claimed.add((workflow, step))

    return claimed


def check_coverage(workflows: dict[str, dict[str, dict]],
                   claimed: set[tuple[str, str]]) -> None:
    """Every step that runs a command must be registered or explicitly exempted."""
    for workflow, steps in workflows.items():
        for name, step in steps.items():
            if not step["runs"]:
                continue  # a `uses:` step is an action, not a check
            if (workflow, name) not in claimed:
                fail(f"{workflow} [{name}]",
                     "runs a command but is not in the gate registry, so it declares no "
                     "class. Register it, or list it under not_a_gate with a reason.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path,
                        help="repository root; discovered from the config when omitted")
    parser.add_argument("--tier", choices=TIERS,
                        help="resolve against this tier instead of the configured one")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        tier = args.tier or resolve_tier(root)
        registry = load_registry(root)
        workflows = load_workflow_steps(root)
        claimed = check_entries(registry, workflows, tier)
        check_coverage(workflows, claimed)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    if violations:
        for violation in violations:
            print(f"  violation: {violation}")
        print(f"\n{len(violations)} gate registry violation(s) at tier {tier}.")
        return 1

    tally: dict[str, int] = {}
    for entry in (registry.get("gates") or []) + (registry.get("planned") or []):
        resolved = check_class_field("", entry.get("class"))
        if resolved:
            tally[resolved[tier]] = tally.get(resolved[tier], 0) + 1
    summary = ", ".join(f"{count} {name}"
                         for name, count in sorted(tally.items(), key=lambda item: -item[1]))
    gates = len(registry.get("gates") or [])
    planned = len(registry.get("planned") or [])
    print(f"gate registry is valid at tier {tier}: {gates} gates declared, {planned} planned.")
    print(f"  resolved classes: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
