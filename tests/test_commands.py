#!/usr/bin/env python3
"""Tests for slash commands as thin wrappers (M4-09).

Run: python -m unittest discover -s tests -v

The rule being defended is that a command is one invocation. It is not obviously worth a gate
until you notice the drift is invisible: a command that has grown a second step keeps working,
it just stops meaning what its name says, in a file nobody greps and no test covers.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-commands.py"
SHARED = ROOT / ".claude" / "commands"

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2

GOOD = """\
---
description: Do the thing.
---

Does the thing, described in a line a person will actually see.

```
python scripts/thing.py $ARGUMENTS
```
"""


class CommandCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / ".claude" / "commands").mkdir(parents=True)
        (self.dir / "scripts").mkdir()
        (self.dir / "scripts" / "thing.py").write_text("print('hi')\n", encoding="utf-8")

    def command(self, text: str, name: str = "thing.md") -> None:
        (self.dir / ".claude" / "commands" / name).write_text(text, encoding="utf-8")

    def run_check(self) -> tuple[int, str]:
        result = subprocess.run([sys.executable, str(SCRIPT), "--dir", str(self.dir)],
                                capture_output=True)
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")

    def assertRejects(self, needle: str) -> None:
        code, out = self.run_check()
        self.assertEqual(code, FAIL, out)
        self.assertIn(needle, out)


class TestOneInvocation(CommandCase):
    def test_a_well_formed_command_passes(self) -> None:
        self.command(GOOD)
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)

    def test_two_command_lines_are_rejected(self) -> None:
        self.command(GOOD.replace("python scripts/thing.py $ARGUMENTS",
                                  "python scripts/thing.py\npython scripts/thing.py"))
        self.assertRejects("expected exactly 1")

    def test_two_code_blocks_are_rejected(self) -> None:
        self.command(GOOD + "\n```\npython scripts/thing.py\n```\n")
        self.assertRejects("code block(s), expected exactly 1")

    def test_shell_operators_are_rejected(self) -> None:
        """Each of these turns a wrapper into a program that no test covers."""
        for operator in ("&&", "||", ";", "|", "$(date)", "if true", "for x"):
            with self.subTest(operator=operator):
                self.command(GOOD.replace("$ARGUMENTS", f"{operator} python scripts/thing.py"))
                self.assertRejects("That is logic")

    def test_a_missing_target_is_rejected(self) -> None:
        """A wrapper around a missing script fails when someone reaches for it, which is the
        worst possible moment to find out."""
        self.command(GOOD.replace("scripts/thing.py", "scripts/absent.py"))
        self.assertRejects("does not exist")

    def test_an_invocation_naming_no_script_is_rejected(self) -> None:
        self.command(GOOD.replace("python scripts/thing.py $ARGUMENTS", "echo hello"))
        self.assertRejects("names no script")

    def test_an_unclosed_fence_is_rejected(self) -> None:
        self.command(GOOD.rstrip()[:-3])
        code, out = self.run_check()
        self.assertEqual(code, FAIL, out)


class TestWhatTheUserSees(CommandCase):
    def test_a_body_starting_with_code_is_rejected(self) -> None:
        """Measured: Cursor shows the body in the `/` picker, not the frontmatter
        description. The first line is user-visible whether or not its author knew."""
        self.command("---\ndescription: Do the thing.\n---\n\n"
                     "```\npython scripts/thing.py\n```\n")
        self.assertRejects("first line is user-visible")

    def test_missing_frontmatter_is_rejected(self) -> None:
        self.command(GOOD.split("---\n\n", 1)[1])
        self.assertRejects("no YAML frontmatter")

    def test_a_frontmatter_without_a_description_is_rejected(self) -> None:
        self.command(GOOD.replace("description: Do the thing.", "name: thing"))
        self.assertRejects("no description")


class TestOneDirectory(CommandCase):
    def test_a_cursor_copy_is_rejected(self) -> None:
        """Not because duplication is untidy, but because it is a fact in two places, and the
        copy nobody edits is the one that goes stale while still being offered."""
        self.command(GOOD)
        (self.dir / ".cursor" / "commands").mkdir(parents=True)
        (self.dir / ".cursor" / "commands" / "thing.md").write_text(GOOD, encoding="utf-8")
        self.assertRejects("two tool directories")

    def test_an_empty_cursor_commands_directory_is_not_a_violation(self) -> None:
        self.command(GOOD)
        (self.dir / ".cursor" / "commands").mkdir(parents=True)
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)

    def test_a_missing_shared_directory_could_not_run(self) -> None:
        shutil.rmtree(self.dir / ".claude" / "commands")
        code, _ = self.run_check()
        self.assertEqual(code, COULD_NOT_RUN)


class TestThisRepository(unittest.TestCase):
    def test_the_shipped_commands_pass(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, PASS, result.stdout.decode())

    def test_every_command_wraps_something_that_exists_today(self) -> None:
        """A command pointing at `aios` would be a wrapper around a binary this machine
        cannot build. The set stays small until the CLI lands rather than shipping broken."""
        for path in SHARED.glob("*.md"):
            with self.subTest(command=path.name):
                self.assertIn(".github/scripts/", path.read_text(encoding="utf-8"))

    def test_there_is_no_cursor_commands_directory(self) -> None:
        self.assertFalse((ROOT / ".cursor" / "commands").is_dir())

    def test_the_gate_is_registered(self) -> None:
        import yaml
        gates = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        found = [g for g in gates["gates"] if g["id"] == "state.thin_commands"]
        self.assertEqual(len(found), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
