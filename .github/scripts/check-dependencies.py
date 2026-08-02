#!/usr/bin/env python3
"""Supply-chain controls: nothing third-party runs here unless it is allowlisted and pinned.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

Package hallucination is the highest-probability AI-specific risk in this system — around
19.7% of generated package references do not exist, and 43% of those invented names repeat
across identical prompts, which is repeatable enough for an attacker to pre-register one and
wait. The 90-day minimum age is the specific counter: the attacker has to sit on the name for
three months while every scanner watching for this is looking straight at it.

The direction that matters is finding dependencies the allowlist does *not* mention. An
allowlist checked only against itself is a list of things someone remembered to write down.
So the sources are read instead: Cargo manifests, workflow `uses:` steps, and every non-stdlib
import in the gate scripts.

Exit codes: 0 clean · 1 violations · 2 could not run.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative

SHA_PIN = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")

# Modules that ship with Python. An import outside this set and outside the local scripts is a
# third-party dependency, whether or not anyone declared it.
STDLIB = set(sys.stdlib_module_names) | {"__future__"}

violations: list[str] = []


def fail(where: str, message: str) -> None:
    violations.append(f"{where}: {message}")


def distance(a: str, b: str) -> int:
    """Levenshtein, iterative. Two names close together is the lookalike attack."""
    if a == b:
        return 0
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1,
                               previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def load_allowlist(root: Path) -> dict:
    path = root / "aios" / "dependencies.yml"
    if not path.is_file():
        raise CouldNotRun(f"no dependency allowlist at {relative(path)}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotRun(f"{relative(path)} is not parseable: {exc}")


def discover_actions(root: Path) -> dict[str, set[str]]:
    """Every `uses:` across the workflows, mapped to the references seen."""
    found: dict[str, set[str]] = {}
    directory = root / ".github" / "workflows"
    if not directory.is_dir():
        return found
    for path in sorted(directory.glob("*.yml")):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = USES.match(line)
            if not match:
                continue
            name, _, reference = match.group(1).partition("@")
            found.setdefault(name, set()).add(reference)
    return found


def discover_python_imports(root: Path) -> set[str]:
    """Third-party imports in the gate layer, ignoring stdlib and local modules.

    Parsed, not pattern-matched. A regex over the source read this file's own docstring —
    a sentence ending "every non-stdlib / import in the gate scripts" — and reported a
    dependency named `in`. The AST cannot mistake prose for code, and the class of bug goes
    with it rather than being narrowed.
    """
    found: set[str] = set()
    directories = [root / ".github" / "scripts", root / "tests", root / "aios" / "bin"]
    local = set()
    for directory in directories:
        if directory.is_dir():
            local |= {path.stem for path in directory.rglob("*.py")}

    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*.py")):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            except SyntaxError as exc:
                raise CouldNotRun(f"{relative(path)} does not parse: {exc}")
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module] if node.level == 0 and node.module else []
                else:
                    continue
                for name in names:
                    root_module = name.split(".")[0]
                    if root_module not in STDLIB and root_module not in local:
                        found.add(root_module)
    return found


def discover_cargo(root: Path) -> set[str]:
    path = root / "Cargo.toml"
    if not path.is_file():
        return set()
    found, in_dependencies = set(), False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("["):
            in_dependencies = "dependencies" in stripped
            continue
        if in_dependencies and "=" in stripped and not stripped.startswith("#"):
            found.add(stripped.split("=")[0].strip())
    return found


def check_declarations(entries: list[dict], policy: dict, today: dt.date) -> None:
    minimum = int(policy.get("min_age_days", 90))
    for entry in entries:
        name = entry.get("name", "<unnamed>")
        where = f"dependency [{name}]"
        if len(str(entry.get("reason", "")).strip()) < 30:
            fail(where, "has no reason worth reading. Writing why is most of what stops a "
                        "dependency being added casually.")
        if not entry.get("version"):
            fail(where, "declares no version, so nothing is pinned")
        released = entry.get("first_release")
        if not isinstance(released, dt.date):
            fail(where, f"first_release {released!r} is not a date, so its age is unknown")
            continue
        age = (today - released).days
        if age < minimum:
            fail(where, f"is {age} days old, under the {minimum}-day minimum. A name "
                        f"registered recently is the shape of a pre-registered hallucination.")


def check_typosquats(entries: list[dict], policy: dict) -> None:
    limit = int(policy.get("typosquat_distance", 2))
    names = [str(entry.get("name", "")) for entry in entries if entry.get("name")]
    for i, first in enumerate(names):
        for second in names[i + 1:]:
            # Compare the bare package name: org prefixes differ for unrelated reasons.
            a, b = first.split("/")[-1].lower(), second.split("/")[-1].lower()
            if a != b and distance(a, b) <= limit:
                fail("dependencies", f"{first!r} and {second!r} differ by "
                                     f"{distance(a, b)} characters. A lookalike sitting beside "
                                     f"the real one is where a reader's eye slides over it.")


def check_pinning(root: Path, declared: dict[str, dict]) -> None:
    for name, references in discover_actions(root).items():
        where = f"action [{name}]"
        if name not in declared:
            fail(where, "is used in a workflow but is not in the allowlist")
            continue
        for reference in sorted(references):
            if not SHA_PIN.match(reference):
                fail(where, f"is pinned to {reference!r}, which is a tag and not a commit. A "
                            f"tag is mutable, and an action runs arbitrary code in CI with a "
                            f"token.")
            elif reference != str(declared[name].get("version")):
                fail(where, f"runs {reference} but the allowlist says "
                            f"{declared[name].get('version')}")


def check_python_pinning(root: Path, declared: dict[str, dict]) -> None:
    requirements = root / ".github" / "scripts" / "requirements.txt"
    imports = discover_python_imports(root)
    # The import name and the distribution name differ often enough that mapping them by hand
    # is the honest option; guessing produces false clean results.
    known = {"yaml": "PyYAML"}
    for module in sorted(imports):
        distribution = known.get(module, module)
        if distribution not in declared:
            fail(f"import [{module}]",
                 "is a third-party import in the gate layer and is not in the allowlist")
    if not imports:
        return
    if not requirements.is_file():
        fail("requirements", f"{relative(requirements)} is missing, so nothing pins the "
                             f"gate layer's imports")
        return
    text = requirements.read_text(encoding="utf-8")
    if "--hash=sha256:" not in text:
        fail("requirements", "pins no hashes. Without --require-hashes an exact version still "
                             "trusts whatever the index serves for it.")
    for line in text.splitlines():
        if line.strip().startswith("#") or not line.strip():
            continue
        if re.match(r"^[A-Za-z]", line) and "==" not in line:
            fail("requirements", f"{line.strip()!r} is not pinned to an exact version")


def check_cargo(root: Path, declared: dict[str, dict]) -> None:
    for name in sorted(discover_cargo(root)):
        if name not in declared:
            fail(f"crate [{name}]", "is in Cargo.toml but is not in the allowlist")
    if discover_cargo(root) and not (root / "Cargo.lock").is_file():
        fail("cargo", "declares dependencies with no Cargo.lock committed, so an install is "
                      "not reproducible")


def check_planned(document: dict) -> None:
    for entry in document.get("planned") or []:
        where = f"planned control [{entry.get('id', '<no id>')}]"
        if not entry.get("pending"):
            fail(where, "names no task that builds it")
        if len(str(entry.get("reason", "")).strip()) < 30:
            fail(where, "gives no reason it is not built yet")


ECOSYSTEMS = {"pypi": "pip", "crates": "rust", "npm": "npm", "github-actions": "actions"}


def check_advisories(entries: list[dict], blocking: list[str]) -> None:
    """Known vulnerabilities, from GitHub's advisory database.

    GitHub rather than OSV for two reasons. It is the forge this repository already depends on
    (ADR-002), so it adds no new trusted party; and api.osv.dev is filtered on this network,
    with the same connection-reset signature as the Rust hosts, so it could not be verified
    even once. A source that cannot be tested from the machine that writes the check is not a
    source.

    Unauthenticated, so it is rate-limited. That is survivable precisely because this runs on
    a schedule rather than on every pull request.
    """
    for entry in entries:
        ecosystem = ECOSYSTEMS.get(str(entry.get("ecosystem")))
        name, version = entry.get("name"), entry.get("version")
        if not ecosystem or not name or not version:
            continue
        affects = urllib.parse.quote(f"{name}@{version}")
        url = (f"https://api.github.com/advisories?ecosystem={ecosystem}"
               f"&affects={affects}")
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.github+json", "User-Agent": "aios-supply-chain"})
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                advisories = json.load(response)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            print(f"  could not check advisories for {name}: {exc}", file=sys.stderr)
            continue

        hits = [a for a in advisories if str(a.get("severity", "")).lower() in blocking]
        for advisory in hits:
            fail(f"dependency [{name}]",
                 f"{version} is affected by {advisory.get('ghsa_id')} "
                 f"({advisory.get('severity')}): {advisory.get('summary')}")
        if not hits:
            print(f"  no {'/'.join(blocking)} advisories: {name} {version}")


def verify_online(entries: list[dict], today: dt.date, minimum: int) -> None:
    """Confirm each package exists and is old enough, against the registry itself.

    Kept out of the pull-request gate deliberately. A Contract gate that reaches the network
    fails on someone else's outage, and a gate that fails for reasons unrelated to the change
    is one people learn to re-run rather than read.
    """
    for entry in entries:
        if entry.get("ecosystem") != "pypi":
            continue
        name = entry["name"]
        # The whole project, not the pinned version. The age rule exists to make an attacker
        # sit on a pre-registered name for three months, and that is a property of the *name*.
        # Checking the version's upload date instead would forbid ever taking an update to a
        # package that has existed for fifteen years, which is not what the control is for.
        url = f"https://pypi.org/pypi/{name}/json"
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                fail(f"dependency [{name}]",
                     f"version {entry['version']} does not exist on PyPI. This is what a "
                     f"hallucinated package looks like.")
            else:
                print(f"  could not verify {name}: HTTP {exc.code}", file=sys.stderr)
            continue
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"  could not verify {name}: {exc}", file=sys.stderr)
            continue

        if entry["version"] not in (data.get("releases") or {}):
            fail(f"dependency [{name}]",
                 f"version {entry['version']} does not exist on PyPI. This is what a "
                 f"hallucinated package looks like.")
            continue
        uploads = [file["upload_time"][:10]
                   for files in (data.get("releases") or {}).values()
                   for file in files if file.get("upload_time")]
        if not uploads:
            continue
        released = dt.date.fromisoformat(min(uploads))
        age = (today - released).days
        if age < minimum:
            fail(f"dependency [{name}]", f"was published {age} days ago, under the "
                                         f"{minimum}-day minimum")
        elif released != entry.get("first_release"):
            fail(f"dependency [{name}]", f"records first_release {entry.get('first_release')} "
                                         f"but the registry says {released}")
        else:
            print(f"  verified: {name} {entry['version']}, {age} days old")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--online", action="store_true",
                        help="also verify existence and age against the registry")
    parser.add_argument("--today", help="override today's date, for tests")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        document = load_allowlist(root)
        today = dt.date.fromisoformat(args.today) if args.today else dt.date.today()
    except (CouldNotRun, ValueError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    entries = document.get("dependencies") or []
    policy = document.get("policy") or {}
    declared = {str(entry.get("name")): entry for entry in entries}

    check_declarations(entries, policy, today)
    check_typosquats(entries, policy)
    check_pinning(root, declared)
    check_python_pinning(root, declared)
    check_cargo(root, declared)
    check_planned(document)

    if args.online:
        verify_online(entries, today, int(policy.get("min_age_days", 90)))
        check_advisories(entries, [str(s).lower()
                                   for s in policy.get("block_severities") or []])

    if violations:
        for violation in violations:
            print(f"  violation: {violation}")
        print(f"\n{len(violations)} supply-chain violation(s).")
        return 1

    print(f"supply chain is clean: {len(entries)} dependency(s) allowlisted and pinned.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
