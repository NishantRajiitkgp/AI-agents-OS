#!/usr/bin/env python3
"""The fast local checks, run before a commit is written (M2-04).

PROVISIONAL. Becomes `aios hook pre-commit` when the binary exists (ADR-006).

The budget is five seconds, and the budget is the design. Everything here is chosen because it
is cheap on a diff and expensive to discover late; everything expensive is deliberately not
here even where it would catch more. A pre-commit hook that takes twenty seconds is removed by
the third day, and a removed hook catches nothing — so the failure mode being designed against
is not "a bug slips through", it is "the developer turns it off".

That is why this is scoped to the staged files rather than the tree, and why the full suite,
the ratchets and the whole-repository gates are not called. Those run in CI, where waiting is
what the machine is for. The one Contract-class check that does run is the secrets scan: a
credential is the one failure a later gate cannot undo, because by the time CI sees it the
value is already in an object git will keep.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from aios_state import CouldNotRun, find_config

PASS, REFUSED, COULD_NOT_RUN = 0, 1, 2

BUDGET_SECONDS = 5.0


def staged(root: Path) -> list[str]:
    out = subprocess.run(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
                         cwd=root, capture_output=True, text=True, timeout=10)
    if out.returncode != 0:
        raise CouldNotRun(f"git diff --cached failed: {out.stderr.strip()}")
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def run(root: Path, name: str, argv: list[str]) -> tuple[str, int, str]:
    started = time.monotonic()
    out = subprocess.run([sys.executable, *argv], cwd=root, capture_output=True, text=True)
    return name, out.returncode, f"{time.monotonic() - started:.1f}s"


def main() -> int:
    try:
        root = find_config().parent.parent
        files = staged(root)
    except (CouldNotRun, OSError, subprocess.SubprocessError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if not files:
        return PASS

    started = time.monotonic()
    failures = []

    # Staged-only, and the only Contract-class check fast enough to belong here.
    checks = [("secrets", [".github/scripts/scan-secrets.py", "--paths", *files])]

    for name, argv in checks:
        script = root / argv[0]
        if not script.exists():  # a clone that has not built this half yet
            continue
        label, code, took = run(root, name, argv)
        print(f"  {label}: {'ok' if code == 0 else 'FAILED'} ({took})")
        if code != 0:
            failures.append(label)

    elapsed = time.monotonic() - started
    if elapsed > BUDGET_SECONDS:
        # Reported, never fatal. A slow hook is a problem for the person maintaining the hook,
        # and refusing their commit over it would be the tool prioritising its own budget over
        # the work — which is the same instinct that gets it uninstalled.
        print(f"  (took {elapsed:.1f}s, over the {BUDGET_SECONDS:.0f}s budget — that is a bug "
              f"in this hook, not in the commit)", file=sys.stderr)

    if failures:
        print(f"\nRefused by: {', '.join(failures)}. Nothing has been committed.",
              file=sys.stderr)
        return REFUSED
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
