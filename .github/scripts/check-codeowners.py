#!/usr/bin/env python3
"""Every protected path has a named owner (M2-01).

PROVISIONAL. Becomes `aios check codeowners` when the binary exists (ADR-006).

Two lists say which paths are protected: `protected_paths` in aios/config.yml, which the local
hook and the scope checker read, and .github/CODEOWNERS, which GitHub reads. Only the second
is enforced server-side. If they drift, the gap is silent and sits exactly where nobody looks
— the config keeps refusing the edit locally while the branch accepts it, which reads as a
control that works right up until the moment it is tested.

It also fails while the placeholder owner is present. GitHub does not error on an unresolvable
owner; it drops the rule and reports the file as valid. A CODEOWNERS naming nobody is the
worst state of the three, because it looks exactly like one naming somebody.

None of this makes the file enforced. That is a branch protection setting, which lives on the
forge — and this said for a while that it therefore could not be checked from here, which was
wrong. It is checked, by check-branch-protection.py, against the state `branch_protection` in
aios/config.yml declares. The two questions stay in two scripts because they fail for
unrelated reasons and a single red step would not say which.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from aios_state import CouldNotRun, find_config, load_config

PASS, FAILED, COULD_NOT_RUN = 0, 1, 2

PLACEHOLDER = "@OWNER-PLACEHOLDER"
OWNER = re.compile(r"@[A-Za-z0-9][A-Za-z0-9-]*(?:/[A-Za-z0-9._-]+)?$")


def rules(text: str) -> list[tuple[str, list[str]]]:
    parsed = []
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        pattern, *owners = line.split()
        parsed.append((pattern, owners))
    return parsed


def covers(pattern: str, protected: str) -> bool:
    """Does a CODEOWNERS pattern cover a config protected_paths pattern?

    Deliberately a comparison of the two written forms rather than a match against real files.
    A tree-based check passes on a repository that happens not to contain the file yet, and
    the point of the protected set is what it will refuse tomorrow.
    """
    owned = pattern.strip("/")
    want = protected.removesuffix("/**").removesuffix("/*").strip("/")
    if owned == want:
        return True
    # `/tests/` covers `tests/**`; a directory rule covers everything beneath it.
    return pattern.endswith("/") and want.startswith(owned + "/")


def main() -> int:
    try:
        root = find_config().parent.parent
        patterns = load_config().get("protected_paths") or []
        path = root / ".github" / "CODEOWNERS"
        text = path.read_text(encoding="utf-8")
    except (CouldNotRun, OSError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    parsed = rules(text)
    problems = []

    unowned = [pattern for pattern, owners in parsed if not owners]
    for pattern in unowned:
        problems.append(f"{pattern} is listed with no owner, which removes any rule an earlier "
                        f"line gave it — CODEOWNERS is last-match-wins")

    for pattern, owners in parsed:
        for owner in owners:
            if not OWNER.match(owner):
                problems.append(f"{pattern}: {owner!r} is not a @user or @org/team")

    if PLACEHOLDER in text:
        count = text.count(PLACEHOLDER)
        problems.append(
            f"{count} rule(s) still name {PLACEHOLDER}. GitHub does not reject an owner it "
            f"cannot resolve — it drops the rule and reports the file as valid, so this file "
            f"would protect nothing while looking exactly like one that does. Replace it with "
            f"the handle or team that reviews these paths")

    for protected in patterns:
        if protected.startswith("**/"):
            # A bare-glob rule like `**/*_test.*` is written in CODEOWNERS without the prefix.
            wanted = protected[3:]
            if not any(p == wanted for p, _ in parsed):
                problems.append(f"protected_paths has {protected!r} with no CODEOWNERS rule; "
                                f"add {wanted!r}")
            continue
        if not any(covers(p, protected) for p, _ in parsed):
            problems.append(f"protected_paths has {protected!r} and CODEOWNERS does not cover "
                            f"it. Locally the edit is refused and on the branch it is not")

    for problem in problems:
        print(f"  {problem}")

    if problems:
        print(f"\n{len(problems)} problem(s) in .github/CODEOWNERS.")
        return FAILED

    print(f"{len(parsed)} rule(s), covering every entry in protected_paths.\n"
          f"Not checked here: whether the branch requires code-owner review, which is the "
          f"setting that makes this file mean anything. That is check-branch-protection.py.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
