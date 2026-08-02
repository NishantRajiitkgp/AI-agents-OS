#!/usr/bin/env python3
"""Install the local git hooks (M2-04).

PROVISIONAL. Becomes `aios install-hooks` when the binary exists (ADR-006).

Git requires the hook to be a file it can execute at `.git/hooks/<event>`, and on this
platform it runs it under the `sh` that ships with Git for Windows. So the two files written
here are shell, which ADR-006 forbids in `aios/bin/` — the distinction being that these are
not the logic. Each is one line that hands off to a Python script under version control. A
shim that can only fail by not finding the interpreter is a different risk from logic nobody
can run because the execution policy blocks it.

`.git/hooks/` is not version-controlled, so this is opt-in per clone by construction. That is
a property of git, not a decision made here, and it is the reason this layer cannot be relied
on: a clone that never runs this command has no local checks and looks identical to one that
has. The layer that does not depend on the committer is CODEOWNERS (M2-01).

Existing hooks are never overwritten without --force. Silently replacing a hook someone else
installed is how a tool loses the right to be run.
"""

from __future__ import annotations

import argparse
import stat
import sys
from pathlib import Path

from aios_state import CouldNotRun, find_config

PASS, REFUSED, COULD_NOT_RUN = 0, 1, 2

MARKER = "# installed by aios install-hooks"

HOOKS = {
    "commit-msg": '"$(command -v python3 || command -v python)" '
                  '.github/scripts/check-human-trailer.py --message-file "$1"',
    "pre-commit": '"$(command -v python3 || command -v python)" '
                  '.github/scripts/pre-commit.py',
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true",
                        help="replace hooks this tool did not write")
    parser.add_argument("--check", action="store_true",
                        help="report what is installed and change nothing")
    args = parser.parse_args()

    try:
        root = find_config().parent.parent
        hooks = root / ".git" / "hooks"
        if not hooks.parent.is_dir():
            raise CouldNotRun("no .git directory; this is not a clone")
        hooks.mkdir(parents=True, exist_ok=True)
    except (CouldNotRun, OSError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    refused = []
    for name, body in HOOKS.items():
        path = hooks / name
        script = f"#!/bin/sh\n{MARKER}\n{body}\n"
        if args.check:
            state = ("absent" if not path.exists()
                     else "installed" if MARKER in path.read_text(encoding="utf-8",
                                                                  errors="replace")
                     else "present, not ours")
            print(f"  {name}: {state}")
            continue
        if path.exists() and MARKER not in path.read_text(encoding="utf-8", errors="replace") \
                and not args.force:
            refused.append(name)
            continue
        path.write_text(script, encoding="utf-8", newline="\n")
        path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print(f"  {name}: installed")

    if refused:
        print(f"\nNot replacing {', '.join(refused)}: something else wrote them. Read them, "
              f"then re-run with --force if the replacement is what you want.", file=sys.stderr)
        return REFUSED
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
