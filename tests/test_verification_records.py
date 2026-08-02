#!/usr/bin/env python3
"""Tests for the verification-record re-check (M1-15) and the attacks on it (M1-17).

M1-17 names three attacks and requires all three to go red: hand-edit a task's frontmatter to
`done` without running the CLI, amend a `verify` list after the fact, and point a record at a
SHA that does not exist. Each is a test below, built as a real git repository with real
commits, because every one of them is a claim about what git can and cannot resolve and a
fixture that stubs git would be testing the stub.

The design says: if any of the three goes green, M1 is not done and the design needs rework
before M2 starts. So these are not regression tests for a fix — they are the experiment, and
the assertions are written to fail loudly rather than to be satisfiable by a narrower
implementation.

@satisfies STATE-6  malformed state is refused at the boundary — a forged or mismatched
                    verification record is refused by a reader that is not its author
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
CHECKER = SCRIPTS / "check-verification-records.py"

sys.path.insert(0, str(SCRIPTS))


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


records = load(CHECKER, "check_verification_records")


class RealRepository(unittest.TestCase):
    """A git repository with a commit, because the attacks are claims about git."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

        for part in ("aios/tasks", "aios/requirements"):
            (self.dir / part).mkdir(parents=True)
        (self.dir / "aios" / "config.yml").write_text(
            "tier: prototype\nbudgets:\n  task_file_lines: 200\n", encoding="utf-8")

        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.dir, capture_output=True, text=True)

    def commit(self, message: str = "state") -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD").stdout.strip()

    def write_task(self, task_id: str, *, status: str, verify: list[str],
                   record: str | None) -> Path:
        # Built without textwrap.dedent on purpose. dedent computes the common indent across
        # every line including the interpolated ones, so a two-space list item inside a
        # twelve-space literal leaves ten spaces on `---` and the frontmatter stops being
        # frontmatter — which the checker then reports as an unreadable file rather than as
        # the forgery the test is about.
        lines = [
            "---",
            f"id: {task_id}",
            "title: a task",
            f"status: {status}",
            "satisfies: []",
            "priority: 1",
            "risk: low",
            "touches: []",
            "acceptance:",
            '  - "When run, the system shall do the thing"',
            "verify:" if verify else "verify: []",
        ]
        lines.extend(f"  - {command}" for command in verify)
        body = "\n".join(lines) + "\n"
        if record:
            body += record
        body += "---\n\nprose\n"
        path = self.dir / "aios" / "tasks" / f"{task_id}.md"
        path.write_text(body, encoding="utf-8")
        return path

    def record_for(self, sha: str, commands: list[str], exits: list[int] | None = None) -> str:
        exits = exits or [0] * len(commands)
        lines = ["verified:", f"  sha: {sha}", "  at: 2026-08-02", "  commands:"]
        for command, code in zip(commands, exits):
            lines.append(f'    - command: "{command}"')
            lines.append(f"      exit: {code}")
        return "\n".join(lines) + "\n"

    def run_check(self, *extra: str) -> tuple[int, str]:
        out = subprocess.run(
            [sys.executable, str(CHECKER), "--root", str(self.dir), *extra],
            capture_output=True, text=True, cwd=self.dir)
        return out.returncode, out.stdout + out.stderr


class TestTheThreeAttacks(RealRepository):
    """M1-17. All three must go red."""

    def test_frontmatter_edited_to_done_without_the_cli(self) -> None:
        """Attack one: write the word `done` and skip the mechanism entirely.

        This is the attack the whole milestone exists for. Nothing about the task file looks
        wrong; the only thing missing is the evidence, which is exactly what an agent
        optimising for the appearance of completion would omit.
        """
        self.write_task("T-0001", status="done", verify=["exit 0"], record=None)
        self.commit()
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn("no verification record", output)
        self.assertIn("edited by hand", output)

    def test_verify_amended_after_the_record_was_written(self) -> None:
        """Attack two: pass a weak check, record it, then claim a strong one.

        The record is genuine and the status is genuine; what has changed is the task's claim
        about what was verified. A checker that only asked "is there a record, and is its SHA
        real" would pass this, which is why the command lists are compared.
        """
        sha = self.commit("first")
        self.write_task(
            "T-0002", status="done",
            verify=["exit 0", "the-real-and-expensive-test-suite"],
            record=self.record_for(sha, ["exit 0"]))
        self.commit("amend the claim")
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn("does not match", output)
        self.assertIn("declared but never verified", output)

    def test_a_record_pointing_at_a_commit_that_does_not_exist(self) -> None:
        """Attack three: invent the evidence.

        Forty hex characters look exactly like a commit. Only git can say otherwise, which is
        why this check asks git rather than validating the string's shape.
        """
        self.commit("first")
        self.write_task("T-0003", status="done", verify=["exit 0"],
                        record=self.record_for("a" * 40, ["exit 0"]))
        self.commit("claim")
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn("not a commit in this repository", output)


class TestTheNarrowerForgeries(RealRepository):
    """Variations that a checker built only against the three above would let through."""

    def test_a_record_naming_head_rather_than_a_commit(self) -> None:
        """`HEAD` resolves, and attests to nothing — it names a different commit tomorrow."""
        self.commit("first")
        self.write_task("T-0004", status="done", verify=["exit 0"],
                        record=self.record_for("HEAD", ["exit 0"]))
        self.commit("claim")
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn("not a commit", output)

    def test_a_record_whose_own_exit_codes_are_nonzero(self) -> None:
        """The record contradicts the status it was written to justify."""
        sha = self.commit("first")
        self.write_task("T-0005", status="done", verify=["exit 1"],
                        record=self.record_for(sha, ["exit 1"], exits=[1]))
        self.commit("claim")
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn("contradicts the status", output)

    def test_a_record_with_no_commands_at_all(self) -> None:
        sha = self.commit("first")
        self.write_task("T-0006", status="done", verify=["exit 0"],
                        record=f"verified:\n  sha: {sha}\n  at: 2026-08-02\n  commands: []\n")
        self.commit("claim")
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn("attests to nothing", output)

    def test_a_command_that_passed_then_and_fails_now(self) -> None:
        """The blameless failure, and the only one of these that is not an accusation."""
        sha = self.commit("first")
        self.write_task("T-0007", status="done", verify=["exit 3"],
                        record=self.record_for(sha, ["exit 3"]))
        self.commit("claim")
        code, output = self.run_check()
        self.assertEqual(code, 1, output)
        self.assertIn("where the record says it passed", output)


class TestTheHonestCase(RealRepository):
    def test_a_genuine_record_passes_a_rerun(self) -> None:
        sha = self.commit("first")
        self.write_task("T-0008", status="done", verify=["exit 0"],
                        record=self.record_for(sha, ["exit 0"]))
        self.commit("claim")
        code, output = self.run_check()
        self.assertEqual(code, 0, output)
        self.assertIn("every record intact", output)

    def test_a_task_that_is_not_done_is_not_asked_for_a_record(self) -> None:
        self.write_task("T-0009", status="doing", verify=["exit 0"], record=None)
        self.commit()
        code, output = self.run_check()
        self.assertEqual(code, 0, output)

    def test_an_empty_backlog_does_not_read_as_a_pass(self) -> None:
        """Zero records checked is not the same fact as every record holding.

        A summary line that says "all records valid" over an empty set is how a check earns
        trust it has not done anything to deserve.
        """
        self.commit("nothing")
        code, output = self.run_check()
        self.assertIn("not a passing grade", output)

    def test_the_rerun_does_not_disturb_the_working_tree(self) -> None:
        """A checkout in place would rewrite the tree of whoever ran this."""
        sha = self.commit("first")
        self.write_task("T-0010", status="done", verify=["exit 0"],
                        record=self.record_for(sha, ["exit 0"]))
        head = self.commit("claim")
        self.run_check()
        self.assertEqual(self.git("rev-parse", "HEAD").stdout.strip(), head)
        self.assertEqual(self.git("status", "--porcelain").stdout.strip(), "")

    def test_no_rerun_still_catches_the_three_forgeries(self) -> None:
        """The fast path may skip re-running; it may not skip the shape checks.

        Those are the three that indicate a claim was never earned, and they cost nothing.
        """
        self.commit("first")
        self.write_task("T-0011", status="done", verify=["exit 0"], record=None)
        self.commit("claim")
        code, output = self.run_check("--no-rerun")
        self.assertEqual(code, 1, output)
        self.assertIn("no verification record", output)


class TestItCannotRunRatherThanAccuse(RealRepository):
    def test_a_repository_with_no_commits_could_not_run(self) -> None:
        """Every SHA is unresolvable there, and calling that forgery is a false accusation."""
        self.write_task("T-0012", status="done", verify=["exit 0"],
                        record=self.record_for("a" * 40, ["exit 0"]))
        code, output = self.run_check()
        self.assertEqual(code, 2, output)
        self.assertIn("no commits", output)

    def test_a_missing_state_directory_could_not_run(self) -> None:
        with tempfile.TemporaryDirectory() as empty:
            out = subprocess.run(
                [sys.executable, str(CHECKER), "--root", empty],
                capture_output=True, text=True)
            self.assertEqual(out.returncode, 2, out.stdout + out.stderr)


class TestTheGateIsRegistered(unittest.TestCase):
    def test_it_runs_in_ci(self) -> None:
        gates = (ROOT / "aios" / "gates.yml").read_text(encoding="utf-8")
        self.assertIn("state.verification_records", gates)

    def test_the_commit_check_asks_git_rather_than_matching_a_shape(self) -> None:
        """Forty hex characters look exactly like a commit; only git knows."""
        source = CHECKER.read_text(encoding="utf-8")
        self.assertIn("cat-file", source)
        self.assertIn("^{commit}", source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
