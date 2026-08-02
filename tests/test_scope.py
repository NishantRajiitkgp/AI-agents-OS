#!/usr/bin/env python3
"""Tests for the declared-scope check.

Run: python3 -m unittest discover -s tests -v

M2-06's Done-when is "a diff outside declared scope fails, and the unused-scope figure is
reported". Both halves are asserted, and the first has to be asserted at a tier where the
gate is Contract — this repository is `prototype`, where scope is Advisory by design (06 §3),
so a test that only ran against the local configuration would conclude the gate never blocks.

The glob tests are the ones that would silently rot. `fnmatch` treats `*` as crossing
directory separators, so a naive implementation makes `src/*` match `src/a/b/c.py` — and a
task scoped lazily then looks precisely scoped, which is the exact failure the unused-scope
figure exists to surface.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-scope.py"

IN_SCOPE, ESCAPED, CANNOT_RUN = 0, 1, 2

TASK = textwrap.dedent("""\
    ---
    id: T-950a
    title: A task with a declared scope
    status: doing
    satisfies: [STATE-6]
    priority: 1
    risk: low
    touches:
      - src/api/**
      - docs/notes.md
    acceptance:
      - "The system shall do the thing"
    verify:
      - python3 -c "pass"
    ---

    ## Context

    Why this exists.
    """)


def diff_for(*paths: str) -> str:
    out = []
    for path in paths:
        out.append(f"diff --git a/{path} b/{path}")
        out.append(f"--- a/{path}")
        out.append(f"+++ b/{path}")
        out.append("@@ -1 +1 @@")
        out.append("-old")
        out.append("+new")
    return "\n".join(out) + "\n"


class ScopeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        (self.dir / "T-950a.md").write_text(TASK, encoding="utf-8")

    def run_check(self, diff: str, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--tasks-dir", str(self.dir), *args],
            input=diff, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr


class TestScopeEnforcement(ScopeCase):
    def test_paths_inside_declared_scope_pass(self) -> None:
        code, out = self.run_check(diff_for("src/api/search.py"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)
        self.assertIn("no paths escaped", out)

    def test_escape_blocks_at_contract_tier(self) -> None:
        code, out = self.run_check(
            diff_for("src/api/search.py", "src/billing/charge.py"),
            "--task", "T-950a", "--tier", "internal")
        self.assertEqual(code, ESCAPED, out)
        self.assertIn("src/billing/charge.py", out)
        self.assertIn("blocks the merge", out)

    def test_escape_only_reports_at_prototype_tier(self) -> None:
        """Advisory at prototype is the designed behaviour, not a bug to fix."""
        code, out = self.run_check(
            diff_for("src/billing/charge.py"), "--task", "T-950a", "--tier", "prototype")
        self.assertEqual(code, IN_SCOPE, out)
        self.assertIn("src/billing/charge.py", out)
        self.assertIn("not blocking", out)

    def test_every_contract_tier_blocks(self) -> None:
        for tier in ("internal", "production", "regulated"):
            with self.subTest(tier=tier):
                code, _ = self.run_check(
                    diff_for("src/billing/charge.py"), "--task", "T-950a", "--tier", tier)
                self.assertEqual(code, ESCAPED)

    def test_the_message_says_to_amend_the_task_file(self) -> None:
        _, out = self.run_check(diff_for("src/billing/charge.py"), "--task", "T-950a")
        self.assertIn("Amend", out)
        self.assertIn("T-950a.md", out)

    def test_a_deletion_is_still_a_write(self) -> None:
        diff = ("diff --git a/src/billing/charge.py b/src/billing/charge.py\n"
                "--- a/src/billing/charge.py\n+++ /dev/null\n@@ -1 +0,0 @@\n-gone\n")
        code, out = self.run_check(diff, "--task", "T-950a", "--tier", "internal")
        self.assertEqual(code, ESCAPED, out)

    def test_the_tasks_own_file_is_always_in_scope(self) -> None:
        """Otherwise every status transition would escape the scope it is recording."""
        code, out = self.run_check(
            diff_for("src/api/search.py", "aios/tasks/T-950a.md"),
            "--task", "T-950a", "--tier", "regulated")
        self.assertEqual(code, IN_SCOPE, out)


class TestUnusedScope(ScopeCase):
    def test_unused_scope_is_reported(self) -> None:
        code, out = self.run_check(diff_for("src/api/search.py"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)
        self.assertIn("unused scope: 1 of 2", out)
        self.assertIn("docs/notes.md", out)

    def test_fully_used_scope_reports_nothing(self) -> None:
        code, out = self.run_check(
            diff_for("src/api/search.py", "docs/notes.md"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)
        self.assertNotIn("unused scope", out)


class TestGlobSemantics(ScopeCase):
    def write_task(self, *globs: str) -> None:
        # Quoted, and it has to be: a scalar beginning with `*` is an alias node in YAML, so
        # an unquoted `**/notes.md` makes the whole task file unparseable rather than merely
        # mis-scoped. Real task files carry the same constraint.
        body = TASK.replace("  - src/api/**\n  - docs/notes.md\n",
                            "".join(f'  - "{g}"\n' for g in globs))
        (self.dir / "T-950a.md").write_text(body, encoding="utf-8")

    def test_single_star_does_not_cross_directories(self) -> None:
        """The fnmatch trap: `*` must not swallow `/`, or lazy scoping looks precise."""
        self.write_task("src/*")
        code, out = self.run_check(
            diff_for("src/a/b/c.py"), "--task", "T-950a", "--tier", "internal")
        self.assertEqual(code, ESCAPED, out)

    def test_single_star_matches_within_one_segment(self) -> None:
        self.write_task("src/*")
        code, out = self.run_check(diff_for("src/main.py"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)

    def test_double_star_crosses_directories(self) -> None:
        self.write_task("src/**")
        code, out = self.run_check(diff_for("src/a/b/c.py"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)

    def test_leading_double_star_matches_at_any_depth(self) -> None:
        self.write_task("**/notes.md")
        code, out = self.run_check(diff_for("docs/deep/notes.md"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)

    def test_leading_double_star_also_matches_at_the_root(self) -> None:
        self.write_task("**/notes.md")
        code, out = self.run_check(diff_for("notes.md"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)

    def test_a_trailing_slash_means_everything_under_it(self) -> None:
        self.write_task("src/api/")
        code, out = self.run_check(diff_for("src/api/deep/x.py"), "--task", "T-950a")
        self.assertEqual(code, IN_SCOPE, out)

    def test_an_exact_path_matches_only_itself(self) -> None:
        self.write_task("src/api/search.py")
        code, out = self.run_check(
            diff_for("src/api/search_test.py"), "--task", "T-950a", "--tier", "internal")
        self.assertEqual(code, ESCAPED, out)


class TestTaskResolution(ScopeCase):
    def test_the_branch_name_can_name_the_task(self) -> None:
        code, out = self.run_check(
            diff_for("src/api/search.py"), "--branch", "feat/T-950a-add-search")
        self.assertEqual(code, IN_SCOPE, out)

    def test_a_diff_touching_one_task_file_identifies_it(self) -> None:
        code, out = self.run_check(diff_for("src/api/search.py", "aios/tasks/T-950a.md"))
        self.assertEqual(code, IN_SCOPE, out)

    def test_an_unidentifiable_diff_refuses_rather_than_guessing(self) -> None:
        code, out = self.run_check(diff_for("src/api/search.py"))
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("cannot tell which task", out)

    def test_several_task_files_in_one_diff_is_ambiguous(self) -> None:
        (self.dir / "T-beef.md").write_text(
            TASK.replace("T-950a", "T-beef"), encoding="utf-8")
        code, out = self.run_check(
            diff_for("aios/tasks/T-950a.md", "aios/tasks/T-beef.md"))
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("ambiguous", out)

    def test_an_unknown_task_id_cannot_run(self) -> None:
        code, out = self.run_check(diff_for("src/api/search.py"), "--task", "T-0000")
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("names no task file", out)

    def test_empty_diff_is_clean(self) -> None:
        code, out = self.run_check("")
        self.assertEqual(code, IN_SCOPE, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
