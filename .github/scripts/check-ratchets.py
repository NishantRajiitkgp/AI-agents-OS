#!/usr/bin/env python3
"""Measure the ratchet metrics and refuse any that got worse.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

A ratchet permits the current value of a metric and forbids it worsening. That is what makes
it the class that solves the threshold problem: it is always satisfiable, it never blocks a
good change, and it improves monotonically. No number has to be argued for, because the
number is whatever the repository already is.

Two properties do the work, and both are about the baseline rather than the metric:

  1. **Metrics are measured here, in code.** A ratchet definition cannot supply a shell
     command to run. If it could, lowering a bar would be a one-line edit to a data file that
     reads like configuration, and the measurement would be the thing under the agent's
     control rather than the thing measuring it.
  2. **A baseline may only move in the improving direction.** Loosening one is the whole
     evasion, and it is the only edit to this file that a regression needs. So it is checked
     against the previous committed value, not merely reviewed — `aios/ratchets.yml` is a
     protected path as well, but a control that depends only on someone noticing a number got
     bigger is not a control.

Exit codes: 0 all held · 1 a metric regressed or a baseline was loosened · 2 could not run.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, relative


def load_sibling(name: str):
    """Import a hyphenated sibling script as a module.

    The gate scripts are named as commands rather than as modules, so the one that owns a
    definition cannot simply be imported. Loading it is still better than restating it: a
    restated definition is a second implementation, and two of those can disagree.
    """
    path = Path(__file__).resolve().parent / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_")[:-3], path)
    if spec is None or spec.loader is None:
        raise CouldNotRun(f"could not load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


always_on = load_sibling("check-always-on.py")

LOWER, HIGHER = "lower_is_better", "higher_is_better"
DIRECTIONS = (LOWER, HIGHER)

# These two files describe the patterns they count, so counting them would make every metric
# a measurement of its own source. The same exclusion the test-integrity audit needs for its
# fixtures, and the same blind spot: a suppression genuinely added here is not counted.
SELF = ("check-ratchets.py", "test_ratchets.py")

# Markers and suppressions are counted in code only, not in prose. Writing the words TODO and
# FIXME into a document that explains the TODO ratchet raised it by eight, which is a metric
# measuring its own documentation. A marker in code is debt; the same word in a design note is
# a sentence, and a count that cannot tell them apart teaches people to avoid the vocabulary
# rather than the debt.
CODE_SUFFIXES = (".py", ".rs", ".sh", ".ps1")

MARKERS = re.compile(r"\b(TODO|FIXME|XXX|HACK)\b")
SUPPRESSIONS = re.compile(
    r"(noqa|type:\s*ignore|pylint:\s*disable|pyright:\s*ignore|eslint-disable"
    r"|nosec|allow\(dead_code\)|#\[allow\(|@SuppressWarnings|istanbul ignore)")


def tracked_code_files(root: Path) -> list[Path]:
    try:
        listing = subprocess.run(["git", "ls-files"], cwd=root,
                                 capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise CouldNotRun(f"could not list tracked files: {exc}")
    files = []
    for line in listing.splitlines():
        path = root / line
        if path.suffix in CODE_SUFFIXES and path.name not in SELF and path.is_file():
            files.append(path)
    return files


def count_matching(root: Path, pattern: re.Pattern[str]) -> int:
    total = 0
    for path in tracked_code_files(root):
        try:
            total += len(pattern.findall(path.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return total


def line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return len(path.read_text(encoding="utf-8").splitlines())


def measure_always_on_lines(root: Path) -> int:
    """Everything loaded on every turn (ADR-010).

    Delegated rather than reimplemented. This function used to count AGENTS.md and the
    alwaysApply rules and stop, which agreed with the budget gate exactly as long as no skill
    or subagent existed — and would have reported "held" the moment one did.
    """
    return always_on.measure(root)


def measure_agents_md_lines(root: Path) -> int:
    return line_count(root / "AGENTS.md")


def measure_root_markdown_files(root: Path) -> int:
    return len(list(root.glob("*.md")))


def measure_todo_markers(root: Path) -> int:
    return count_matching(root, MARKERS)


def measure_suppressions(root: Path) -> int:
    """The cheapest defence against an agent silencing a check rather than satisfying it."""
    return count_matching(root, SUPPRESSIONS)


def measure_gates_registered(root: Path) -> int:
    """Deleting a check is the quietest way to stop it failing. This makes it loud."""
    path = root / "aios" / "gates.yml"
    if not path.is_file():
        return 0
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotRun(f"{relative(path)} is not parseable: {exc}")
    return len(document.get("gates") or [])


def measure_tests_declared(root: Path) -> int:
    """Counted from source, not from a run, so it cannot be moved by skipping.

    Deliberately not excluding this project's own test files the way the marker counts do:
    the number that matters is every test that exists, and a blind spot in a count whose whole
    job is to notice tests disappearing would be self-defeating.
    """
    directory = root / "tests"
    if not directory.is_dir():
        return 0
    total = 0
    for path in sorted(directory.rglob("*.py")):
        total += len(re.findall(r"(?m)^\s*def test_", path.read_text(encoding="utf-8")))
    return total


MEASURES = {
    "always_on_lines": measure_always_on_lines,
    "agents_md_lines": measure_agents_md_lines,
    "root_markdown_files": measure_root_markdown_files,
    "todo_markers": measure_todo_markers,
    "suppressions": measure_suppressions,
    "gates_registered": measure_gates_registered,
    "tests_declared": measure_tests_declared,
}


def load_ratchets(root: Path) -> dict:
    path = root / "aios" / "ratchets.yml"
    if not path.is_file():
        raise CouldNotRun(f"no ratchet definitions at {relative(path)}")
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotRun(f"{relative(path)} is not parseable: {exc}")


def committed_baselines(root: Path) -> dict[str, float] | None:
    """The baselines as of HEAD, or None when there is no committed version to compare to."""
    try:
        blob = subprocess.run(["git", "show", "HEAD:aios/ratchets.yml"], cwd=root,
                              capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise CouldNotRun(f"git is not available: {exc}")
    if blob.returncode != 0:
        return None
    try:
        document = yaml.safe_load(blob.stdout) or {}
    except yaml.YAMLError:
        return None
    return {entry["id"]: entry["baseline"]
            for entry in document.get("ratchets") or []
            if "id" in entry and "baseline" in entry}


def worse(direction: str, value: float, than: float) -> bool:
    return value > than if direction == LOWER else value < than


def check_unwired(document: dict, failures: list[str]) -> None:
    """A metric the design names but that is not wired must say which it is, and why.

    Otherwise the difference between "cannot be measured yet" and "nobody got round to it" is
    invisible, and the second is what a missing ratchet usually is.
    """
    for entry in document.get("planned") or []:
        metric = entry.get("id", "<no id>")
        where = f"planned ratchet [{metric}]"
        if not entry.get("pending"):
            failures.append(f"{where}: names no task that wires it")
        if len(str(entry.get("reason", "")).strip()) < 20:
            failures.append(f"{where}: gives no reason it is not wired yet")
        if entry.get("direction") not in DIRECTIONS:
            failures.append(f"{where}: direction {entry.get('direction')!r} is not one of "
                            f"{', '.join(DIRECTIONS)}")
        # The rule that stops `planned` being where a ratchet goes to avoid enforcement.
        if metric in MEASURES:
            failures.append(f"{where}: is measurable today, so it is not planned. Wire it or "
                            f"delete the measurement.")

    for entry in document.get("not_applicable") or []:
        metric = entry.get("id", "<no id>")
        where = f"not-applicable ratchet [{metric}]"
        if len(str(entry.get("reason", "")).strip()) < 20:
            failures.append(f"{where}: gives no reason it does not apply")
        if metric in MEASURES:
            failures.append(f"{where}: is measurable today, so it does apply")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--update", action="store_true",
                        help="tighten baselines that have improved, and write them back")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        document = load_ratchets(root)
        entries = document.get("ratchets") or []
        if not entries:
            raise CouldNotRun("the ratchet file defines no ratchets")
        previous = committed_baselines(root)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    failures: list[str] = []
    improvements: list[tuple[dict, float]] = []
    loosened: list[str] = []

    for entry in entries:
        metric = entry.get("id")
        direction = entry.get("direction")
        baseline = entry.get("baseline")
        where = f"ratchet [{metric}]"

        if metric not in MEASURES:
            failures.append(f"{where}: no measurement is implemented for this metric")
            continue
        if direction not in DIRECTIONS:
            failures.append(f"{where}: direction {direction!r} is not one of "
                            f"{', '.join(DIRECTIONS)}")
            continue
        if not isinstance(baseline, (int, float)):
            failures.append(f"{where}: baseline {baseline!r} is not a number")
            continue

        # A loosened baseline is the whole evasion: it is the one edit a regression needs.
        # But a baseline that may *only* improve is a freeze, not a ratchet — it forbids
        # spending headroom that was deliberately left, and "never blocks a good change" stops
        # being true. So loosening is permitted and made expensive: it must state the exact
        # value it moved from, and why. Naming the old value is what stops one justification
        # covering every later move, since a stale `from` no longer matches.
        if previous is not None and metric in previous:
            if worse(direction, baseline, previous[metric]):
                raised = entry.get("raised") or {}
                reason = str(raised.get("reason", "")).strip()
                if raised.get("from") != previous[metric]:
                    failures.append(
                        f"{where}: baseline was loosened from {previous[metric]} to "
                        f"{baseline}. Loosening one is allowed and must be declared: add "
                        f"`raised: {{from: {previous[metric]}, reason: ...}}`.")
                    continue
                if len(reason) < 20:
                    failures.append(
                        f"{where}: baseline was loosened from {previous[metric]} to "
                        f"{baseline} with no reason worth reading. Say what was bought.")
                    continue
                loosened.append(f"{metric}: {previous[metric]} to {baseline} — {reason}")

        try:
            value = MEASURES[metric](root)
        except CouldNotRun as exc:
            print(f"could not run: {exc}", file=sys.stderr)
            return 2

        # A tolerance is for metrics whose measurement is noisy, not for metrics whose value
        # is inconvenient. Wall-clock time on a shared runner moves by tens of percent between
        # identical runs, and a ratchet that fails on that gets re-run rather than read. It
        # must be declared with a reason, and it is applied to the comparison only — an
        # improvement still tightens to the measured value, so the slack cannot accumulate.
        tolerance = entry.get("tolerance_percent")
        if tolerance is not None:
            if not isinstance(tolerance, (int, float)) or not 0 < tolerance <= 50:
                failures.append(f"{where}: tolerance_percent {tolerance!r} is not a number "
                                f"above 0 and at most 50")
                continue
            if len(str(entry.get("tolerance_reason", "")).strip()) < 20:
                failures.append(f"{where}: declares a tolerance with no reason worth reading. "
                                f"Say what is noisy and why the number moves on its own.")
                continue

        allowance = baseline
        if tolerance is not None:
            slack = abs(baseline) * float(tolerance) / 100
            allowance = baseline + slack if direction == "lower_is_better" else baseline - slack

        if worse(direction, value, allowance):
            failures.append(f"{where}: {value} is worse than the baseline {baseline} "
                            + (f"plus its {tolerance}% tolerance " if tolerance else "")
                            + f"({direction.replace('_', ' ')})")
        elif tolerance is not None and worse(direction, value, baseline):
            print(f"  within tolerance: {metric} is {value} against a baseline of {baseline}")
        elif value != baseline:
            improvements.append((entry, value))
            print(f"  improved: {metric} is {value}, better than the baseline {baseline}")
        else:
            print(f"  held: {metric} at {value}")

    check_unwired(document, failures)

    if args.update and improvements:
        text = (root / "aios" / "ratchets.yml").read_text(encoding="utf-8")
        for entry, value in improvements:
            # Anchored on the id so the right block is rewritten when two share a baseline.
            text = re.sub(rf"(?ms)(- id:\s*{re.escape(entry['id'])}\b.*?baseline:\s*)"
                          rf"{re.escape(str(entry['baseline']))}",
                          rf"\g<1>{value}", text)
        (root / "aios" / "ratchets.yml").write_text(text, encoding="utf-8")
        print(f"\ntightened {len(improvements)} baseline(s).")

    if failures:
        print()
        for failure in failures:
            print(f"  violation: {failure}")
        print(f"\n{len(failures)} ratchet violation(s).")
        return 1

    if loosened:
        # Printed loudly rather than merely permitted. This file is a protected path, so the
        # thing that actually stops a casual loosening is the human who has to approve it —
        # and this is what they read. The tool check is the second layer, not the first.
        print("\n  LOOSENED, and this needs a human to agree with it:")
        for note in loosened:
            print(f"    {note}")

    if improvements and not args.update:
        print(f"\n{len(improvements)} baseline(s) can be tightened. This does not block: a "
              f"ratchet never blocks a good change.")
    print(f"\n{len(entries)} ratchet(s) held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
