#!/usr/bin/env python3
"""Independently re-check every verification record (M1-15).

PROVISIONAL. Becomes `aios verify-records` when the binary exists (ADR-006).

**The state the agent can write is not the state anyone reads.** A task file says `done`
because something wrote that word into it, and the thing that wrote it is the party whose work
is being judged. This script is the second reader. For every task claiming `done` it checks
that a record exists, that the commit it names is real, that the commands it names are the
ones the task declares, and that those commands still pass at that commit.

The four checks are not interchangeable and each closes a different hole:

  no record            the frontmatter was hand-edited to `done` without the CLI
  unknown SHA          the record points at a commit nobody can produce
  commands mismatch    `verify` was amended after the record was written, so the record
                       attests to a weaker check than the task now claims to have
  re-run fails         the record was true once and is not true now

Only the last is a normal, blameless failure — code rots, and that is what a re-check is for.
The first three are the shape of a claim that was never earned, which is why they are reported
separately rather than folded into one count.

Re-running is the expensive half and the honest half. `--no-rerun` exists for the pre-commit
path, where seconds matter; CI runs the full thing, because a record nobody re-runs is a
sentence in a file.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from aios_state import CouldNotRun, find_config, load_tasks, state_dir

PASS, FAILED, COULD_NOT_RUN = 0, 1, 2


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                          timeout=120)


def has_commits(root: Path) -> bool:
    return git(root, "rev-parse", "--verify", "HEAD").returncode == 0


def commit_exists(root: Path, sha: str) -> bool:
    """Is this a real commit object in this repository?

    `cat-file -e <sha>^{commit}` rather than `rev-parse`, because rev-parse happily resolves
    a branch name, a tag, or `HEAD` — and a record naming `HEAD` would pass a check that only
    asked whether the string resolved, while attesting to nothing in particular.
    """
    if not sha or len(sha) < 7:
        return False
    return git(root, "cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def record_of(task: dict) -> dict | None:
    data = task.get("data") or {}
    record = data.get("verified")
    return record if isinstance(record, dict) else None


def recorded_commands(record: dict) -> list[str]:
    entries = record.get("commands") or []
    out = []
    for entry in entries:
        if isinstance(entry, dict) and "command" in entry:
            out.append(str(entry["command"]))
        elif isinstance(entry, str):
            out.append(entry)
    return out


def rerun(root: Path, sha: str, commands: list[str]) -> list[tuple[str, int]]:
    """Run the recorded commands at the recorded commit, in a detached worktree.

    A worktree rather than a checkout of the running tree. Checking out an old commit in place
    would rewrite the working directory of whoever ran this, and on CI it would silently change
    what every later step in the job is looking at. The temporary tree is removed afterwards
    whether or not the commands passed.
    """
    import tempfile

    results: list[tuple[str, int]] = []
    with tempfile.TemporaryDirectory() as tmp:
        tree = Path(tmp) / "at"
        made = git(root, "worktree", "add", "--detach", str(tree), sha)
        if made.returncode != 0:
            raise CouldNotRun(f"could not create a worktree at {sha[:8]}: "
                              f"{made.stderr.strip()}")
        try:
            for command in commands:
                out = subprocess.run(command, shell=True, cwd=tree, capture_output=True,
                                     text=True, timeout=900)
                results.append((command, out.returncode))
        finally:
            git(root, "worktree", "remove", "--force", str(tree))
    return results


def check(root: Path, task: dict, do_rerun: bool) -> list[str]:
    data = task.get("data") or {}
    task_id = data.get("id", task.get("path", "?"))
    problems: list[str] = []

    record = record_of(task)
    if record is None:
        return [f"{task_id} is done and carries no verification record. Either the CLI did "
                f"not write it or the status was edited by hand — and from here those look "
                f"identical, which is why the record is mandatory rather than expected."]

    sha = str(record.get("sha") or "").strip()
    if not commit_exists(root, sha):
        problems.append(f"{task_id} records commit {sha[:12] or '(none)'}, which is not a "
                        f"commit in this repository")

    declared = [str(c) for c in (data.get("verify") or [])]
    recorded = recorded_commands(record)
    if not recorded:
        problems.append(f"{task_id} records no commands, so it attests to nothing")
    elif recorded != declared:
        added = [c for c in declared if c not in recorded]
        gone = [c for c in recorded if c not in declared]
        detail = []
        if added:
            detail.append(f"{len(added)} command(s) declared but never verified: {added[0]!r}")
        if gone:
            detail.append(f"{len(gone)} verified but no longer declared: {gone[0]!r}")
        problems.append(
            f"{task_id}: the record does not match the task's verify list. "
            + "; ".join(detail or ["the order differs"])
            + ". A verify list amended after the record was written means the record attests "
              "to a different check from the one the task now claims.")

    failed_exits = [(c, code) for c, code in
                    ((e.get("command"), e.get("exit")) for e in (record.get("commands") or [])
                     if isinstance(e, dict))
                    if code not in (0, None)]
    for command, code in failed_exits:
        problems.append(f"{task_id} records {command!r} exiting {code} and is still marked "
                        f"done. The record contradicts the status it was written to justify.")

    if do_rerun and not problems and recorded:
        try:
            results = rerun(root, sha, recorded)
        except (CouldNotRun, subprocess.SubprocessError, OSError) as exc:
            raise CouldNotRun(f"{task_id}: {exc}")
        for command, code in results:
            if code != 0:
                problems.append(f"{task_id}: {command!r} exits {code} at {sha[:8]}, where the "
                                f"record says it passed")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="repository root; discovered if omitted")
    parser.add_argument("--no-rerun", action="store_true",
                        help="check the shape of each record without re-running its commands")
    args = parser.parse_args()

    try:
        root = Path(args.root) if args.root else find_config().parent.parent
        tasks = load_tasks(root / "aios" / "tasks" if args.root else state_dir("tasks"))
    except (CouldNotRun, OSError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    unreadable = [t for t in tasks if t.get("error")]
    for task in unreadable:
        print(f"  unreadable: {task['path']}: {task['error']}")

    done = [t for t in tasks
            if not t.get("error") and (t.get("data") or {}).get("status") == "done"]

    if not done:
        print("No task claims done, so there is no record to re-check. That is a true "
              "statement about this repository and not a passing grade.")
        return FAILED if unreadable else PASS

    do_rerun = not args.no_rerun
    if do_rerun and not has_commits(root):
        # Zero commits means every recorded SHA is unresolvable, and reporting that as forgery
        # would be a false accusation aimed at the state of the repository rather than at
        # anything anybody did.
        print("could not run: this repository has no commits, so no recorded commit can be "
              "resolved and no re-run is possible.", file=sys.stderr)
        return COULD_NOT_RUN

    problems: list[str] = []
    try:
        for task in done:
            problems.extend(check(root, task, do_rerun))
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    for problem in problems:
        print(f"  {problem}")

    if problems or unreadable:
        print(f"\n{len(problems)} record problem(s) across {len(done)} done task(s).")
        print("A verification record is evidence, not an assertion. Its only value is that "
              "somebody other than its author can check it, which is what just happened.")
        return FAILED

    scope = "re-run" if do_rerun else "checked for shape only"
    print(f"{len(done)} done task(s), every record intact and {scope}.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
