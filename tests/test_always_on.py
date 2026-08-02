#!/usr/bin/env python3
"""Tests for the always-on context measurement and the explorer subagent.

Run: python -m unittest discover -s tests -v

The measurement had drifted into two implementations — shell in the workflow, Python in the
ratchet — which agreed on the total right up until the first subagent existed, because only
one of them counted descriptions. Most of what is here is about that class of failure: the
set being measured, not the threshold being compared against.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-always-on.py"
RATCHETS = ROOT / ".github" / "scripts" / "check-ratchets.py"
EXPLORER = ROOT / ".claude" / "agents" / "explorer.md"

WITHIN, OVER, CANNOT_RUN = 0, 1, 2

CONFIG = """\
tier: prototype
budgets:
  always_on_lines: 200
  agents_md_lines: 150
"""


def load(path: Path):
    # The gate scripts import each other by plain name, so their directory has to be
    # importable before one of them is loaded out of context like this.
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


always_on = load(SCRIPT)


class MeasurementCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir(parents=True)
        (self.dir / "aios" / "config.yml").write_text(CONFIG, encoding="utf-8")
        (self.dir / "AGENTS.md").write_text("line\n" * 10, encoding="utf-8")

    def rule(self, name: str, always: bool, body_lines: int) -> None:
        rules = self.dir / ".cursor" / "rules"
        rules.mkdir(parents=True, exist_ok=True)
        frontmatter = f"---\nalwaysApply: {'true' if always else 'false'}\n---\n"
        (rules / name).write_text(frontmatter + "x\n" * body_lines, encoding="utf-8")

    def subagent(self, name: str, description: str, body_lines: int = 40) -> None:
        agents = self.dir / ".claude" / "agents"
        agents.mkdir(parents=True, exist_ok=True)
        (agents / name).write_text(
            f"---\nname: {name.removesuffix('.md')}\ndescription: {description}\n"
            f"tools: Read, Grep, Glob\n---\n" + "body\n" * body_lines, encoding="utf-8")

    def skill(self, name: str, description: str, body_lines: int = 40) -> None:
        skill = self.dir / ".claude" / "skills" / name
        skill.mkdir(parents=True, exist_ok=True)
        (skill / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n" + "body\n" * body_lines,
            encoding="utf-8")

    def run_script(self) -> tuple[int, str]:
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(self.dir)],
                                capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout + result.stderr


class TestTheSetBeingMeasured(MeasurementCase):
    """ADR-010 names four contributors. Missing one is how a budget becomes decoration."""

    def test_agents_md_counts(self) -> None:
        self.assertEqual(always_on.measure(self.dir), 10)

    def test_an_always_apply_rule_counts(self) -> None:
        self.rule("scoped.mdc", always=True, body_lines=7)
        self.assertEqual(always_on.measure(self.dir), 10 + 10)

    def test_a_glob_scoped_rule_does_not_count(self) -> None:
        """Glob rules attach when a matching path is worked, so they cost nothing at rest."""
        self.rule("scoped.mdc", always=False, body_lines=7)
        self.assertEqual(always_on.measure(self.dir), 10)

    def test_a_subagent_description_counts(self) -> None:
        """The regression this file exists for: descriptions used to measure as zero."""
        self.subagent("explorer.md", "One line of description.")
        self.assertEqual(always_on.measure(self.dir), 11)

    def test_a_skill_description_counts(self) -> None:
        self.skill("automate", "One line of description.")
        self.assertEqual(always_on.measure(self.dir), 11)

    def test_a_subagent_body_does_not_count(self) -> None:
        """A body loads on invocation. Charging for it would price subagents out entirely."""
        self.subagent("explorer.md", "One line.", body_lines=500)
        self.assertEqual(always_on.measure(self.dir), 11)

    def test_a_multi_line_description_counts_every_line(self) -> None:
        agents = self.dir / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "explorer.md").write_text(
            "---\nname: explorer\ndescription: >-\n  first\n  second\n  third\n"
            "tools: Read\n---\nbody\n", encoding="utf-8")
        self.assertEqual(always_on.measure(self.dir), 10 + 4)

    def test_a_following_field_ends_the_description(self) -> None:
        agents = self.dir / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "explorer.md").write_text(
            "---\ndescription: one\ntools: Read\nmodel: inherit\n---\nbody\n",
            encoding="utf-8")
        self.assertEqual(always_on.measure(self.dir), 11)

    def test_everything_is_summed_together(self) -> None:
        self.rule("a.mdc", always=True, body_lines=5)
        self.subagent("explorer.md", "One line.")
        self.skill("automate", "One line.")
        self.assertEqual(always_on.measure(self.dir), 10 + 8 + 1 + 1)


class TestTheBudget(MeasurementCase):
    def test_within_budget_passes(self) -> None:
        code, out = self.run_script()
        self.assertEqual(code, WITHIN, out)
        self.assertIn("ALWAYS-ON TOTAL", out)

    def test_over_the_total_fails(self) -> None:
        (self.dir / "AGENTS.md").write_text("x\n" * 120, encoding="utf-8")
        self.rule("big.mdc", always=True, body_lines=120)
        code, out = self.run_script()
        self.assertEqual(code, OVER, out)
        self.assertIn("Always-on context is", out)

    def test_over_the_agents_sub_budget_fails(self) -> None:
        (self.dir / "AGENTS.md").write_text("x\n" * 160, encoding="utf-8")
        code, out = self.run_script()
        self.assertEqual(code, OVER, out)
        self.assertIn("sub-budget", out)

    def test_a_subagent_can_push_the_total_over(self) -> None:
        """The whole point of counting descriptions: they have to be able to blow the budget.

        Sat exactly on the 200-line total, and under the AGENTS.md sub-budget, so the only
        thing that can move the verdict is the description.
        """
        (self.dir / "AGENTS.md").write_text("x\n" * 150, encoding="utf-8")
        self.rule("filler.mdc", always=True, body_lines=47)
        within, _ = self.run_script()
        self.subagent("explorer.md", "One line.")
        over, out = self.run_script()
        self.assertEqual((within, over), (WITHIN, OVER), out)

    def test_a_missing_agents_file_cannot_run(self) -> None:
        (self.dir / "AGENTS.md").unlink()
        code, out = self.run_script()
        self.assertEqual(code, CANNOT_RUN, out)

    def test_a_missing_budget_cannot_run(self) -> None:
        (self.dir / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        code, out = self.run_script()
        self.assertEqual(code, CANNOT_RUN, out)


class TestOneDefinition(MeasurementCase):
    """The drift that caused this: two implementations of one set."""

    def test_the_ratchet_uses_the_same_measurement(self) -> None:
        self.subagent("explorer.md", "One line of description.")
        (self.dir / "aios" / "ratchets.yml").write_text(yaml.safe_dump(
            {"ratchets": [{"id": "always_on_lines", "direction": "lower_is_better",
                           "baseline": always_on.measure(self.dir)}]}), encoding="utf-8")
        result = subprocess.run([sys.executable, str(RATCHETS), "--root", str(self.dir)],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("held", result.stdout)

    def test_the_workflow_calls_the_script_rather_than_restating_it(self) -> None:
        document = yaml.safe_load((ROOT / ".github" / "workflows" / "hygiene.yml")
                                  .read_text(encoding="utf-8"))
        steps = [s for job in document["jobs"].values() for s in job["steps"]]
        step = [s for s in steps if s.get("name") == "Always-on context is within budget"][0]
        self.assertIn("check-always-on.py", step["run"])
        self.assertNotIn("wc -l", step["run"],
                         "counting here again is how the two copies diverged")


class TestThisRepository(unittest.TestCase):
    """Properties of the subagents themselves live in test_subagents.py; this is the budget."""

    def test_this_repository_is_within_budget(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT,
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, WITHIN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
