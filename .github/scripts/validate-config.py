#!/usr/bin/env python3
"""Validate aios/config.yml against aios/config.schema.yml.

PROVISIONAL. ADR-006 requires gate logic to ship as subcommands of the aios binary. That
binary does not exist yet, so this runs as a script from a protected path and moves into
`aios check` when there is something to move it into.

Beyond shape, this enforces the property the schema exists for: every key documents what it
does, and either names the check that reads it or the task that will make one. An
`enforced_by` naming a workflow step is verified against the workflow, so a key cannot claim
an enforcement that is not there.

Exit codes: 0 valid, 1 invalid, 2 could not run. The third is distinguished because an
unrunnable check that reports success is worse than no check.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    print("could not run: PyYAML is not available", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[2]

# Overridable so the gate can be exercised against deliberately broken fixtures. A check
# that has only ever been run against a passing input is not known to fail.
def _arg(flag: str, default: Path) -> Path:
    return Path(sys.argv[sys.argv.index(flag) + 1]) if flag in sys.argv else default


CONFIG = _arg("--config", ROOT / "aios" / "config.yml")
SCHEMA = _arg("--schema", ROOT / "aios" / "config.schema.yml")
WORKFLOWS = _arg("--workflows", ROOT / ".github" / "workflows")

TASK_ID = re.compile(r"^(P0|M[0-6]|S)-\d+$")
# Any workflow, not just hygiene.yml. Gates that need a pull request diff live in their own
# workflows, and a key those read is no less enforced for it.
STEP_REF = re.compile(r'^([A-Za-z0-9._-]+\.ya?ml) step "(.+)"$')

errors: list[str] = []


def fail(msg: str) -> None:
    errors.append(msg)


def load(path: Path) -> dict:
    if not path.exists():
        print(f"could not run: {path} does not exist", file=sys.stderr)
        raise SystemExit(2)
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        print(f"could not run: {path} is not valid YAML: {exc}", file=sys.stderr)
        raise SystemExit(2)


def flatten(node, opaque: set[str], prefix: str = "") -> dict[str, object]:
    """Leaf keys as dotted paths. A list is a leaf; a mapping is not.

    `opaque` names the mappings whose keys are data rather than schema — the deny-list prefix
    map is keyed by the regexes themselves. Descending into one would demand a schema entry
    per regex, which is not a schema, it is the same list written twice.
    """
    out: dict[str, object] = {}
    for key, value in node.items():
        path = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(value, dict) and path not in opaque:
            out.update(flatten(value, opaque, path))
        else:
            out[path] = value
    return out


def check_value(name: str, value, rule: dict) -> None:
    declared = rule.get("type")

    if declared == "integer":
        # bool is a subclass of int; a flag where a number belongs is a real mistake.
        if not isinstance(value, int) or isinstance(value, bool):
            fail(f"{name}: expected an integer, got {type(value).__name__}")
            return
        low = rule.get("min")
        if low is not None and value < low:
            fail(f"{name}: {value} is below the minimum of {low}")

    elif declared == "boolean":
        # Strictly, not by truthiness. YAML reads `yes`, `on` and `1` as things that look true
        # at a glance, and a switch whose configured value is the *string* "on" is exactly the
        # silently-inert control this file exists to refuse.
        if not isinstance(value, bool):
            fail(f"{name}: expected true or false, got {type(value).__name__}")

    elif declared == "string":
        if not isinstance(value, str):
            fail(f"{name}: expected a string, got {type(value).__name__}")
            return
        allowed = rule.get("enum")
        if allowed and value not in allowed:
            fail(f"{name}: {value!r} is not one of {allowed}")
        pattern = rule.get("pattern")
        if pattern and not re.match(pattern, value):
            fail(f"{name}: {value!r} does not match {pattern}")

    elif declared == "list":
        if not isinstance(value, list):
            fail(f"{name}: expected a list, got {type(value).__name__}")
            return
        if rule.get("item_type") == "string":
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    fail(f"{name}[{i}]: expected a string, got {type(item).__name__}")

    elif declared == "map":
        # A mapping whose keys are data. The schema cannot name them, so it constrains the
        # shape of every entry instead and the meaning of the keys is checked by whoever reads
        # them — for the deny-list prefix map, by the generator, which refuses a key that is
        # not also a deny_commands pattern.
        if not isinstance(value, dict):
            fail(f"{name}: expected a mapping, got {type(value).__name__}")
            return
        wanted = rule.get("item_type")
        for key, item in value.items():
            if wanted == "list" and not isinstance(item, list):
                fail(f"{name}[{key!r}]: expected a list, got {type(item).__name__}")
            elif wanted == "string" and not isinstance(item, str):
                fail(f"{name}[{key!r}]: expected a string, got {type(item).__name__}")

    else:
        fail(f"{name}: schema declares unknown type {declared!r}")


def main() -> int:
    schema = load(SCHEMA).get("keys") or {}
    # Read the opaque set from the schema itself rather than listing it here, so that
    # declaring a key as a data-keyed map is one edit in one file.
    opaque = {name for name, rule in schema.items()
              if isinstance(rule, dict) and rule.get("type") == "map"}
    config = flatten(load(CONFIG), opaque)

    if not schema:
        print("could not run: schema declares no keys", file=sys.stderr)
        return 2

    steps_by_workflow: dict[str, set[str]] = {}
    if WORKFLOWS.is_dir():
        for path in sorted(WORKFLOWS.glob("*.y*ml")):
            found = re.findall(r"^\s*-\s*name:\s*(.+?)\s*$",
                               path.read_text(encoding="utf-8"), re.M)
            steps_by_workflow[path.name] = {s.strip('"\'') for s in found}

    for name in sorted(set(config) - set(schema)):
        fail(f"{name}: set in config.yml but not declared in the schema")
    for name in sorted(set(schema) - set(config)):
        fail(f"{name}: declared in the schema but absent from config.yml")

    for name, rule in sorted(schema.items()):
        if not isinstance(rule, dict):
            fail(f"{name}: schema entry is not a mapping")
            continue

        if not str(rule.get("effect") or "").strip():
            fail(f"{name}: no documented effect")

        enforced, pending = rule.get("enforced_by"), rule.get("pending")
        if bool(enforced) == bool(pending):
            fail(f"{name}: declare exactly one of enforced_by or pending")
        elif pending:
            if not TASK_ID.match(str(pending)):
                fail(f"{name}: pending {pending!r} is not a task ID, so it points at nothing")
        else:
            ref = STEP_REF.match(str(enforced))
            if not ref:
                fail(f"{name}: enforced_by {enforced!r} is not of the form "
                     f'\'<workflow>.yml step "<step name>"\', so it cannot be checked')
            elif steps_by_workflow:
                workflow, step = ref.group(1), ref.group(2)
                if workflow not in steps_by_workflow:
                    fail(f"{name}: enforced_by names {workflow}, which does not exist")
                elif step not in steps_by_workflow[workflow]:
                    fail(f"{name}: enforced_by names step {step!r}, "
                         f"which is not in {workflow}")

        if name in config:
            check_value(name, config[name], rule)

    if errors:
        print(f"aios/config.yml is invalid ({len(errors)} problem(s)):")
        for err in errors:
            print(f"  {err}")
        return 1

    enforced_now = sum(1 for r in schema.values() if isinstance(r, dict) and r.get("enforced_by"))
    print(f"aios/config.yml is valid: {len(schema)} keys, {enforced_now} enforced today, "
          f"{len(schema) - enforced_now} pending a named task.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
