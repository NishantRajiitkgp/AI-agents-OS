#!/usr/bin/env python3
"""The always-on context may not be larger than it was N commits ago (M5-02).

PROVISIONAL. Moves into the binary at `M1-08`.

There is already a budget on this set, and a ratchet on it. This is a third thing, and the
difference is where the number it compares against comes from.

`check-always-on.py` enforces a **ceiling** — 200 lines, from ADR-011. A ceiling permits every
increase below it, so a set at 153 lines can grow by 47 without a single gate objecting.

`check-ratchets.py` compares against a **stored baseline** in `aios/ratchets.yml`. That is
strictly better, and it has one weakness that matters more than it looks: the baseline is a
file in the repository, so the commit that grows the set can raise the baseline. There is a
`raised:` field demanding a reason, and the reason is written by the party doing the raising,
in the same change, under the same deadline.

This compares against **git history**, which the commit under review cannot edit. That is the
whole of the idea. Everything else here is detail.

Why it is worth a third implementation of an adjacent-looking rule: every system in this space
gets worse in month six than in month one, and the mechanism is always the same. Adding a rule
feels responsible and takes a minute. Deleting one feels reckless and nobody is thanked for it.
The asymmetry is in the psychology, not the tooling, so the tooling has to lean the other way —
past the line, an addition has to name a deletion, and shrinking has to be the path of least
resistance rather than an act of courage.

Growth is not forbidden. It requires a `Grow-context:` trailer with a reason on a commit in the
window, which is the same shape as the override trailer in `M3-07` and for the same reason: the
record lands somewhere the next change cannot quietly revise.

Usage:
    check-growth.py                   compare against the window in aios/config.yml
    check-growth.py --window 5        compare against 5 commits ago
    check-growth.py --root <path>     operate on another repository, for tests

Exit 0 held or shrunk, 1 grew, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HELD, GREW, COULD_NOT_RUN = 0, 1, 2

# The pattern captures whatever follows the trailer, including nothing. Whether that is a
# reason is `MINIMUM_REASON`'s business and only its business — requiring at least one
# character here as well reads like a second guard and is not one, since a one-character
# reason fails the length check anyway.
TRAILER = re.compile(r"^Grow-context:\s*(.*)$", re.MULTILINE)
MINIMUM_REASON = 20

# The always-on set, as shapes rather than paths, because which files match is exactly what
# changes between two commits.
SHAPES = ("AGENTS.md", ".cursor/rules/", ".claude/agents/", ".claude/skills/")


def load_always_on():
    """One measurement of the set, shared with the budget gate.

    Imported rather than reimplemented: this repository has already shipped one incident where
    two counts of this same set disagreed, and reported "held" while the thing grew.
    """
    path = Path(__file__).resolve().parent / "check-always-on.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("check_always_on", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CouldNotRun(Exception):
    pass


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args],
                            capture_output=True)
    if result.returncode:
        raise CouldNotRun(f"git {' '.join(args)}: "
                          f"{result.stderr.decode('utf-8', 'replace').strip()}")
    return result.stdout.decode("utf-8", "replace")


def history(root: Path, window: int) -> list[str]:
    """The commits in the window, newest first. Shorter history is not an error — a repository
    on its third commit is compared against its first."""
    try:
        out = git(root, "rev-list", f"--max-count={window + 1}", "HEAD")
    except CouldNotRun as exc:
        if "unknown revision" in str(exc) or "bad revision" in str(exc):
            return []
        raise
    return out.split()


def materialise(root: Path, rev: str, into: Path) -> None:
    """Reconstruct the always-on set as it was at `rev`.

    A worktree would be simpler and would leave state in `.git/worktrees` that a failed run
    does not clean up. Only a handful of files are ever needed, so they are read out directly.
    """
    for line in git(root, "ls-tree", "-r", "--name-only", rev).splitlines():
        path = line.strip()
        if not path.startswith(SHAPES):
            continue
        destination = into / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(
            subprocess.run(["git", "-C", str(root), "show", f"{rev}:{path}"],
                           capture_output=True, check=True).stdout)


def measure_at(root: Path, rev: str, always_on) -> tuple[int, dict[str, int]]:
    scratch = Path(tempfile.mkdtemp())
    try:
        materialise(root, rev, scratch)
        if not (scratch / "AGENTS.md").is_file():
            # The set did not exist yet. Zero is the honest answer and makes any later
            # addition growth, which is correct — it is growth from nothing.
            return 0, {}
        found = dict(always_on.contributors(scratch))
        return sum(found.values()), found
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def permission(root: Path, revisions: list[str]) -> tuple[str, str] | None:
    """The newest `Grow-context:` trailer in the window, with a reason worth reading.

    A trailer authorises the level the set reached *at its own commit*, not everything that
    happens afterwards. The first draft permitted any growth while the trailer sat in the
    window, which turns one justification into a licence lasting twenty commits — the escape
    hatch quietly becoming the door.
    """
    for rev in revisions:
        match = TRAILER.search(git(root, "log", "-1", "--format=%B", rev))
        if match and len(match.group(1).strip()) >= MINIMUM_REASON:
            return rev, match.group(1).strip()
    return None


def report_membership(before: dict[str, int], after: dict[str, int]) -> None:
    """Rules and subagents added versus deleted.

    M5 is the milestone that asks whether this system can shrink, and the only honest answer
    is a count of deletions next to a count of additions. Reported at every run, including
    runs that pass, because a set that holds its line count while churning its membership is
    a different thing from one that is stable.
    """
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    for label in removed:
        print(f"  deleted: {label} (-{before[label]} lines)")
    for label in added:
        print(f"  added:   {label} (+{after[label]} lines)")
    if not added and not removed:
        print("  membership unchanged")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--window", type=int, help="commits to look back")
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    always_on = load_always_on()

    try:
        config = yaml.safe_load((root / "aios" / "config.yml").read_text(encoding="utf-8"))
        window = args.window or (config.get("budgets") or {})["growth_window_commits"]
        revisions = history(root, window)
    except (OSError, KeyError, yaml.YAMLError, CouldNotRun) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if not revisions:
        # Loud rather than silent. A check that passes because it had nothing to read is
        # indistinguishable, in a green CI run, from one that passed because the thing it
        # watches is healthy — and this repository has zero commits by a deliberate choice,
        # so that state is real rather than theoretical.
        print("::warning::No commit history, so the growth ratchet has nothing to compare "
              "against and is enforcing nothing. It starts working at the first commit.")
        return COULD_NOT_RUN

    try:
        now = always_on.measure(root)
        earliest = revisions[-1]
        then, before = measure_at(root, earliest, always_on)
        after = dict(always_on.contributors(root))
    except (CouldNotRun, OSError, subprocess.CalledProcessError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    span = len(revisions) - 1
    print(f"Always-on context: {then} lines {span} commit(s) ago, {now} now.")
    report_membership(before, after)

    baseline, granted = then, None
    try:
        granted = permission(root, revisions)
        if granted:
            authorised, _ = measure_at(root, granted[0], always_on)
            baseline = max(baseline, authorised)
    except (CouldNotRun, OSError, subprocess.CalledProcessError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if now <= baseline:
        if granted and baseline > then:
            print(f"held at the level permitted by {granted[0][:8]}: {granted[1]}")
        else:
            print(f"held ({'unchanged' if now == then else f'down {then - now}'}).")
        return HELD

    print(f"::error::Always-on context grew by {now - baseline} lines over {span} commit(s), "
          f"from {baseline} to {now}.")
    print("Growth is allowed and has to be said out loud: put a `Grow-context: <reason>` "
          "trailer on the commit, naming what the addition is worth and what it displaces.")
    print("The cheaper answer is usually deletion. Something in this set is almost certainly "
          "no longer earning its place, and finding it costs less than justifying the growth.")
    return GREW


if __name__ == "__main__":
    raise SystemExit(main())
