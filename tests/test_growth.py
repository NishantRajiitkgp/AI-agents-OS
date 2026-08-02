#!/usr/bin/env python3
"""Tests for the always-on growth ratchet (M5-02).

Run: python -m unittest discover -s tests -v

Every test here builds a real repository and makes real commits. The check reads git history
precisely because history is the one input the change under review cannot edit, so testing it
against a stand-in would test the part that does not matter.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-growth.py"

HELD, GREW, COULD_NOT_RUN = 0, 1, 2

CONFIG = """\
tier: prototype
budgets:
  always_on_lines: 200
  agents_md_lines: 150
  growth_window_commits: 20
"""

RULE = """\
---
alwaysApply: true
---

A rule.
"""


class GrowthCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir()
        (self.dir / "aios" / "config.yml").write_text(CONFIG, encoding="utf-8")
        self.git("init", "-b", "main")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")

    def git(self, *args: str) -> str:
        result = subprocess.run(["git", "-C", str(self.dir), *args], capture_output=True)
        self.assertEqual(result.returncode, 0,
                         result.stderr.decode("utf-8", "replace"))
        return result.stdout.decode("utf-8", "replace")

    def agents(self, lines: int) -> None:
        (self.dir / "AGENTS.md").write_text("\n".join(f"line {n}" for n in range(lines)) + "\n",
                                            encoding="utf-8")

    def commit(self, message: str = "a change") -> None:
        self.git("add", "-A")
        self.git("commit", "-m", message, "--no-verify")

    def run_check(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.dir), *extra],
            capture_output=True)
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")


class TestTheRatchetDirection(GrowthCase):
    def test_unchanged_holds(self) -> None:
        self.agents(50)
        self.commit()
        code, out = self.run_check()
        self.assertEqual(code, HELD, out)
        self.assertIn("held", out)

    def test_shrinking_holds(self) -> None:
        self.agents(50)
        self.commit()
        self.agents(30)
        code, out = self.run_check()
        self.assertEqual(code, HELD, out)
        self.assertIn("down 20", out)

    def test_growing_fails(self) -> None:
        self.agents(50)
        self.commit()
        self.agents(60)
        code, out = self.run_check()
        self.assertEqual(code, GREW, out)
        self.assertIn("grew by 10", out)

    def test_growth_is_measured_against_the_window_not_the_last_commit(self) -> None:
        """The check a stored baseline cannot make. Growing one line per commit passes every
        adjacent comparison and is exactly the drift this exists to catch."""
        self.agents(50)
        self.commit()
        for size in range(51, 56):
            self.agents(size)
            self.commit()
        code, out = self.run_check()
        self.assertEqual(code, GREW, out)
        self.assertIn("grew by 5", out)

    def test_growth_inside_the_window_that_is_undone_holds(self) -> None:
        """A rule added and removed again nets to zero, which is why the window is a window
        and not a high-water mark. Penalising the round trip would discourage the deletion."""
        self.agents(50)
        self.commit()
        self.agents(90)
        self.commit()
        self.agents(50)
        self.commit()
        self.assertEqual(self.run_check()[0], HELD)


class TestGrowthIsPossibleButRecorded(GrowthCase):
    def test_a_trailer_with_a_reason_permits_growth(self) -> None:
        self.agents(50)
        self.commit()
        self.agents(70)
        self.commit("Add a rule\n\nGrow-context: the injection defence has to be resident, "
                    "and it displaces nothing")
        code, out = self.run_check()
        self.assertEqual(code, HELD, out)
        self.assertIn("permitted by", out)

    def test_a_thin_reason_does_not(self) -> None:
        """A trailer that says nothing is the form of a justification without the substance,
        and it is the shape an escape hatch decays into if the length is not checked."""
        self.agents(50)
        self.commit()
        self.agents(70)
        self.commit("Add a rule\n\nGrow-context: needed")
        self.assertEqual(self.run_check()[0], GREW)

    def test_the_trailer_does_not_permit_growth_forever(self) -> None:
        """Once the trailer falls out of the window, the raised level is the new baseline and
        the next increase needs its own reason."""
        self.agents(50)
        self.commit()
        self.agents(70)
        self.commit("Grow it\n\nGrow-context: a genuine reason, stated at some length")
        self.assertEqual(self.run_check("--window", "1")[0], HELD)
        self.agents(80)
        self.commit()
        code, out = self.run_check("--window", "1")
        self.assertEqual(code, GREW, out)


class TestTheWholeSetIsWatched(GrowthCase):
    def test_a_rule_added_after_the_baseline_counts_as_growth(self) -> None:
        """AGENTS.md is the file everyone watches. The budget is over four contributors, and
        a rule file is the easy place to put what will not fit in the one being watched."""
        self.agents(50)
        self.commit()
        (self.dir / ".cursor" / "rules").mkdir(parents=True)
        (self.dir / ".cursor" / "rules" / "new.mdc").write_text(RULE, encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, GREW, out)
        self.assertIn("added:", out)

    def test_a_rule_that_does_not_always_apply_is_not_counted(self) -> None:
        self.agents(50)
        self.commit()
        (self.dir / ".cursor" / "rules").mkdir(parents=True)
        (self.dir / ".cursor" / "rules" / "scoped.mdc").write_text(
            RULE.replace("alwaysApply: true", "globs: '*.py'"), encoding="utf-8")
        self.assertEqual(self.run_check()[0], HELD)

    def test_deletions_and_additions_are_both_reported(self) -> None:
        """M5 asks whether this system can shrink, and the only honest answer is a count of
        deletions next to a count of additions."""
        self.agents(50)
        (self.dir / ".cursor" / "rules").mkdir(parents=True)
        (self.dir / ".cursor" / "rules" / "old.mdc").write_text(RULE, encoding="utf-8")
        self.commit()
        (self.dir / ".cursor" / "rules" / "old.mdc").unlink()
        code, out = self.run_check()
        self.assertEqual(code, HELD, out)
        self.assertIn("deleted:", out)

    def test_membership_is_reported_even_when_nothing_moved(self) -> None:
        self.agents(50)
        self.commit()
        self.assertIn("membership unchanged", self.run_check()[1])


class TestItUsesOneMeasurement(GrowthCase):
    def test_it_imports_the_budget_gates_measurement(self) -> None:
        """Two counts of this set have disagreed here before, and the ratchet reported "held"
        while the thing it watched grew. There is one implementation and this calls it."""
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("check-always-on.py", source)
        self.assertNotIn("alwaysApply", source.split('"""', 2)[-1])

    def test_it_agrees_with_the_budget_gate_on_this_repository(self) -> None:
        always_on = subprocess.run(
            [sys.executable, str(ROOT / ".github" / "scripts" / "check-always-on.py")],
            capture_output=True, cwd=str(ROOT))
        reported = [line for line in always_on.stdout.decode("utf-8", "replace").splitlines()
                    if "ALWAYS-ON TOTAL" in line]
        self.assertTrue(reported, always_on.stderr.decode("utf-8", "replace"))


class TestNoHistory(GrowthCase):
    def test_it_says_it_is_enforcing_nothing(self) -> None:
        """This repository has zero commits by a deliberate choice, so an empty history is a
        real state rather than a theoretical one. A check that passes because it had nothing
        to read looks exactly like a healthy one in a green CI run."""
        self.agents(50)
        code, out = self.run_check()
        self.assertEqual(code, COULD_NOT_RUN, out)
        self.assertIn("enforcing nothing", out)

    def test_a_shorter_history_than_the_window_is_not_an_error(self) -> None:
        """A repository on its third commit compares against its first."""
        self.agents(50)
        self.commit()
        self.agents(40)
        self.commit()
        code, out = self.run_check("--window", "500")
        self.assertEqual(code, HELD, out)

    def test_the_set_appearing_from_nothing_is_growth(self) -> None:
        (self.dir / "README.md").write_text("hello\n", encoding="utf-8")
        self.commit()
        self.agents(50)
        code, out = self.run_check()
        self.assertEqual(code, GREW, out)


class TestCouldNotRun(GrowthCase):
    def test_a_missing_config_is_not_a_verdict(self) -> None:
        (self.dir / "aios" / "config.yml").unlink()
        self.assertEqual(self.run_check()[0], COULD_NOT_RUN)

    def test_a_config_without_the_window_is_not_a_verdict(self) -> None:
        (self.dir / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        self.assertEqual(self.run_check()[0], COULD_NOT_RUN)

    def test_a_directory_that_is_not_a_repository(self) -> None:
        shutil.rmtree(self.dir / ".git")
        self.assertEqual(self.run_check()[0], COULD_NOT_RUN)


class TestThisRepository(unittest.TestCase):
    def test_the_gate_is_registered(self) -> None:
        import yaml
        gates = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        entry = [g for g in gates["gates"] if g["id"] == "state.context_growth"]
        self.assertEqual(len(entry), 1)
        self.assertEqual(entry[0]["class"], "contract")

    def test_the_workflow_fetches_full_history(self) -> None:
        """A shallow clone shortens the window to whatever was fetched, silently. The check
        still runs, still passes, and compares against almost nothing."""
        import yaml
        workflow = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "hygiene.yml").read_text(encoding="utf-8"))
        steps = next(iter(workflow["jobs"].values()))["steps"]
        checkout = next(s for s in steps if str(s.get("uses", "")).startswith(
            "actions/checkout"))
        self.assertEqual(checkout.get("with", {}).get("fetch-depth"), 0)

    def test_the_window_is_configured(self) -> None:
        import yaml
        config = yaml.safe_load((ROOT / "aios" / "config.yml").read_text(encoding="utf-8"))
        self.assertGreaterEqual(config["budgets"]["growth_window_commits"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
