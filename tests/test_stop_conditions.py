#!/usr/bin/env python3
"""Tests for the hard stop conditions (M4-06, 05 §3.3).

Run: python -m unittest discover -s tests -v

The centrepiece is the three-strikes rule: the same test failing three times without passing.
It is the only stop in 05 §3.3 that is both mechanical and not already covered elsewhere, and
the design calls it the interesting one because it fires at the moment the incentive to weaken
a test appears.

Payloads follow the measured `postToolUse` shape, including `tool_output` arriving as a JSON
*string* with the exit code nested inside it — and the exit code being the shell's rather than
the command's, which is why nothing here asserts on it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OBSERVER = ROOT / "aios" / "bin" / "hooks" / "record-attempt.py"
HOOK = ROOT / "aios" / "bin" / "hooks" / "check-mode.py"

CONFIG = """\
tier: prototype
autonomy:
  chain_limit: 3
  stop_after_failed_attempts: 3
  levels:
    - "prototype:  low=A2 medium=A2 high=A1"
    - "internal:   low=A2 medium=A1 high=A0"
    - "production: low=A1 medium=A1 high=A0"
    - "regulated:  low=A1 medium=A0 high=A0"
modes:
  implement:
    writes: touches
  plan:
    writes:
      - "aios/tasks/**"
"""

FAILING = "FAILED (failures=1)\nRan 3 tests\n"
PASSING = "Ran 3 tests in 0.1s\n\nOK\n"


class StopCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "tasks").mkdir(parents=True)
        (self.dir / "src").mkdir()
        (self.dir / "aios" / "config.yml").write_text(CONFIG, encoding="utf-8")
        (self.dir / "aios" / "tasks" / "T-0001.md").write_text(textwrap.dedent("""\
            ---
            id: T-0001
            title: A task
            status: doing
            risk: low
            touches:
              - "src/**"
            duplicate_check:
              - "the thing — nothing found; searched a, b"
            ---

            Body.
            """), encoding="utf-8")
        (self.dir / ".aios-mode").write_text("implement T-0001", encoding="utf-8")

    def observe(self, command: str, output: str, exit_code: int = 1) -> None:
        payload = {
            "tool_name": "Shell",
            "tool_input": {"command": command, "cwd": str(self.dir), "timeout": 60000},
            "tool_output": json.dumps({"output": output, "exitCode": exit_code}),
            "hook_event_name": "postToolUse",
        }
        raw = "\ufeff".encode() + json.dumps(payload).encode() + b"\r\n"
        result = subprocess.run([sys.executable, str(OBSERVER)], input=raw,
                                capture_output=True, cwd=str(self.dir),
                                env={"CURSOR_PROJECT_DIR": str(self.dir), "PATH": ""})
        self.assertEqual(result.returncode, 0, result.stderr.decode())

    def write(self) -> dict:
        payload = {"tool_name": "Write",
                   "tool_input": {"file_path": str(self.dir / "src" / "main.rs"),
                                  "content": "x"},
                   "hook_event_name": "preToolUse"}
        raw = "\ufeff".encode() + json.dumps(payload).encode() + b"\r\n"
        result = subprocess.run([sys.executable, str(HOOK)], input=raw, capture_output=True,
                                cwd=str(self.dir),
                                env={"CURSOR_PROJECT_DIR": str(self.dir), "PATH": ""})
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return json.loads(result.stdout.decode("utf-8"))

    def ledger(self) -> list[str]:
        path = self.dir / ".aios-attempts"
        return path.read_text(encoding="utf-8").split("\n") if path.is_file() else []


class TestTheObserverRecords(StopCase):
    def test_a_failing_test_run_is_recorded(self) -> None:
        self.observe("python -m unittest tests.test_thing", FAILING)
        self.assertTrue(any(line.startswith("FAIL") for line in self.ledger()))

    def test_a_passing_run_is_recorded_as_a_pass(self) -> None:
        self.observe("python -m unittest tests.test_thing", PASSING, exit_code=0)
        self.assertTrue(any(line.startswith("PASS") for line in self.ledger()))

    def test_a_non_test_command_is_ignored(self) -> None:
        """A control that fires on `git status` gets switched off, taking the control away."""
        for command in ("git status", "ls -la", "python .github/scripts/check-ratchets.py"):
            with self.subTest(command=command):
                self.observe(command, "FAILED something")
        self.assertEqual(self.ledger(), [])

    def test_output_with_no_verdict_is_not_recorded(self) -> None:
        """No verdict is not a pass, and recording a guess would corrupt the count."""
        self.observe("python -m unittest tests.test_thing", "starting up...\n")
        self.assertEqual(self.ledger(), [])

    def test_the_shell_exit_code_is_not_the_signal(self) -> None:
        """Measured: a Python process exiting 1 inside a PowerShell block reported 0. Reading
        that field would miss every failure in a wrapped command, which is most of them."""
        self.observe("python -m unittest tests.test_thing", FAILING, exit_code=0)
        self.assertTrue(any(line.startswith("FAIL") for line in self.ledger()))

    def test_different_tests_are_counted_separately(self) -> None:
        self.observe("python -m unittest tests.test_alpha", FAILING)
        self.observe("python -m unittest tests.test_beta", FAILING)
        self.observe("python -m unittest tests.test_gamma", FAILING)
        self.assertEqual(self.write()["permission"], "allow")

    def test_an_unreadable_event_records_nothing_and_blocks_nothing(self) -> None:
        result = subprocess.run([sys.executable, str(OBSERVER)], input=b"not json",
                                capture_output=True, cwd=str(self.dir),
                                env={"CURSOR_PROJECT_DIR": str(self.dir), "PATH": ""})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.ledger(), [])


class TestTheThirdStrikeStops(StopCase):
    def fail_times(self, count: int, name: str = "tests.test_thing") -> None:
        for _ in range(count):
            self.observe(f"python -m unittest {name}", FAILING)

    def test_two_failures_still_permit_a_write(self) -> None:
        self.fail_times(2)
        self.assertEqual(self.write()["permission"], "allow")

    def test_the_third_failure_stops_the_writing(self) -> None:
        self.fail_times(3)
        decision = self.write()
        self.assertEqual(decision["permission"], "deny")
        self.assertIn("failed 3 times", decision["user_message"])

    def test_a_pass_clears_the_count(self) -> None:
        """The rule is about being stuck, not about having ever failed."""
        self.fail_times(2)
        self.observe("python -m unittest tests.test_thing", PASSING, exit_code=0)
        self.fail_times(2)
        self.assertEqual(self.write()["permission"], "allow")

    def test_the_refusal_names_the_possibility_that_the_test_is_right(self) -> None:
        """The correct output here is a question, not a workaround — and the likeliest
        unexamined answer after three tries is that the task is wrong."""
        self.fail_times(3)
        message = self.write()["agent_message"]
        self.assertIn("the task is wrong", message)
        self.assertIn("weakening", message)

    def test_clearing_the_ledger_is_named_as_a_human_action(self) -> None:
        self.fail_times(3)
        self.assertIn("human", self.write()["agent_message"])

    def test_the_threshold_comes_from_config(self) -> None:
        (self.dir / "aios" / "config.yml").write_text(
            CONFIG.replace("stop_after_failed_attempts: 3",
                           "stop_after_failed_attempts: 2"), encoding="utf-8")
        self.fail_times(2)
        self.assertEqual(self.write()["permission"], "deny")


class TestThisRepository(unittest.TestCase):
    def test_the_observer_is_registered_on_the_event_that_carries_an_outcome(self) -> None:
        hooks = json.loads((ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        entries = hooks["hooks"].get("postToolUse", [])
        self.assertTrue(any("record-attempt" in entry["command"] for entry in entries))

    def test_the_observer_returns_no_decision(self) -> None:
        """postToolUse cannot deny anything. A hook that emitted a permission there would
        read like a control while enforcing nothing, which is worse than no control."""
        payload = {"tool_name": "Shell",
                   "tool_input": {"command": "python -m unittest tests.test_thing"},
                   "tool_output": json.dumps({"output": FAILING, "exitCode": 1}),
                   "hook_event_name": "postToolUse"}
        raw = "\ufeff".encode() + json.dumps(payload).encode() + b"\r\n"
        with tempfile.TemporaryDirectory() as scratch:
            result = subprocess.run([sys.executable, str(OBSERVER)], input=raw,
                                    capture_output=True, cwd=scratch,
                                    env={"CURSOR_PROJECT_DIR": scratch, "PATH": ""})
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.decode().strip(), "")

    def test_the_ledger_is_not_committed(self) -> None:
        self.assertIn(".aios-attempts", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_the_measurement_records_the_exit_code_caveat(self) -> None:
        """If this record is lost, the next person reads `exitCode` and builds on sand."""
        measured = (ROOT / "aios" / "bin" / "probe" / "results"
                    / "hook-event-2026-08-01.md").read_text(encoding="utf-8")
        self.assertIn("exit code is the shell's", measured)


if __name__ == "__main__":
    unittest.main(verbosity=2)
