#!/usr/bin/env python3
"""Tests for the ratchet mechanism.

Run: python -m unittest discover -s tests -v

M3-03's criterion is "a regression fails and an equal-or-better value passes, on a real
metric". Both halves matter equally and for different reasons. Failing a regression is what a
ratchet is for; passing an improvement is what makes it a ratchet rather than a threshold,
because a check that blocks a good change gets removed and takes the ratchet with it.

The third property is the one the criterion does not name and the mechanism lives or dies on:
loosening a baseline must fail. It is the single edit a regression needs, and it looks like
ordinary configuration.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-ratchets.py"

HELD, FAILED, CANNOT_RUN = 0, 1, 2


def ratchet_file(baseline: int, metric: str = "agents_md_lines",
                 direction: str = "lower_is_better") -> str:
    return (f"ratchets:\n"
            f"  - id: {metric}\n"
            f"    title: A metric\n"
            f"    direction: {direction}\n"
            f"    baseline: {baseline}\n")


class RatchetCase(unittest.TestCase):
    """A fixture repository that is a real git repo, since baselines compare against HEAD."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir(parents=True)
        self.write("AGENTS.md", "\n".join(f"line {n}" for n in range(10)))
        self.write("aios/ratchets.yml", ratchet_file(10))
        self.git("init", "-q")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "user.name", "Test")
        self.commit()

    def git(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=self.dir,
                              capture_output=True, text=True)

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "state")

    def write(self, relative: str, text: str) -> None:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def set_agents_md_lines(self, count: int) -> None:
        self.write("AGENTS.md", "\n".join(f"line {n}" for n in range(count)))

    def check(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.dir), *extra],
            capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr


class TestTheRule(RatchetCase):
    """May not make this worse."""

    def test_a_regression_fails(self) -> None:
        self.set_agents_md_lines(11)
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("worse than the baseline", out)

    def test_an_equal_value_passes(self) -> None:
        code, out = self.check()
        self.assertEqual(code, HELD, out)
        self.assertIn("held", out)

    def test_a_better_value_passes(self) -> None:
        """A ratchet that blocked an improvement would be deleted, and rightly."""
        self.set_agents_md_lines(5)
        code, out = self.check()
        self.assertEqual(code, HELD, out)
        self.assertIn("improved", out)

    def test_a_better_value_reports_that_the_baseline_can_be_tightened(self) -> None:
        self.set_agents_md_lines(5)
        self.assertIn("can be tightened", self.check()[1])

    def test_higher_is_better_inverts_the_comparison(self) -> None:
        """Coverage ratchets the other way, so the direction cannot be assumed."""
        self.write("aios/ratchets.yml", ratchet_file(10, direction="higher_is_better"))
        self.commit()
        self.set_agents_md_lines(11)
        self.assertEqual(self.check()[0], HELD)
        self.set_agents_md_lines(9)
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("worse than the baseline", out)


class TestBaselineTampering(RatchetCase):
    """The evasion the mechanism exists to survive."""

    def test_loosening_a_baseline_fails(self) -> None:
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml", ratchet_file(20))
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("baseline was loosened", out)

    def test_loosening_fails_even_when_the_metric_would_pass(self) -> None:
        """The point: after loosening, the measurement agrees. Only the history disagrees."""
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml", ratchet_file(25))
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("must be declared", out)

    def test_tightening_a_baseline_passes(self) -> None:
        self.set_agents_md_lines(5)
        self.write("aios/ratchets.yml", ratchet_file(5))
        code, out = self.check()
        self.assertEqual(code, HELD, out)

    def test_loosening_is_direction_aware(self) -> None:
        self.write("aios/ratchets.yml", ratchet_file(10, direction="higher_is_better"))
        self.commit()
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml", ratchet_file(5, direction="higher_is_better"))
        self.assertIn("baseline was loosened", self.check()[1])

    def test_a_new_ratchet_has_nothing_to_compare_against_and_passes(self) -> None:
        """Adding a metric must be possible, or no ratchet is ever added."""
        self.write("aios/ratchets.yml", ratchet_file(10) + """\
  - id: todo_markers
    title: Markers
    direction: lower_is_better
    baseline: 500
""")
        code, out = self.check()
        self.assertEqual(code, HELD, out)


class TestDeclaredLoosening(RatchetCase):
    """A baseline that may only ever improve is a freeze, not a ratchet.

    It forbids spending headroom that was deliberately left, which makes "never blocks a good
    change" untrue. So loosening is permitted, and made expensive rather than impossible.
    """

    def raised(self, baseline: int, source: int, reason: str) -> str:
        return ratchet_file(baseline) + f"    raised:\n      from: {source}\n" \
                                        f"      reason: {reason}\n"

    def test_a_declared_loosening_passes(self) -> None:
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml",
                   self.raised(20, 10, "Ten lines of measured constraints were added."))
        code, out = self.check()
        self.assertEqual(code, HELD, out)

    def test_a_declared_loosening_says_so_loudly(self) -> None:
        """Review is the control. This is what review reads."""
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml",
                   self.raised(20, 10, "Ten lines of measured constraints were added."))
        self.assertIn("LOOSENED", self.check()[1])

    def test_a_stale_justification_does_not_carry_over(self) -> None:
        """Naming the old value is what stops one reason covering every later move."""
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml",
                   self.raised(20, 10, "Ten lines of measured constraints were added."))
        self.commit()
        self.set_agents_md_lines(30)
        self.write("aios/ratchets.yml",
                   self.raised(30, 10, "Ten lines of measured constraints were added."))
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("must be declared", out)

    def test_a_loosening_with_no_reason_fails(self) -> None:
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml", self.raised(20, 10, "needed"))
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("no reason worth reading", out)

    def test_a_loosening_naming_the_wrong_source_fails(self) -> None:
        self.set_agents_md_lines(20)
        self.write("aios/ratchets.yml",
                   self.raised(20, 15, "Ten lines of measured constraints were added."))
        self.assertEqual(self.check()[0], FAILED)

    def test_a_declaration_cannot_excuse_a_regression(self) -> None:
        """`raised` justifies moving the bar, never being under it."""
        self.write("aios/ratchets.yml",
                   self.raised(10, 10, "Ten lines of measured constraints were added."))
        self.commit()
        self.set_agents_md_lines(11)
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("worse than the baseline", out)


class TestUpdate(RatchetCase):
    def test_update_tightens_an_improved_baseline(self) -> None:
        self.set_agents_md_lines(5)
        code, out = self.check("--update")
        self.assertEqual(code, HELD, out)
        self.assertIn("baseline: 5", (self.dir / "aios" / "ratchets.yml").read_text())

    def test_update_rewrites_the_right_block_when_baselines_collide(self) -> None:
        """Two metrics sharing a baseline value must not have each other's rewritten.

        `todo_markers` is pinned to exactly its measured value so it holds, while
        `agents_md_lines` improves from the same number. Only the improving block may move.
        """
        self.write("notes.py", "# TODO\n" * 10)
        self.write("aios/ratchets.yml", ratchet_file(10) + """\
  - id: todo_markers
    title: Markers
    direction: lower_is_better
    baseline: 10
""")
        self.commit()
        self.set_agents_md_lines(5)
        code, out = self.check("--update")
        self.assertEqual(code, HELD, out)
        text = (self.dir / "aios" / "ratchets.yml").read_text()
        agents_block, todo_block = text.split("- id: todo_markers")
        self.assertIn("baseline: 5", agents_block)
        self.assertIn("baseline: 10", todo_block)

    def test_update_leaves_a_held_baseline_alone(self) -> None:
        before = (self.dir / "aios" / "ratchets.yml").read_text()
        self.check("--update")
        self.assertEqual(before, (self.dir / "aios" / "ratchets.yml").read_text())


class TestDefinitionsAreRejected(RatchetCase):
    def test_an_unknown_metric_fails(self) -> None:
        self.write("aios/ratchets.yml", ratchet_file(10, metric="vibes"))
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("no measurement is implemented", out)

    def test_an_unknown_direction_fails(self) -> None:
        self.write("aios/ratchets.yml", ratchet_file(10, direction="sideways"))
        self.assertIn("is not one of", self.check()[1])

    def test_a_non_numeric_baseline_fails(self) -> None:
        self.write("aios/ratchets.yml",
                   ratchet_file(10).replace("baseline: 10", "baseline: low"))
        self.assertIn("is not a number", self.check()[1])

    def test_a_missing_file_cannot_run(self) -> None:
        (self.dir / "aios" / "ratchets.yml").unlink()
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)

    def test_an_empty_ratchet_set_cannot_run(self) -> None:
        """Zero ratchets would pass silently, which is how a gate becomes decorative."""
        self.write("aios/ratchets.yml", "ratchets: []\n")
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)


class TestMeasurements(RatchetCase):
    """A metric nobody checks the arithmetic of is a number, not a measurement."""

    def test_always_on_counts_only_always_apply_rules(self) -> None:
        self.write(".cursor/rules/on.mdc", "alwaysApply: true\na\nb\n")
        self.write(".cursor/rules/off.mdc", "alwaysApply: false\n" + "x\n" * 50)
        self.write("aios/ratchets.yml", ratchet_file(13, metric="always_on_lines"))
        self.commit()
        code, out = self.check()
        self.assertEqual(code, HELD, out)  # 10 lines of AGENTS.md + 3 of the applied rule

    def test_suppressions_are_counted_across_tracked_files(self) -> None:
        self.write("a.py", "x = 1  # noqa\ny = 2  # type: ignore\n")
        self.write("aios/ratchets.yml", ratchet_file(2, metric="suppressions"))
        self.commit()
        self.assertEqual(self.check()[0], HELD)
        self.write("a.py", "x = 1  # noqa\ny = 2  # type: ignore\nz = 3  # nosec\n")
        self.commit()
        self.assertEqual(self.check()[0], FAILED)

    def test_untracked_files_are_not_counted(self) -> None:
        """Otherwise a local scratch file changes the measurement and CI disagrees."""
        self.write("aios/ratchets.yml", ratchet_file(0, metric="todo_markers"))
        self.commit()
        self.write("scratch.py", "# TODO: not committed\n")
        self.assertEqual(self.check()[0], HELD)


class TestAntiDeletionRatchets(RatchetCase):
    """Two metrics whose only job is to notice something disappearing."""

    def test_deleting_a_gate_trips_the_registry_count(self) -> None:
        """Deleting a check is the quietest way to stop it failing."""
        self.write("aios/gates.yml", "gates:\n  - id: a\n  - id: b\n")
        self.write("aios/ratchets.yml",
                   ratchet_file(2, metric="gates_registered", direction="higher_is_better"))
        self.commit()
        self.assertEqual(self.check()[0], HELD)
        self.write("aios/gates.yml", "gates:\n  - id: a\n")
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("worse than the baseline", out)

    def test_deleting_a_test_trips_the_test_count(self) -> None:
        self.write("tests/test_thing.py", "def test_one():\n    pass\n\n"
                                          "def test_two():\n    pass\n")
        self.write("aios/ratchets.yml",
                   ratchet_file(2, metric="tests_declared", direction="higher_is_better"))
        self.commit()
        self.assertEqual(self.check()[0], HELD)
        self.write("tests/test_thing.py", "def test_one():\n    pass\n")
        self.assertEqual(self.check()[0], FAILED)

    def test_the_test_count_reads_source_not_a_run(self) -> None:
        """Skipping a test must not move this number.

        That failure belongs to the test-integrity audit, and the two are deliberately
        different: the audit reads a diff and sees only what a pull request contains, while
        this reads the tree and notices a suite that shrank by any route.
        """
        self.write("tests/test_thing.py", "import unittest\n\n"
                                          "@unittest.skip('later')\n"
                                          "def test_one():\n    pass\n")
        self.write("aios/ratchets.yml",
                   ratchet_file(1, metric="tests_declared", direction="higher_is_better"))
        self.commit()
        self.assertEqual(self.check()[0], HELD)


class TestUnwiredMetrics(RatchetCase):
    """`planned` and `not_applicable` must not become places a ratchet hides."""

    def planned(self, body: str) -> None:
        self.write("aios/ratchets.yml", ratchet_file(10) + "planned:\n" + body)

    def test_a_planned_metric_needs_a_task(self) -> None:
        self.planned("  - id: coverage_changed_lines\n"
                     "    direction: higher_is_better\n"
                     "    reason: Needs a compiled binary, which cannot be built here.\n")
        self.assertIn("names no task", self.check()[1])

    def test_a_planned_metric_needs_a_reason(self) -> None:
        self.planned("  - id: coverage_changed_lines\n"
                     "    direction: higher_is_better\n"
                     "    pending: M1-08\n")
        self.assertIn("no reason", self.check()[1])

    def test_a_planned_metric_that_is_measurable_today_fails(self) -> None:
        """The rule that stops `planned` being where a ratchet goes to avoid enforcement."""
        self.planned("  - id: suppressions\n"
                     "    direction: lower_is_better\n"
                     "    pending: M9-99\n"
                     "    reason: We would rather not count these just yet, honestly.\n")
        code, out = self.check()
        self.assertEqual(code, FAILED, out)
        self.assertIn("is measurable today", out)

    def test_a_not_applicable_metric_that_is_measurable_fails(self) -> None:
        self.write("aios/ratchets.yml", ratchet_file(10) + "not_applicable:\n"
                   "  - id: todo_markers\n"
                   "    reason: This repository does not believe in deferred work.\n")
        self.assertIn("it does apply", self.check()[1])

    def test_a_not_applicable_metric_needs_a_reason(self) -> None:
        self.write("aios/ratchets.yml", ratchet_file(10) + "not_applicable:\n"
                   "  - id: accessibility_violations\n    reason: n/a\n")
        self.assertIn("no reason", self.check()[1])

    def test_a_properly_declared_unwired_metric_passes(self) -> None:
        self.planned("  - id: coverage_changed_lines\n"
                     "    direction: higher_is_better\n"
                     "    pending: M1-08\n"
                     "    reason: Needs a compiled binary, which cannot be built here.\n")
        code, out = self.check()
        self.assertEqual(code, HELD, out)


class TestMarkersAreCountedInCodeOnly(RatchetCase):
    def test_a_marker_in_prose_is_not_counted(self) -> None:
        """Otherwise documenting the ratchet raises the ratchet, as it did here."""
        self.write("notes.md", "The TODO ratchet counts TODO and FIXME markers.\n")
        self.write("aios/ratchets.yml", ratchet_file(0, metric="todo_markers"))
        self.commit()
        code, out = self.check()
        self.assertEqual(code, HELD, out)

    def test_a_marker_in_code_is_counted(self) -> None:
        self.write("thing.py", "# TODO: finish this\n")
        self.write("aios/ratchets.yml", ratchet_file(0, metric="todo_markers"))
        self.commit()
        self.assertEqual(self.check()[0], FAILED)


class TestThisRepository(unittest.TestCase):
    def test_every_ratchet_in_this_repository_holds(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, HELD, result.stdout + result.stderr)

    def test_every_baseline_was_measured_rather_than_chosen(self) -> None:
        """A baseline set to an aspiration is a Contract gate wearing a ratchet's name.

        The tell is a baseline better than the current value: nothing produced it, so it
        blocks from the moment it lands.
        """
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            capture_output=True, text=True)
        self.assertNotIn("worse than the baseline", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
