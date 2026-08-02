#!/usr/bin/env python3
"""Scan for committed credentials, in the working tree and in history.

PROVISIONAL. Moves into `aios check` at M1-14, per ADR-006.

Contract at every tier, prototypes included (06 §3). The reason prototypes are not exempt is
that prototype repositories become real repositories with their history intact, and a
credential committed on day one is still in the history on the day the repository gets its
first real user. Nothing about "it was only a prototype" removes the key from the log.

Which is why --history exists and is not optional. Deleting a secret in a later commit
changes nothing: it remains readable at the commit that added it, forever, to anyone who can
clone. A scanner that only looked at the current tree would report clean on a repository
whose entire history is compromised — the most dangerous possible false negative, because it
is indistinguishable from real safety.

There is deliberately no inline waiver comment. A Contract gate that can be silenced by a
line in the file it is checking is an Advisory gate wearing a Contract label. The route for a
legitimate credential-shaped string is to make it obviously not a credential — the
placeholder list below is what that means in practice.

Exit codes: 0 clean, 1 secrets found, 2 could not run.
"""

from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

# Known credential formats, matched on their issuer's own prefix and length. These carry
# almost no false-positive risk: a string is not accidentally shaped like an AWS key ID.
PROVIDER_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("aws-access-key-id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("github-fine-grained-pat", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{60,}\b")),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{12,}\b")),
    ("stripe-secret-key", re.compile(r"\b[sr]k_live_[A-Za-z0-9]{16,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("openai-key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}\b")),
    ("npm-token", re.compile(r"\bnpm_[A-Za-z0-9]{36}\b")),
    ("sendgrid-key", re.compile(r"\bSG\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{40,}\b")),
    ("twilio-key", re.compile(r"\bSK[0-9a-f]{32}\b")),
    ("private-key-block", re.compile(r"-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("json-web-token", re.compile(
        r"\beyJ[A-Za-z0-9_\-]{8,}\.eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\b")),
    ("azure-storage-key", re.compile(r"AccountKey=[A-Za-z0-9+/=]{60,}")),
    ("basic-auth-in-url", re.compile(r"://[^\s:/@]+:[^\s:/@]{8,}@[A-Za-z0-9.\-]+")),
]

# The generic catch: a secret-shaped name assigned a high-entropy value. This is where false
# positives would come from, so it needs both the name and the entropy to agree.
ASSIGNMENT = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|apikey|access[_-]?key|"
    r"client[_-]?secret|private[_-]?key|auth[_-]?token|credential)\b"
    r"\s*[:=]\s*['\"]?([A-Za-z0-9+/=_\-]{20,})['\"]?"
)

# Values that are shaped like a credential but say plainly that they are not one. This is the
# supported route for documentation and fixtures, in place of a waiver comment.
PLACEHOLDER = re.compile(
    r"(?i)^(?:x{3,}|\.{3,}|-{3,}|<[^>]*>|\$\{?[a-z_][a-z0-9_]*\}?|"
    r"(?:your|my|the)[_-]?\w+|example\w*|\w*example|changeme|redacted|placeholder|"
    r"dummy|sample|fake|test\w*|\w*_here|none|null|nil|true|false|\d+)$"
)
PLACEHOLDER_SUBSTRING = re.compile(r"(?i)example|redacted|placeholder|changeme|xxxxx|your[_-]")

ENTROPY_FLOOR = 3.5

# Binary content only. Lockfiles are deliberately *not* skipped: they were, until a mutation
# test showed the skip was load-bearing for nothing. The generic rule keys on the variable
# name rather than raw entropy, so `integrity` and `checksum` hashes never matched it — while
# the skip would have hidden a private-registry URL with a real token in it, which is one of
# the more common ways a credential actually reaches a repository.
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".gz", ".exe", ".ico",
                 ".woff", ".woff2", ".ttf", ".so", ".dll", ".class", ".pyc"}


class CouldNotRun(Exception):
    pass


def entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    total = len(value)
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def looks_like_placeholder(value: str) -> bool:
    return bool(PLACEHOLDER.match(value) or PLACEHOLDER_SUBSTRING.search(value))


def scan_text(text: str, where: str) -> list[str]:
    """Report every credential-shaped string in one blob of text."""
    findings: list[str] = []

    for lineno, line in enumerate(text.splitlines(), 1):
        if len(line) > 4000:
            continue  # minified or generated; not where credentials are authored

        for name, pattern in PROVIDER_PATTERNS:
            match = pattern.search(line)
            if match and not looks_like_placeholder(match.group(0)):
                findings.append(f"{where}:{lineno} [{name}] {redact(match.group(0))}")

        match = ASSIGNMENT.search(line)
        if match:
            value = match.group(2)
            if not looks_like_placeholder(value) and entropy(value) >= ENTROPY_FLOOR:
                findings.append(
                    f"{where}:{lineno} [high-entropy-assignment] "
                    f"{match.group(1)} = {redact(value)} (entropy {entropy(value):.2f})")

    return findings


def redact(value: str) -> str:
    """Never print the whole thing. CI logs are widely readable and often retained."""
    return value[:4] + "…" + f"[{len(value)} chars]" if len(value) > 8 else "…"


def git(args: list[str], repo: Path) -> str:
    result = subprocess.run(["git", "-C", str(repo), *args],
                            capture_output=True, text=True, errors="replace")
    if result.returncode != 0:
        raise CouldNotRun(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout


def skip_path(path: str) -> bool:
    return Path(path).suffix.lower() in SKIP_SUFFIXES


def scan_worktree(repo: Path, only: list[str] | None = None) -> list[str]:
    """Scan the tracked tree, or just the paths named.

    `only` exists for the pre-commit hook (M2-04), which has five seconds and a handful of
    staged files. The skip rules still apply to a named path — a caller passing an explicit
    list has said which files, not which rules.
    """
    findings: list[str] = []
    for path in (only if only is not None else git(["ls-files"], repo).splitlines()):
        if not path or skip_path(path):
            continue
        full = repo / path
        try:
            text = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings.extend(scan_text(text, path))
    return findings


def scan_history(repo: Path) -> list[str]:
    """Scan every version of every file that any commit ever introduced.

    Reads commit patches rather than the current tree, so a secret added in one commit and
    deleted in the next is still found at the commit that added it — which is the only place
    it matters, because that is where a clone can still read it.
    """
    if not git(["rev-list", "--all", "--count"], repo).strip().strip("0"):
        return []  # no commits yet; nothing to scan rather than an error

    patch = git(["log", "--all", "--no-color", "--no-merges", "-p",
                 "--format=commit %H"], repo)

    findings: list[str] = []
    commit = "?"
    path = "?"
    for line in patch.splitlines():
        if line.startswith("commit "):
            commit = line.split()[1][:8]
        elif line.startswith("+++ b/"):
            path = line[6:]
        elif line.startswith("+") and not line.startswith("+++"):
            if skip_path(path):
                continue
            findings.extend(scan_text(line[1:], f"{commit} {path}"))
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=".", help="repository to scan")
    parser.add_argument("--history", action="store_true",
                        help="scan every commit rather than the working tree")
    parser.add_argument("--all", action="store_true", help="scan both")
    parser.add_argument("--paths", nargs="*", metavar="PATH",
                       help="scan only these tracked paths, relative to the repository root")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    try:
        findings: list[str] = []
        if args.history or args.all:
            findings += scan_history(repo)
        if not args.history or args.all:
            findings += scan_worktree(repo, args.paths)
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    # Order-preserving dedupe: the same secret in tree and history is one problem.
    seen: set[str] = set()
    unique = [f for f in findings if not (f in seen or seen.add(f))]

    for finding in unique:
        print(f"  secret: {finding}")

    if unique:
        print(f"\n{len(unique)} credential(s) found. Contract gate at every tier: this blocks "
              f"the merge.\nRotate the credential first — it is compromised the moment it is "
              f"pushed. Removing it\nfrom the tree does not remove it from the history.")
        return 1

    scope = "history and working tree" if args.all else (
        "history" if args.history else
        f"{len(args.paths)} named path(s)" if args.paths is not None else "working tree")
    print(f"no credentials found in the {scope}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
