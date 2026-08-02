#!/usr/bin/env python3
"""Run the registered gates and record what each returned, for the review packet.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

The packet needs a result per gate, and there are three ways to get one. Asking GitHub for
check runs does not work: a check run is a *job*, and a gate is a *step*, so the results come
back at the wrong granularity. Keeping a list of commands in the workflow works until the list
and the registry drift, which they do, and then the packet reports on a set of gates that is
quietly not the set that runs.

So the commands are read from the registry: each gate names its workflow and step, and the
step's `run:` block is the command. There is exactly one definition of what a gate runs, and
it is the one CI executes — D-040 applied to the reporting layer.

Steps that are `uses:` rather than `run:` cannot be executed here and are reported as such,
not as passes. So are steps whose command still holds an unsubstituted expression. A gate that
did not run must never be indistinguishable from a gate that passed.

Exit codes: 0 always, unless the registry cannot be read. This runs gates, it does not judge
them — the workflows that own them already do that, and a second opinion that can block is a
second implementation of every gate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative

EXPRESSION = re.compile(r"\$\{\{([^}]+)\}\}")
CANNOT_RUN = 2


def substitute(command: str) -> str:
    """Fill in the few GitHub expressions whose values exist outside Actions."""
    known = {
        "github.base_ref": os.environ.get("GITHUB_BASE_REF", ""),
        "github.head_ref": os.environ.get("GITHUB_HEAD_REF", ""),
        "github.workspace": os.environ.get("GITHUB_WORKSPACE", str(Path.cwd())),
    }

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        return known.get(key) or match.group(0)

    return EXPRESSION.sub(replace, command)


def commands(root: Path, skip_workflows: set[str] | None = None) -> dict[str, dict]:
    """Each gate's command, taken from the workflow step the registry points at."""
    registry = yaml.safe_load((root / "aios" / "gates.yml").read_text(encoding="utf-8")) or {}
    steps: dict[tuple[str, str], dict] = {}
    directory = root / ".github" / "workflows"
    for path in sorted(directory.glob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise CouldNotRun(f"{relative(path)} is not valid YAML: {exc}")
        for job in (document.get("jobs") or {}).values():
            for step in job.get("steps") or []:
                if step.get("name"):
                    steps[(path.name, str(step["name"]))] = step

    found: dict[str, dict] = {}
    for entry in registry.get("gates") or []:
        key = (str(entry.get("workflow")), str(entry.get("step")))
        step = steps.get(key)
        gate_id = str(entry.get("id"))
        if key[0] in (skip_workflows or set()):
            # Named by workflow rather than by gate, so the exclusion cannot drift as gates
            # are added to it. Attempting a build without a toolchain would report `failure`,
            # and a packet saying the build failed when nothing tried to build it is worse
            # than one saying nothing.
            found[gate_id] = {"skip": f"{key[0]} is not run by the packet job"}
        elif step is None:
            found[gate_id] = {"skip": "the registry points at a step that does not exist"}
        elif "run" not in step:
            found[gate_id] = {"skip": "the step is an action, not a command"}
        else:
            command = substitute(str(step["run"]).strip())
            if EXPRESSION.search(command):
                found[gate_id] = {"skip": "the command holds an expression only Actions can "
                                          "resolve"}
            else:
                found[gate_id] = {"command": command}
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--out", type=Path, help="write results JSON here")
    parser.add_argument("--list", action="store_true",
                        help="show what would run, without running it")
    parser.add_argument("--skip-workflow", action="append", default=[],
                        help="do not run gates owned by this workflow file")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        plan = commands(root, set(args.skip_workflow))
    except (CouldNotRun, OSError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    if args.list:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0

    results: dict[str, str] = {}
    for gate_id, detail in sorted(plan.items()):
        if "skip" in detail:
            results[gate_id] = "skipped"
            print(f"  skipped {gate_id}: {detail['skip']}")
            continue
        outcome = subprocess.run(detail["command"], shell=True, cwd=root,
                                 capture_output=True, text=True)
        results[gate_id] = "success" if outcome.returncode == 0 else "failure"
        print(f"  {results[gate_id]:<8} {gate_id}")

    payload = json.dumps(results, indent=2, sort_keys=True)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"\nwrote {relative(args.out)}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
