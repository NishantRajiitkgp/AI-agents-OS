#!/usr/bin/env python3
"""Require a `human:` trailer on commits touching protected paths (M2-04).

PROVISIONAL. Becomes `aios hook commit-msg` when the binary exists (ADR-006).

This is the weakest of the three layers protecting those paths and the only one the person it
constrains can remove with one command. It is here for the case it is good at — the change
nobody meant to make, caught a second after it was staged rather than ten minutes into a CI
run. It is not what stops a determined edit, and nothing about it should be described as if it
were. CODEOWNERS with server-side required review is that (M2-01), because it is the only one
of the three the committer does not control.

It runs as `commit-msg` rather than `pre-commit`, which the task named. `pre-commit` fires
before a message exists, so a check on the message cannot run there and the two halves of
M2-04 land in two hooks: the message check here, the fast checks in `pre-commit`.

  --message-file PATH   the file git passes to commit-msg
  --message TEXT        a message given directly, for tests
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

from aios_state import CouldNotRun, find_config, load_config

PASS, REFUSED, COULD_NOT_RUN = 0, 1, 2

# `Human: name` — a trailer, matched at the start of a line, case-insensitively on the key
# because git's own trailer handling is. The value must be non-trivial: `human: x` is the
# shape of a control that has been noticed and routed around.
TRAILER = re.compile(r"^human:\s*(.+)$", re.IGNORECASE | re.MULTILINE)
MINIMUM_NAME = 3


def staged(root: Path) -> list[str]:
    try:
        out = subprocess.run(["git", "diff", "--cached", "--name-only"],
                             cwd=root, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise CouldNotRun(f"could not read the index: {exc}")
    if out.returncode != 0:
        raise CouldNotRun(f"git diff --cached failed: {out.stderr.strip()}")
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def protected(paths: list[str], patterns: list[str]) -> list[str]:
    """Which staged paths are protected.

    fnmatch, not pathlib globbing, because the patterns come from config and are written the
    way a .gitignore is. `aios/bin/**` has to match `aios/bin/hooks/x.py`, so a pattern ending
    in `/**` is also tried as a prefix — fnmatch's `*` crosses separators, but the doubled
    form is what a reader expects to mean "and everything under it".
    """
    hits = []
    for path in paths:
        for pattern in patterns:
            prefix = pattern[:-3] + "/" if pattern.endswith("/**") else None
            if fnmatch.fnmatch(path, pattern) or (prefix and path.startswith(prefix)):
                hits.append(path)
                break
    return hits


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message-file")
    parser.add_argument("--message")
    args = parser.parse_args()

    try:
        root = find_config().parent.parent
        patterns = load_config().get("protected_paths") or []
        if args.message is not None:
            message = args.message
        elif args.message_file:
            message = Path(args.message_file).read_text(encoding="utf-8", errors="replace")
        else:
            raise CouldNotRun("no message given; pass --message-file or --message")
        touched = protected(staged(root), patterns)
    except (CouldNotRun, OSError) as exc:
        # Could-not-run, not refused. A commit blocked because this script could not read the
        # index is a commit blocked for a reason that has nothing to do with the committer,
        # and the local layer is not worth that.
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if not touched:
        return PASS

    match = TRAILER.search(message)
    if match and len(match.group(1).strip()) >= MINIMUM_NAME:
        print(f"{len(touched)} protected path(s), attributed to "
              f"{match.group(1).strip()}.")
        return PASS

    listed = "\n".join(f"    {path}" for path in sorted(touched)[:10])
    more = f"\n    ... and {len(touched) - 10} more" if len(touched) > 10 else ""
    print(f"This commit changes {len(touched)} path(s) outside the agent's write scope:\n"
          f"{listed}{more}\n\n"
          f"Add a trailer naming the person accountable for the change:\n"
          f"    Human: <name>\n\n"
          f"The trailer is not permission — it is a record of who to ask. The gate that "
          f"actually holds is the review requirement on the same paths, which is server-side "
          f"and which this does not substitute for.", file=sys.stderr)
    return REFUSED


if __name__ == "__main__":
    raise SystemExit(main())
