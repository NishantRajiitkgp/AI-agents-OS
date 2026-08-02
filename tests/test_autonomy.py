#!/usr/bin/env python3
"""Tests for autonomy tiers (M4-05, D-025).

Run: python -m unittest discover -s tests -v

Two halves, and they are tested separately on purpose. The table is data checked in CI, where
a pull request can fail on it. The chain limit is enforced by the hook, on a machine nobody
else can see, and is Advisory by classification (ADR-012).
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
SCRIPT = ROOT / ".github" / "scripts" / "check-autonomy.py"
HOOK = ROOT / "aios" / "bin" / "hooks" / "check-mode.py"

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2

GOOD_TABLE = """\
tier: prototype
paths:
  state_dir: aios
autonomy:
  chain_limit: 3
  levels:
    - "prototype:  low=A2 medium=A2 high=A1"
    - "internal:   low=A2 medium=A1 high=A0"
    - "production: low=A1 medium=A1 high=A0"
    - "regulated:  low=A1 medium=A0 high=A0"
modes:
  explore:
    writes: []
  plan:
    writes:
      - "aios/tasks/**"
  implement:
    writes: touches
  verify:
    writes: []
"""


def run(*args: str) -> tuple[int, str]:
    result = subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True)
    return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")


class TableCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def table(self, text: str) -> str:
        path = self.dir / "config.yml"
        path.write_text(text, encoding="utf-8")
        return str(path)

    def check(self, text: str) -> tuple[int, str]:
        return run("--config", self.table(text))


class TestTheTableIsChecked(TableCase):
    def test_the_shipped_table_passes(self) -> None:
        code, out = run()
        self.assertEqual(code, PASS, out)
        self.assertIn("12 cells", out)

    def test_the_design_table_is_transcribed_faithfully(self) -> None:
        """05 §4, cell by cell. Transcription is exactly the kind of thing that goes wrong
        quietly, and this table decides how much merges without a human."""
        expected = {
            ("prototype", "low"): "A2", ("prototype", "medium"): "A2",
            ("prototype", "high"): "A1",
            ("internal", "low"): "A2", ("internal", "medium"): "A1",
            ("internal", "high"): "A0",
            ("production", "low"): "A1", ("production", "medium"): "A1",
            ("production", "high"): "A0",
            ("regulated", "low"): "A1", ("regulated", "medium"): "A0",
            ("regulated", "high"): "A0",
        }
        module = load_script()
        import yaml
        config = yaml.safe_load((ROOT / "aios" / "config.yml").read_text(encoding="utf-8"))
        table, problems = module.parse_table(config["autonomy"]["levels"])
        self.assertEqual(problems, [])
        self.assertEqual(table, expected)

    def test_high_risk_reaching_a2_is_rejected(self) -> None:
        """The invariant, asserted apart from the numbers so the table cannot repeal it."""
        text = GOOD_TABLE.replace("prototype:  low=A2 medium=A2 high=A1",
                                  "prototype:  low=A2 medium=A2 high=A2")
        code, out = self.check(text)
        self.assertEqual(code, FAIL, out)
        self.assertIn("never reaches A2", out)

    def test_a_missing_cell_is_rejected(self) -> None:
        """A missing cell resolves by a default, and a default here is unwritten policy."""
        text = GOOD_TABLE.replace('    - "regulated:  low=A1 medium=A0 high=A0"\n', "")
        code, out = self.check(text)
        self.assertEqual(code, FAIL, out)
        self.assertIn("no level for regulated", out)

    def test_autonomy_may_not_loosen_as_risk_rises(self) -> None:
        text = GOOD_TABLE.replace("production: low=A1 medium=A1 high=A0",
                                  "production: low=A0 medium=A1 high=A0")
        code, out = self.check(text)
        self.assertEqual(code, FAIL, out)
        self.assertIn("tighten as risk rises", out)

    def test_autonomy_may_not_loosen_as_the_tier_rises(self) -> None:
        text = GOOD_TABLE.replace("regulated:  low=A1 medium=A0 high=A0",
                                  "regulated:  low=A2 medium=A0 high=A0")
        code, out = self.check(text)
        self.assertEqual(code, FAIL, out)
        self.assertIn("tighten as the tier rises", out)

    def test_a_malformed_row_is_rejected_rather_than_skipped(self) -> None:
        text = GOOD_TABLE.replace("prototype:  low=A2 medium=A2 high=A1", "prototype: A2")
        code, out = self.check(text)
        self.assertEqual(code, FAIL, out)

    def test_a_malformed_row_is_reported_even_when_the_table_is_complete(self) -> None:
        """The row above also removes a cell, so the missing-cell check would catch it and
        the malformed-row check could be deleted unnoticed. This one adds an unparseable row
        to an otherwise complete table, so only reporting it can fail."""
        text = GOOD_TABLE.replace('    - "regulated:  low=A1 medium=A0 high=A0"',
                                  '    - "regulated:  low=A1 medium=A0 high=A0"\n'
                                  '    - "nonsense"')
        code, out = self.check(text)
        self.assertEqual(code, FAIL, out)
        self.assertIn("nonsense", out)

    def test_an_unknown_level_is_rejected(self) -> None:
        text = GOOD_TABLE.replace("high=A1", "high=A9")
        code, out = self.check(text)
        self.assertEqual(code, FAIL, out)

    def test_a_chain_limit_below_one_is_rejected(self) -> None:
        code, out = self.check(GOOD_TABLE.replace("chain_limit: 3", "chain_limit: 0"))
        self.assertEqual(code, FAIL, out)

    def test_a_missing_config_cannot_run_rather_than_fail(self) -> None:
        """Exit 2 is 'could not run', which is not the same as 'the table is wrong'."""
        code, _ = run("--config", str(self.dir / "absent.yml"))
        self.assertEqual(code, COULD_NOT_RUN)


def load_script():
    import importlib.util
    sys.path.insert(0, str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("check_autonomy", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestChainLimitsPerLevel(unittest.TestCase):
    def test_a0_permits_nothing_without_approval(self) -> None:
        """Zero, not one: the approval is what permits the first task."""
        self.assertEqual(load_script().chain_limit("A0", 3), 0)

    def test_an_approved_a0_permits_one_task_not_a_chain(self) -> None:
        """Approval permits a task. The diff review is A0's second checkpoint, so it stops
        in the same place A1 does."""
        self.assertEqual(load_script().chain_limit("A0", 3, approved=True), 1)

    def test_a1_is_one_task_then_stop(self) -> None:
        self.assertEqual(load_script().chain_limit("A1", 3), 1)

    def test_a2_uses_the_configured_limit(self) -> None:
        self.assertEqual(load_script().chain_limit("A2", 3), 3)


def event(tool_name: str, **tool_input) -> bytes:
    payload = {"tool_name": tool_name, "tool_input": tool_input,
               "hook_event_name": "preToolUse"}
    return "\ufeff".encode() + json.dumps(payload).encode() + b"\r\n"


class TestTheChainIsEnforced(unittest.TestCase):
    """The hook half. Advisory by classification; what blocks a merge is the CI table."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "tasks").mkdir(parents=True)
        (self.dir / "src").mkdir()
        (self.dir / "aios" / "config.yml").write_text(GOOD_TABLE, encoding="utf-8")

    def config(self, tier: str) -> None:
        (self.dir / "aios" / "config.yml").write_text(
            GOOD_TABLE.replace("tier: prototype", f"tier: {tier}"), encoding="utf-8")

    def task(self, task_id: str, risk: str = "low") -> None:
        (self.dir / "aios" / "tasks" / f"{task_id}.md").write_text(textwrap.dedent(f"""\
            ---
            id: {task_id}
            title: A task
            status: doing
            risk: {risk}
            touches:
              - "src/**"
            duplicate_check:
              - "the thing — nothing found; searched a, b"
            ---

            Body.
            """), encoding="utf-8")

    def write(self, task_id: str, name: str = "main.rs") -> dict:
        (self.dir / ".aios-mode").write_text(f"implement {task_id}", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=event("Write", file_path=str(self.dir / "src" / name), content="x"),
            capture_output=True, cwd=str(self.dir),
            env={"CURSOR_PROJECT_DIR": str(self.dir), "PATH": ""})
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return json.loads(result.stdout.decode("utf-8"))

    def test_a2_chains_to_the_limit_then_stops(self) -> None:
        for index in range(3):
            self.task(f"T-000{index}")
            self.assertEqual(self.write(f"T-000{index}")["permission"], "allow",
                             f"task {index + 1} of 3 should be permitted")
        self.task("T-0003")
        decision = self.write("T-0003")
        self.assertEqual(decision["permission"], "deny")
        self.assertIn("task 4", decision["agent_message"])

    def test_a1_stops_after_one(self) -> None:
        self.config("production")
        self.task("T-0001")
        self.assertEqual(self.write("T-0001")["permission"], "allow")
        self.task("T-0002")
        self.assertEqual(self.write("T-0002")["permission"], "deny")

    def test_the_same_task_is_never_re_refused(self) -> None:
        """Otherwise the limit counts writes, and the review surface it protects is tasks."""
        self.config("production")
        self.task("T-0001")
        for _ in range(4):
            self.assertEqual(self.write("T-0001")["permission"], "allow")

    def test_high_risk_at_prototype_is_a1_not_a2(self) -> None:
        self.task("T-0001", risk="high")
        self.assertEqual(self.write("T-0001")["permission"], "allow")
        self.task("T-0002", risk="high")
        self.assertEqual(self.write("T-0002")["permission"], "deny")

    def test_a0_refuses_until_a_human_approves(self) -> None:
        self.config("regulated")
        self.task("T-0001", risk="high")
        decision = self.write("T-0001")
        self.assertEqual(decision["permission"], "deny")
        self.assertIn("approves the approach", decision["user_message"])

    def test_a0_proceeds_once_approved(self) -> None:
        self.config("regulated")
        self.task("T-0001", risk="high")
        (self.dir / ".aios-approval").write_text("T-0001\n", encoding="utf-8")
        self.assertEqual(self.write("T-0001")["permission"], "allow")

    def test_approving_one_a0_task_does_not_approve_the_next(self) -> None:
        """Approval permits a task, not a chain — otherwise the strictest level would be the
        easiest to turn into unbounded autonomy."""
        self.config("regulated")
        self.task("T-0001", risk="high")
        (self.dir / ".aios-approval").write_text("T-0001\n", encoding="utf-8")
        self.assertEqual(self.write("T-0001")["permission"], "allow")
        self.task("T-0002", risk="high")
        self.assertEqual(self.write("T-0002")["permission"], "deny")

    def test_an_unknown_tier_gets_the_default_not_more(self) -> None:
        """A pairing the table does not cover must not resolve to the loosest level."""
        self.config("experimental")
        self.task("T-0001")
        self.assertEqual(self.write("T-0001")["permission"], "allow")
        self.task("T-0002")
        self.assertEqual(self.write("T-0002")["permission"], "deny")

    def test_the_refusal_says_how_to_resume(self) -> None:
        self.config("production")
        self.task("T-0001")
        self.write("T-0001")
        self.task("T-0002")
        message = self.write("T-0002")["agent_message"]
        self.assertIn(".aios-session", message)
        self.assertIn("human", message)


class TestThisRepository(unittest.TestCase):
    def test_the_session_files_are_not_committed(self) -> None:
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".aios-session", ignored)
        self.assertIn(".aios-approval", ignored)

    def test_the_gate_is_registered(self) -> None:
        import yaml
        gates = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        found = [g for g in gates["gates"] if g["id"] == "state.autonomy_table"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["class"], "contract")


if __name__ == "__main__":
    unittest.main(verbosity=2)
