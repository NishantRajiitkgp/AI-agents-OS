#!/usr/bin/env python3
"""Tests for the parallelism rule (M4-11).

Run: python -m unittest discover -s tests -v

Two halves, and they are different kinds of control. Disjointness is checked *before dispatch*
and can prevent the collision entirely. The write lease is checked at the moment of a write
and can only bound one, because nothing tells it when a session ended.

The disjointness check is deliberately sound rather than complete: it may refuse two scopes
that would never have collided, and it may not permit two that would. These tests pin that
direction, because a later "improvement" that trades it away would look like a bug fix.
"""

from __future__ import annotations

import importlib.util
import io
import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-parallel.py"
HOOK = ROOT / "aios" / "bin" / "hooks" / "check-mode.py"

PASS, REFUSED, COULD_NOT_RUN = 0, 1, 2


def load(path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


parallel = load(SCRIPT)


class TestGlobIntersection(unittest.TestCase):
    """Whether two patterns *can* match one path, not whether they do today.

    The distinction is the reason this is a pattern intersection and not a file-set one:
    `src/**` and `src/auth/**` share no file until the task creates `src/auth/`, and by then
    the two agents have already collided.
    """

    def overlap(self, a: str, b: str) -> bool:
        return parallel.patterns_overlap(parallel.split(a), parallel.split(b))

    def test_identical_patterns_overlap(self) -> None:
        self.assertTrue(self.overlap("src/main.rs", "src/main.rs"))

    def test_unrelated_paths_do_not(self) -> None:
        self.assertFalse(self.overlap("src/main.rs", "docs/architecture.md"))

    def test_a_directory_tree_contains_its_subtree(self) -> None:
        self.assertTrue(self.overlap("src/**", "src/auth/**"))

    def test_sibling_subtrees_do_not_overlap(self) -> None:
        self.assertFalse(self.overlap("src/auth/**", "src/search/**"))

    def test_a_star_does_not_cross_a_directory_boundary(self) -> None:
        """`src/*.rs` is one level. If this ever returns True the check has quietly become
        far more permissive than it reads."""
        self.assertFalse(self.overlap("src/*.rs", "src/auth/mod.rs"))

    def test_a_double_star_does_cross(self) -> None:
        self.assertTrue(self.overlap("src/**/*.rs", "src/auth/mod.rs"))

    def test_a_leading_double_star_matches_anywhere(self) -> None:
        self.assertTrue(self.overlap("**/*.md", "docs/design/05-workflows.md"))

    def test_extensions_discriminate(self) -> None:
        self.assertFalse(self.overlap("src/**/*.rs", "src/**/*.py"))

    def test_question_marks_match_any_single_character(self) -> None:
        self.assertTrue(self.overlap("aios/tasks/T-????.md", "aios/tasks/T-a3f8.md"))
        self.assertFalse(self.overlap("aios/tasks/T-???.md", "aios/tasks/T-a3f8.md"))

    def test_a_trailing_slash_means_the_contents(self) -> None:
        """Which is what an author writing `docs/` means, and not what the matcher would
        otherwise do with it."""
        self.assertTrue(self.overlap("docs/", "docs/design/05-workflows.md"))

    def test_a_double_star_matches_zero_segments(self) -> None:
        self.assertTrue(self.overlap("src/**", "src"))

    def test_prefixes_that_only_look_alike_do_not_overlap(self) -> None:
        self.assertFalse(self.overlap("src/auth/**", "src/authz/**"))


class DispatchCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "tasks").mkdir(parents=True)
        self.config(tier="internal")

    def config(self, tier: str = "internal") -> None:
        (self.dir / "aios" / "config.yml").write_text(
            f"tier: {tier}\nparallelism:\n  max_tier: internal\n  write_lease_minutes: 2\n",
            encoding="utf-8")

    def task(self, task_id: str, touches: list[str], status: str = "todo",
             blocked_by: list[str] | None = None) -> None:
        lines = ["---", f"id: {task_id}", "title: A task", f"status: {status}"]
        if touches:
            lines.append("touches:")
            lines += [f'  - "{entry}"' for entry in touches]
        else:
            lines.append("touches: []")
        if blocked_by:
            lines.append("blocked_by:")
            lines += [f"  - {entry}" for entry in blocked_by]
        lines += ["---", "", "Body."]
        (self.dir / "aios" / "tasks" / f"{task_id}.md").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def dispatch(self, *task_ids: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.dir), *task_ids],
            capture_output=True)
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")


class TestDispatch(DispatchCase):
    def test_disjoint_scopes_are_permitted(self) -> None:
        self.task("T-0001", ["src/auth/**"])
        self.task("T-0002", ["src/search/**"])
        code, out = self.dispatch("T-0001", "T-0002")
        self.assertEqual(code, PASS, out)

    def test_the_permission_states_the_cost(self) -> None:
        """05 §6 puts a number on it. A permission that reads as encouragement would make an
        exception into a default."""
        self.task("T-0001", ["src/auth/**"])
        self.task("T-0002", ["src/search/**"])
        _, out = self.dispatch("T-0001", "T-0002")
        self.assertIn("order of magnitude", out)

    def test_overlapping_scopes_are_refused(self) -> None:
        self.task("T-0001", ["src/**"])
        self.task("T-0002", ["src/auth/mod.rs"])
        code, out = self.dispatch("T-0001", "T-0002")
        self.assertEqual(code, REFUSED)
        self.assertIn("can match the same path", out)

    def test_the_refusal_names_both_patterns(self) -> None:
        """A refusal that does not say which two globs collided leaves the human to diff two
        task files by eye, which is how a control becomes something people route around."""
        self.task("T-0001", ["src/**"])
        self.task("T-0002", ["src/auth/mod.rs"])
        _, out = self.dispatch("T-0001", "T-0002")
        self.assertIn("src/**", out)
        self.assertIn("src/auth/mod.rs", out)

    def test_a_scope_that_does_not_exist_yet_still_collides(self) -> None:
        """Nothing is created in the fixture tree. A file-set intersection would call these
        disjoint and be wrong the moment either task ran."""
        self.task("T-0001", ["src/**"])
        self.task("T-0002", ["src/brand/new/file.rs"])
        code, _ = self.dispatch("T-0001", "T-0002")
        self.assertEqual(code, REFUSED)

    def test_a_task_without_touches_cannot_be_paired(self) -> None:
        self.task("T-0001", [])
        self.task("T-0002", ["src/search/**"])
        code, out = self.dispatch("T-0001", "T-0002")
        self.assertEqual(code, REFUSED)
        self.assertIn("declares no touches", out)

    def test_tasks_ordered_by_blocked_by_are_sequential(self) -> None:
        self.task("T-0001", ["src/auth/**"])
        self.task("T-0002", ["src/search/**"], blocked_by=["T-0001"])
        code, out = self.dispatch("T-0001", "T-0002")
        self.assertEqual(code, REFUSED)
        self.assertIn("sequential work", out)

    def test_a_finished_task_is_not_dispatchable(self) -> None:
        self.task("T-0001", ["src/auth/**"], status="done")
        self.task("T-0002", ["src/search/**"])
        code, out = self.dispatch("T-0001", "T-0002")
        self.assertEqual(code, REFUSED)
        self.assertIn("not dispatchable", out)

    def test_the_same_task_twice_is_refused(self) -> None:
        self.task("T-0001", ["src/auth/**"])
        code, out = self.dispatch("T-0001", "T-0001")
        self.assertEqual(code, REFUSED)
        self.assertIn("more than once", out)

    def test_all_collisions_are_reported_not_just_the_first(self) -> None:
        """Fixing one and rerunning to find the next is how a check trains people to stop
        running it."""
        self.task("T-0001", ["src/**"])
        self.task("T-0002", ["src/auth/mod.rs"], status="done")
        _, out = self.dispatch("T-0001", "T-0002")
        self.assertIn("not dispatchable", out)
        self.assertIn("can match the same path", out)


class TestTier(DispatchCase):
    def test_prototype_permits_parallel_worktrees(self) -> None:
        self.config(tier="prototype")
        self.task("T-0001", ["src/auth/**"])
        self.task("T-0002", ["src/search/**"])
        self.assertEqual(self.dispatch("T-0001", "T-0002")[0], PASS)

    def test_production_does_not(self) -> None:
        self.config(tier="production")
        self.task("T-0001", ["src/auth/**"])
        self.task("T-0002", ["src/search/**"])
        code, out = self.dispatch("T-0001", "T-0002")
        self.assertEqual(code, REFUSED)
        self.assertIn("permitted at internal and below", out)

    def test_regulated_does_not(self) -> None:
        self.config(tier="regulated")
        self.task("T-0001", ["src/auth/**"])
        self.task("T-0002", ["src/search/**"])
        self.assertEqual(self.dispatch("T-0001", "T-0002")[0], REFUSED)


class TestCouldNotRun(DispatchCase):
    def test_one_task_is_not_a_parallel_dispatch(self) -> None:
        self.task("T-0001", ["src/**"])
        self.assertEqual(self.dispatch("T-0001")[0], COULD_NOT_RUN)

    def test_a_missing_task_could_not_run(self) -> None:
        self.task("T-0001", ["src/**"])
        code, out = self.dispatch("T-0001", "T-9999")
        self.assertEqual(code, COULD_NOT_RUN)
        self.assertIn("no task file", out)

    def test_a_missing_config_could_not_run(self) -> None:
        """Not a refusal. A check that cannot read its policy has not applied it, and saying
        'refused' would claim an answer it does not have."""
        (self.dir / "aios" / "config.yml").unlink()
        self.task("T-0001", ["src/**"])
        self.task("T-0002", ["docs/**"])
        self.assertEqual(self.dispatch("T-0001", "T-0002")[0], COULD_NOT_RUN)


def write_event(session: str, path: str) -> bytes:
    """A preToolUse payload shaped like the measured one, BOM and all."""
    payload = {"conversation_id": session, "session_id": session, "tool_name": "Write",
               "tool_input": {"file_path": path, "content": "x"},
               "hook_event_name": "preToolUse", "cursor_version": "3.13.21"}
    return b"\xef\xbb\xbf" + json.dumps(payload).encode("utf-8") + b"\r\n"


class TestWriteLease(unittest.TestCase):
    """One writing agent per worktree. Separate worktrees need no special case: each has its
    own root and therefore its own lease, which is the permission the rule grants them."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir(parents=True)
        (self.dir / "aios" / "config.yml").write_text(
            "tier: prototype\nparallelism:\n  write_lease_minutes: 2\n", encoding="utf-8")

    def run_hook(self, session: str, path: str = "src/main.rs") -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(HOOK)], input=write_event(session, str(self.dir / path)),
            capture_output=True, env={**dict(__import__("os").environ),
                                      "CURSOR_PROJECT_DIR": str(self.dir)})
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")

    def test_one_session_writes_freely(self) -> None:
        for _ in range(3):
            code, out = self.run_hook("session-a")
            self.assertNotIn("deny", out)

    def test_a_second_session_is_refused_while_the_lease_is_fresh(self) -> None:
        self.run_hook("session-a")
        code, out = self.run_hook("session-b")
        self.assertIn("deny", out)
        self.assertIn("write lease", out)

    def test_the_refusal_points_at_parallel_worktrees(self) -> None:
        """A refusal with no permitted alternative is one the reader routes around."""
        self.run_hook("session-a")
        _, out = self.run_hook("session-b")
        self.assertIn("separate worktrees", out)

    def test_a_stale_lease_is_taken_over(self) -> None:
        """The measured identity is the chat, not the window, so a different holder is
        usually the same person in their next chat. A lease that never expired would make
        that a refusal, and the response to that is to delete the control."""
        (self.dir / ".aios-writer").write_text(
            f"session-a {time.time() - 3600:.0f}\n", encoding="utf-8")
        code, out = self.run_hook("session-b")
        self.assertNotIn("deny", out)

    def test_taking_over_transfers_the_lease(self) -> None:
        (self.dir / ".aios-writer").write_text(
            f"session-a {time.time() - 3600:.0f}\n", encoding="utf-8")
        self.run_hook("session-b")
        self.assertTrue((self.dir / ".aios-writer").read_text().startswith("session-b"))

    def test_a_separate_worktree_has_its_own_lease(self) -> None:
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, True)
        (other / "aios").mkdir(parents=True)
        shutil.copy(self.dir / "aios" / "config.yml", other / "aios" / "config.yml")
        self.run_hook("session-a")
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=write_event("session-b", str(other / "src" / "main.rs")),
            capture_output=True,
            env={**dict(__import__("os").environ), "CURSOR_PROJECT_DIR": str(other)})
        self.assertNotIn("deny", result.stdout.decode("utf-8", "replace"))

    def test_a_corrupt_lease_does_not_refuse(self) -> None:
        """A control that cannot read its own state must not start denying on that basis;
        that is the fail-closed incident repeating itself in a new file."""
        (self.dir / ".aios-writer").write_text("garbage\n", encoding="utf-8")
        _, out = self.run_hook("session-b")
        self.assertNotIn("deny", out)

    def test_an_event_without_an_identity_neither_claims_nor_is_refused(self) -> None:
        """Run against a *held* lease, which is the only configuration that discriminates.
        With no identity there is no claim to make and no claim to check: enforcing on a
        guess would refuse a caller it cannot name, and recording one would put the string
        `None` in the lease and lock out the session that actually holds it."""
        self.run_hook("session-a")
        payload = {"tool_name": "Write", "tool_input": {"file_path": str(self.dir / "a.rs")},
                   "cursor_version": "3.13.21"}
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=b"\xef\xbb\xbf" + json.dumps(payload).encode() + b"\r\n",
            capture_output=True,
            env={**dict(__import__("os").environ), "CURSOR_PROJECT_DIR": str(self.dir)})
        self.assertNotIn("deny", result.stdout.decode("utf-8", "replace"))
        self.assertTrue((self.dir / ".aios-writer").read_text().startswith("session-a"))

    def test_the_lease_applies_with_no_mode_set(self) -> None:
        """A mode is a choice about how to work and defaults to unrestricted. One writer per
        worktree is an invariant about what the worktree survives, and a fresh clone is not
        exempt from it."""
        self.assertFalse((self.dir / ".aios-mode").exists())
        self.run_hook("session-a")
        _, out = self.run_hook("session-b")
        self.assertIn("deny", out)


class TestThisRepository(unittest.TestCase):
    def test_the_configured_window_sits_between_the_two_intervals(self) -> None:
        """Measured: session identity is per chat. Too long and the next chat is refused;
        too short and two live agents miss each other."""
        import yaml
        config = yaml.safe_load((ROOT / "aios" / "config.yml").read_text(encoding="utf-8"))
        self.assertLessEqual(config["parallelism"]["write_lease_minutes"], 5)
        self.assertGreaterEqual(config["parallelism"]["write_lease_minutes"], 1)

    def test_max_tier_is_internal_as_the_design_says(self) -> None:
        import yaml
        config = yaml.safe_load((ROOT / "aios" / "config.yml").read_text(encoding="utf-8"))
        self.assertEqual(config["parallelism"]["max_tier"], "internal")

    def test_the_lease_file_is_not_committed(self) -> None:
        self.assertIn(".aios-writer", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_this_repositorys_own_task_is_read_by_the_real_check(self) -> None:
        """Pointed at the repository it governs, not only at fixtures. There is one task
        file, so this cannot assert a verdict — it asserts the frontmatter reader survives a
        real task, which is where a hand-rolled parser fails first."""
        fields = parallel.load_task(ROOT, "T-950a")
        self.assertIn("status", fields)
        self.assertTrue(fields.get("touches"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
