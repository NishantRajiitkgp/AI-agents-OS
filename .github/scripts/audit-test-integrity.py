#!/usr/bin/env python3
"""Audit a diff for changes that weaken the tests rather than satisfy them.

PROVISIONAL. Moves into `aios check` at M1-14, per ADR-006.

Every other gate in this repository trusts the test suite. That trust is only worth
something if the suite cannot be quietly edited into agreement — the cheapest way to make a
red build green is to change what "green" means, and it looks like ordinary work in a diff.
This is the audit that makes the rest real (06 §4).

Any hit is a **Contract** failure and cannot be waived. Legitimate cases exist and are
handled by a human commit carrying a reason, which is exactly the visibility the control is
for: the point is not that these edits are forbidden, it is that they cannot be silent.

The patterns are deliberately cross-ecosystem. This repository chose Rust for itself, but a
project cloning the template has chosen nothing (D-041), so an audit that only understood
one language's idioms would be advisory in most repositories that use it.

Reads a unified diff from stdin, or from --diff <path>.
Exit codes: 0 clean, 1 violations, 2 could not run.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field

# Paths whose *content* is diff text rather than code. The audit's own fixtures contain every
# pattern it detects, so without this it fails on the pull request that introduces it.
#
# This exclusion is the audit's soft spot: anything parked under it is unaudited. It is kept
# narrow for that reason, and a separate check asserts the directory holds nothing but .diff
# files, so it cannot quietly become somewhere to hide a real edit.
FIXTURE_DIR = "tests/fixtures/test-integrity/"

TEST_PATH = re.compile(
    r"(^|/)(tests?|spec|__tests__)/|"           # a test directory at any depth
    r"(^|/)test_[^/]*$|[^/]*_test\.[^/]+$|"     # python, go, rust conventions
    r"[^/]*\.(test|spec)\.[^/]+$|"              # javascript, typescript
    r"[^/]*(Test|Tests|Spec)\.[^/]+$|"          # java, c#, kotlin
    r"[^/]*_spec\.rb$",                         # ruby
    re.IGNORECASE,
)

# A test being declared. Used to notice one disappearing.
TEST_DECL = re.compile(
    r"\bdef\s+test\w*\s*\(|"                    # python
    r"\b(it|test|describe)\s*\(|"               # javascript, ruby
    r"#\[\s*test\s*\]|"                         # rust
    r"\bfunc\s+Test\w*\s*\(|"                   # go
    r"@Test\b|\[Fact\]|\[Test\]"                # java, c#
)

SKIP_MARKER = re.compile(
    r"@pytest\.mark\.(skip|xfail)|pytest\.skip\(|@unittest\.skip|unittest\.expectedFailure|"
    r"\b(it|test|describe|context)\.(skip|only)\s*\(|\b(xit|xdescribe|xtest|fit|fdescribe)\s*\(|"
    r"@Disabled\b|@Ignore\b|\[Ignore\]|"
    r"\bt\.Skip(Now)?\s*\(|"
    r"#\[\s*ignore\s*\]|"
    r"\.skip\s*=\s*true|\bskip\s*:\s*true"
)

EXACT_ASSERT = re.compile(
    r"assertEquals?\(|assert_equals?\(|assertSame\(|assert_eq!|"
    r"\.toEqual\(|\.toBe\(|\.toStrictEqual\(|"
    r"isEqualTo\(|should\.equal|\.deepEqual\(|assertArrayEquals\("
)
TRUTHY_ASSERT = re.compile(
    r"assertTrue\(|assert_true\(|assertIsNotNone\(|assertNotNull\(|"
    r"\.toBeTruthy\(|\.toBeDefined\(|\.toBeNull\(|isNotNull\(|"
    r"\bassert!\(|\bassert\s*\(|\bok\s*\(|\.notNull\("
)

BROAD_HANDLER = re.compile(
    r"except\s*:|except\s+(BaseException|Exception)\b|"
    r"catch\s*\(\s*(Exception|Throwable|Error|RuntimeException)\b|"
    r"catch\s*\{|catch\s*\(\s*\w+\s*\)\s*\{\s*\}|"
    r"rescue\s*(=>|$)|"
    r"\.unwrap_or_default\(\)|\bok\(\)\.is_some\(\)"
)
NARROW_HANDLER = re.compile(r"except\s+\w+Error\b|catch\s*\(\s*[A-Z]\w*(Exception|Error)\b")

MOCKING = re.compile(
    r"\b(mock|patch|stub|spy|fake)\w*\s*\(|"
    r"@patch\b|jest\.mock\(|sinon\.(stub|spy)\(|Mockito\.(mock|when)\(|"
    r"unittest\.mock|MagicMock\(|createMock\("
)

TIMEOUT = re.compile(r"\btimeout\w*\b|\bsetTimeout\b|\bwait_?for\b|\bsleep\b", re.IGNORECASE)

TEST_CMD_FLAG = re.compile(
    r"--ignore(=|\s|$)|--exclude(=|\s|$)|--passWithNoTests\b|--deselect\b|"
    r"--testPathIgnorePatterns\b|--no-fail-fast\b|"
    r"-k\s+['\"]?not\s|--skip(=|\s|$)|-skip\s|--exclude-tags\b"
)

COVERAGE = re.compile(
    r"\bcoverage\b|\bfail_under\b|\bthreshold\b|\bmin(imum)?_?coverage\b|"
    r"\b(statements|branches|functions|lines)\s*[:=]",
    re.IGNORECASE,
)

SUPPRESSION = re.compile(
    r"#\s*noqa|#\s*type:\s*ignore|#\s*pylint:\s*disable|#\s*mypy:\s*ignore|"
    r"eslint-disable|@ts-ignore|@ts-expect-error|"
    r"#\[\s*allow\(|@SuppressWarnings|//\s*nolint|#pragma\s+warning\s+disable|"
    r"//\s*@ts-nocheck|--\s*noqa"
)

NUMBER = re.compile(r"\d+(?:\.\d+)?")


@dataclass
class FileDiff:
    path: str
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    is_deletion: bool = False

    @property
    def is_test(self) -> bool:
        return bool(TEST_PATH.search(self.path))


def parse_diff(text: str) -> list[FileDiff]:
    """Parse a unified diff. Only the added and removed lines per file are needed."""
    files: list[FileDiff] = []
    current: FileDiff | None = None

    for line in text.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" b/", 1)
            current = FileDiff(path=parts[1].strip() if len(parts) == 2 else "")
            files.append(current)
        elif line.startswith("+++ "):
            target = line[4:].strip()
            if current is None:
                current = FileDiff(path="")
                files.append(current)
            if target == "/dev/null":
                current.is_deletion = True
            elif not current.path:
                current.path = target[2:] if target.startswith("b/") else target
        elif current is None or line.startswith(("--- ", "@@", "index ", "new file", "old mode",
                                                 "new mode", "deleted file", "similarity",
                                                 "rename ", "Binary files")):
            continue
        elif line.startswith("+"):
            current.added.append(line[1:])
        elif line.startswith("-"):
            current.removed.append(line[1:])

    return [f for f in files if f.path and not f.path.startswith(FIXTURE_DIR)]


def max_number(line: str) -> float | None:
    found = NUMBER.findall(line)
    return max(float(n) for n in found) if found else None


def audit(files: list[FileDiff]) -> list[str]:
    violations: list[str] = []

    def flag(path: str, pattern: str, detail: str) -> None:
        violations.append(f"{path}: [{pattern}] {detail}")

    for f in files:
        added_test_lines = [l for l in f.added if l.strip()]

        if f.is_test:
            for line in added_test_lines:
                if SKIP_MARKER.search(line):
                    flag(f.path, "skip-marker", f"a test was disabled: {line.strip()[:70]}")

            if any(EXACT_ASSERT.search(l) for l in f.removed) and \
               any(TRUTHY_ASSERT.search(l) and not EXACT_ASSERT.search(l) for l in f.added):
                flag(f.path, "weakened-assertion",
                     "an exact assertion was replaced by a truthy one")

            broadened = [l for l in f.added if BROAD_HANDLER.search(l)]
            if broadened and any(NARROW_HANDLER.search(l) for l in f.removed):
                flag(f.path, "broadened-handler",
                     f"a narrow handler was widened: {broadened[0].strip()[:70]}")
            elif broadened and any(EXACT_ASSERT.search(l) or TRUTHY_ASSERT.search(l)
                                   for l in f.removed):
                flag(f.path, "broadened-handler",
                     f"an assertion was replaced by a catch-all: {broadened[0].strip()[:70]}")

            if any(MOCKING.search(l) for l in f.added) and \
               any(EXACT_ASSERT.search(l) or TRUTHY_ASSERT.search(l) for l in f.removed):
                flag(f.path, "mocked-subject",
                     "a mock was introduced where an assertion was removed")

            if not f.is_deletion:
                gone = sum(1 for l in f.removed if TEST_DECL.search(l))
                kept = sum(1 for l in f.added if TEST_DECL.search(l))
                if gone > kept:
                    flag(f.path, "deleted-test",
                         f"{gone - kept} test declaration(s) removed while the file remains")

            for line in f.added:
                if not TIMEOUT.search(line):
                    continue
                new = max_number(line)
                if new is None:
                    continue
                for old_line in f.removed:
                    if not TIMEOUT.search(old_line):
                        continue
                    old = max_number(old_line)
                    if old is not None and new > old:
                        flag(f.path, "raised-timeout",
                             f"timeout raised from {old:g} to {new:g}")
                        break

        for line in f.added:
            if TEST_CMD_FLAG.search(line):
                flag(f.path, "test-command-flag",
                     f"a flag that skips tests was added: {line.strip()[:70]}")
            if SUPPRESSION.search(line):
                flag(f.path, "new-suppression",
                     f"a suppression was added: {line.strip()[:70]}")

        for line in f.added:
            if not COVERAGE.search(line):
                continue
            new = max_number(line)
            if new is None:
                continue
            for old_line in f.removed:
                if not COVERAGE.search(old_line):
                    continue
                old = max_number(old_line)
                if old is not None and new < old:
                    flag(f.path, "lowered-coverage",
                         f"coverage threshold lowered from {old:g} to {new:g}")
                    break

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diff", help="read the diff from this file instead of stdin")
    args = parser.parse_args()

    try:
        text = (open(args.diff, encoding="utf-8").read() if args.diff
                else sys.stdin.read())
    except OSError as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    if not text.strip():
        print("empty diff, nothing to audit.")
        return 0

    violations = audit(parse_diff(text))
    for violation in violations:
        print(f"  violation: {violation}")

    if violations:
        print(f"\n{len(violations)} test-integrity violation(s). This is a Contract gate and "
              f"cannot be waived.\nIf the change is legitimate, it needs a human commit "
              f"carrying the reason.")
        return 1

    print("no test-integrity violations.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
