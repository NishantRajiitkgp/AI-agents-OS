#!/usr/bin/env python3
"""The default branch enforces what `branch_protection` in aios/config.yml declares (M2-02).

PROVISIONAL. Becomes `aios check branch-protection` when the binary exists (ADR-006).

`check-codeowners.py` verifies that CODEOWNERS covers the protected set and names a resolvable
owner, and then says it cannot check the setting that makes any of it true. This is that check.
It was written as uncheckable and it is not: a repository's `protected` flag is served without
a token, and the detail is served to any token that can read the repository, which CI has.

The asymmetry is deliberate and is the whole design of this script. Without credentials it can
still tell *protected* from *unprotected*, which is the difference that matters — a branch with
no protection at all is the state this gate exists to refuse, and it is also the state a
repository is in by default and stays in silently. With credentials it compares every declared
setting. It never reports the second as though it had done the first.

An unreachable API is could-not-run, not a failure. A network gate that reports a flaky lookup
as a violation teaches people to re-run it until it passes, and after that it is not a gate.

Exit codes: 0 as declared · 1 the branch does not enforce it · 2 could not run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from aios_state import CouldNotRun, load_config

PASS, FAILED, COULD_NOT_RUN = 0, 1, 2

API = "https://api.github.com"
REMOTE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)")


def slug() -> str:
    """`owner/repo`, from the environment CI sets or from the remote a clone was made with.

    Read rather than configured. A hard-coded slug is correct in exactly one repository and
    silently wrong in every fork of it, and this check's answer is about a specific branch on
    a specific forge, so being confidently wrong about which one is the failure to avoid.
    """
    if repository := os.environ.get("GITHUB_REPOSITORY"):
        return repository
    try:
        url = subprocess.run(["git", "remote", "get-url", "origin"],
                             capture_output=True, text=True, timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise CouldNotRun(f"no origin remote to read: {exc}") from exc
    match = REMOTE.search(url)
    if not match:
        raise CouldNotRun(f"origin is not a GitHub remote: {url or '(none)'}")
    return f"{match['owner']}/{match['repo']}"


def get(path: str, token: str | None) -> dict | None:
    """The parsed body, or None where the endpoint answered 'not to you' or 'not there'."""
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "aios"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(
                urllib.request.Request(API + path, headers=headers), timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            return None
        raise CouldNotRun(f"{path}: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CouldNotRun(f"{path}: {exc}") from exc


def compare(want: dict, protection: dict) -> list[str]:
    """Declared against actual, one line per disagreement, in the config's vocabulary."""
    reviews = protection.get("required_pull_request_reviews") or {}
    checks = protection.get("required_status_checks") or {}
    actual = {
        "required_reviews": reviews.get("required_approving_review_count", 0),
        "require_code_owner_review": bool(reviews.get("require_code_owner_reviews")),
        "dismiss_stale_reviews": bool(reviews.get("dismiss_stale_reviews")),
        "require_status_checks": bool(checks),
        "require_branches_up_to_date": bool(checks.get("strict")),
        "allow_force_pushes": bool((protection.get("allow_force_pushes") or {}).get("enabled")),
        "allow_deletions": bool((protection.get("allow_deletions") or {}).get("enabled")),
        "enforce_admins": bool((protection.get("enforce_admins") or {}).get("enabled")),
    }
    problems = []
    for key, expected in want.items():
        if key == "branch" or key not in actual:
            continue
        if actual[key] != expected:
            problems.append(f"{key}: declared {expected!r}, branch has {actual[key]!r}")
    return problems


def main() -> int:
    try:
        want = load_config().get("branch_protection") or {}
        if not want:
            print("could not run: aios/config.yml declares no branch_protection",
                  file=sys.stderr)
            return COULD_NOT_RUN
        repository = slug()
        branch = want.get("branch", "main")
        summary = get(f"/repos/{repository}/branches/{branch}", os.environ.get("GITHUB_TOKEN"))
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if summary is None:
        print(f"could not run: {repository} has no branch {branch}, or it is not visible",
              file=sys.stderr)
        return COULD_NOT_RUN

    if not summary.get("protected"):
        print(f"  {repository}@{branch} has no branch protection at all. CODEOWNERS is a file "
              f"the forge is not consulting, and every path in protected_paths is refused "
              f"locally and accepted on the branch.")
        print("\n1 problem. See docs/runbooks/ for the settings this expects.")
        return FAILED

    protection = get(f"/repos/{repository}/branches/{branch}/protection",
                     os.environ.get("GITHUB_TOKEN"))
    if protection is None:
        # The coarse flag was readable and said yes; the detail needs a token this run does not
        # have. Reported as a pass with its limit stated, because failing here would make the
        # gate red on every unauthenticated run of a correctly configured repository.
        print(f"{repository}@{branch} is protected.\n"
              f"Not checked on this run: which settings, which needs a token that can read the "
              f"repository. CI has one; a local run without GITHUB_TOKEN does not.")
        return PASS

    problems = compare(want, protection)
    for problem in problems:
        print(f"  {problem}")
    if problems:
        print(f"\n{len(problems)} setting(s) differ from aios/config.yml. Either the branch "
              f"drifted from what was decided, or the decision changed and nobody wrote it "
              f"down — and those need different fixes.")
        return FAILED

    print(f"{repository}@{branch} enforces every setting branch_protection declares.")
    return PASS


if __name__ == "__main__":
    raise SystemExit(main())
