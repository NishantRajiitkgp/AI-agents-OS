#!/usr/bin/env python3
"""Tests for the test-integrity diff audit.

Run: python3 -m unittest discover -s tests -v

M2-05's Done-when is "each pattern has a fixture diff that trips it and one that does not",
so that is literally what these assert, driven off the fixture tree rather than a hardcoded
list. Two of the tests are reflexive and matter more than the per-pattern ones: a new pattern
added to the audit without fixtures fails, and a fixture directory with no matching pattern
fails. Without those, the suite would keep passing while the audit grew unproven checks.

The paired trips/passes structure is the point. A detector that fires on everything satisfies
"trips" trivially, and this gate is a Contract that cannot be waived, so a false positive is
not a nuisance — it is an unmergeable pull request with no escape hatch.
"""

from __future__ import annotations

import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / ".github" / "scripts" / "audit-test-integrity.py"
FIXTURES = ROOT / "tests" / "fixtures" / "test-integrity"

CLEAN, VIOLATIONS = 0, 1


def run_audit(*args: str, stdin: str | None = None) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(AUDIT), *args],
        input=stdin, capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


def declared_patterns() -> set[str]:
    """The pattern names the audit can actually emit, read from its own source."""
    source = AUDIT.read_text(encoding="utf-8")
    return set(re.findall(r'flag\(\s*f\.path,\s*"([a-z-]+)"', source))


def fixture_dirs() -> list[Path]:
    return sorted(p for p in FIXTURES.iterdir() if p.is_dir())


class TestFixtureCoverage(unittest.TestCase):
    def test_every_pattern_the_audit_emits_has_fixtures(self) -> None:
        missing = declared_patterns() - {d.name for d in fixture_dirs()}
        self.assertEqual(missing, set(), f"patterns with no fixture directory: {missing}")

    def test_every_fixture_directory_matches_a_real_pattern(self) -> None:
        orphans = {d.name for d in fixture_dirs()} - declared_patterns()
        self.assertEqual(orphans, set(), f"fixtures for patterns that do not exist: {orphans}")

    def test_every_fixture_directory_has_both_halves(self) -> None:
        for directory in fixture_dirs():
            for half in ("trips.diff", "passes.diff"):
                self.assertTrue((directory / half).is_file(),
                                f"{directory.name} is missing {half}")

    def test_the_fixture_tree_holds_nothing_but_diffs(self) -> None:
        """The audit skips this directory, so anything else parked here would be unaudited."""
        strays = [p.relative_to(FIXTURES).as_posix()
                  for p in FIXTURES.rglob("*") if p.is_file() and p.suffix != ".diff"]
        self.assertEqual(strays, [], f"non-diff files inside the audit's blind spot: {strays}")


class TestEachPattern(unittest.TestCase):
    """Generated per fixture directory below, so adding a pattern adds its tests."""


def _make_case(directory: Path):
    def trips(self: unittest.TestCase) -> None:
        code, out = run_audit("--diff", str(directory / "trips.diff"))
        self.assertEqual(code, VIOLATIONS, f"expected a violation, got exit {code}\n{out}")
        self.assertIn(f"[{directory.name}]", out,
                      f"tripped, but not on {directory.name}\n{out}")

    def passes(self: unittest.TestCase) -> None:
        code, out = run_audit("--diff", str(directory / "passes.diff"))
        self.assertEqual(code, CLEAN, f"expected clean, got exit {code}\n{out}")

    return trips, passes


for _directory in fixture_dirs():
    _trips, _passes = _make_case(_directory)
    _name = _directory.name.replace("-", "_")
    _trips.__doc__ = f"{_directory.name}: the weakening diff is caught"
    _passes.__doc__ = f"{_directory.name}: the legitimate diff is not"
    setattr(TestEachPattern, f"test_{_name}_trips", _trips)
    setattr(TestEachPattern, f"test_{_name}_does_not_false_positive", _passes)


class TestAuditBehaviour(unittest.TestCase):
    def test_empty_diff_is_clean(self) -> None:
        code, out = run_audit(stdin="")
        self.assertEqual(code, CLEAN, out)

    def test_reads_from_stdin(self) -> None:
        diff = (FIXTURES / "skip-marker" / "trips.diff").read_text(encoding="utf-8")
        code, out = run_audit(stdin=diff)
        self.assertEqual(code, VIOLATIONS, out)
        self.assertIn("[skip-marker]", out)

    def test_missing_diff_file_cannot_run(self) -> None:
        code, out = run_audit("--diff", str(ROOT / "does-not-exist.diff"))
        self.assertEqual(code, 2, out)

    def test_changes_to_the_fixture_tree_itself_are_skipped(self) -> None:
        """Otherwise the audit fails on the pull request that introduces it."""
        diff = (
            "diff --git a/tests/fixtures/test-integrity/skip-marker/trips.diff "
            "b/tests/fixtures/test-integrity/skip-marker/trips.diff\n"
            "--- a/tests/fixtures/test-integrity/skip-marker/trips.diff\n"
            "+++ b/tests/fixtures/test-integrity/skip-marker/trips.diff\n"
            "@@ -1,2 +1,3 @@\n"
            '+@pytest.mark.skip(reason="flaky on CI")\n'
        )
        code, out = run_audit(stdin=diff)
        self.assertEqual(code, CLEAN, out)

    def test_a_real_test_file_is_still_audited(self) -> None:
        """The counterpart to the exclusion: it must be narrow, not a general escape."""
        diff = (
            "diff --git a/tests/fixtures/helpers.py b/tests/fixtures/helpers.py\n"
            "--- a/tests/fixtures/helpers.py\n"
            "+++ b/tests/fixtures/helpers.py\n"
            "@@ -1,2 +1,3 @@\n"
            '+@pytest.mark.skip(reason="flaky on CI")\n'
        )
        code, out = run_audit(stdin=diff)
        self.assertEqual(code, VIOLATIONS, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
