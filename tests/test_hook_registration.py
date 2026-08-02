#!/usr/bin/env python3
"""Tests for hook registration across both tools (M4-07).

Run: python -m unittest discover -s tests -v

The claim being defended is narrow: hook *logic* lives in `aios/bin/hooks/`, and each tool's
settings file holds a registration line pointing at it. What that buys is a drift surface of
one line per tool instead of two implementations of the same rule, where the copy nobody is
looking at is the one that goes stale.

So these tests mostly check that the pointers point somewhere real, and that no logic has
crept back into the settings files.
"""

from __future__ import annotations

import json
import tempfile
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOKS = ROOT / "aios" / "bin" / "hooks"
CURSOR = ROOT / ".cursor" / "hooks.json"
CLAUDE = ROOT / ".claude" / "settings.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def commands(settings: dict) -> list[str]:
    """Every command string either tool's hook block registers."""
    found = []
    for entries in (settings.get("hooks") or {}).values():
        for entry in entries:
            if "command" in entry:            # Cursor's shape
                found.append(entry["command"])
            for inner in entry.get("hooks", []):   # Claude Code's nested shape
                if "command" in inner:
                    found.append(inner["command"])
    return found


class TestBothToolsPointAtTheSameScripts(unittest.TestCase):
    def test_every_registration_points_into_aios_bin_hooks(self) -> None:
        for path in (CURSOR, CLAUDE):
            for command in commands(load(path)):
                with self.subTest(tool=path.name, command=command):
                    self.assertIn("aios/bin/hooks/", command,
                                  "hook logic belongs in aios/bin/hooks/, not in a settings "
                                  "file and not in a tool-specific directory")

    def test_every_referenced_script_exists(self) -> None:
        """A pointer to a file that is not there is a control that silently does nothing."""
        for path in (CURSOR, CLAUDE):
            for command in commands(load(path)):
                target = ROOT / command.split()[-1]
                with self.subTest(tool=path.name, script=target.name):
                    self.assertTrue(target.is_file(), f"{target} does not exist")

    def test_both_tools_register_the_same_set_of_scripts(self) -> None:
        """Divergence here is the drift M4-07 exists to prevent: a control enforced in one
        tool and absent in the other is worse than absent in both, because it looks covered."""
        def scripts(path: Path) -> set[str]:
            return {command.split()[-1].rsplit("/", 1)[-1] for command in commands(load(path))}
        self.assertEqual(scripts(CURSOR), scripts(CLAUDE))

    def test_the_settings_files_hold_no_logic(self) -> None:
        """The registration is a line. The moment a condition appears in it, there are two
        implementations again and one of them is in a file with no tests."""
        for path in (CURSOR, CLAUDE):
            for command in commands(load(path)):
                with self.subTest(tool=path.name, command=command):
                    for shell_operator in ("&&", "||", ";", "|", "if ", "test "):
                        self.assertNotIn(shell_operator, command)


class TestTheResponseLayer(unittest.TestCase):
    """The one thing that genuinely differs between the tools, and therefore the one place a
    branch is allowed to live."""

    def setUp(self) -> None:
        sys.path.insert(0, str(HOOKS))
        import importlib
        self.respond = importlib.import_module("respond")

    def test_a_cursor_event_is_recognised_by_its_version_field(self) -> None:
        self.assertEqual(self.respond.which_tool({"cursor_version": "3.13.21"}),
                         self.respond.CURSOR)

    def test_a_claude_event_is_recognised_without_one(self) -> None:
        self.assertEqual(self.respond.which_tool({"session_id": "s"}), self.respond.CLAUDE)

    def test_an_unknown_caller_is_not_treated_as_claude(self) -> None:
        """Claude's branch denies by exit code. Guessing it for an unknown tool would mean
        denying in a way that tool may not understand, or not at all."""
        self.assertEqual(self.respond.which_tool({}), self.respond.UNKNOWN)


class TestTheDenialReachesEachToolInItsOwnLanguage(unittest.TestCase):
    """Measured for Cursor. For Claude Code this asserts the documented contract, which is
    what M4-13 exists to confirm."""

    def run_hook(self, event: dict) -> subprocess.CompletedProcess:
        """Pointed at a scratch copy, never at the repository itself.

        This used to run with `cwd=ROOT` and no root override, so the hook resolved the real
        repository and took the write lease in it — a test whose side effect was to make the
        next genuine write be refused as a second agent. Anything invoking a hook has to name
        a root it owns.
        """
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, True)
        (scratch / "aios").mkdir()
        shutil.copy(ROOT / "aios" / "config.yml", scratch / "aios" / "config.yml")
        raw = "\ufeff".encode() + json.dumps(event).encode() + b"\r\n"
        return subprocess.run([sys.executable, str(HOOKS / "check-mode.py")], input=raw,
                              capture_output=True, cwd=str(scratch),
                              env={"CURSOR_PROJECT_DIR": str(scratch), "PATH": ""})

    def denying_event(self, **extra) -> dict:
        return {"tool_name": "Write",
                "tool_input": {"file_path": str(ROOT / "src" / "main.rs"), "content": "x"},
                "hook_event_name": "preToolUse", **extra}

    def respond_deny(self, event: dict) -> tuple[int, str, str]:
        """Exercise the refusal branch itself. Going through check-mode.py would need a mode
        file in the repository root, and the branch under test is the response, not the rule."""
        script = (
            "import sys, io, json, contextlib\n"
            f"sys.path.insert(0, {str(HOOKS)!r})\n"
            "import respond\n"
            "out, err = io.StringIO(), io.StringIO()\n"
            "with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):\n"
            f"    code = respond.deny({event!r}, 'user text', 'agent text')\n"
            "print(json.dumps({'code': code, 'out': out.getvalue(), 'err': err.getvalue()}))\n")
        result = subprocess.run([sys.executable, "-c", script], capture_output=True)
        payload = json.loads(result.stdout.decode())
        return payload["code"], payload["out"], payload["err"]

    def test_a_cursor_denial_is_json_on_stdout_with_exit_zero(self) -> None:
        """Measured: Cursor ignores exit code 2 despite documenting it as blocking, so the
        JSON is the only thing that refuses anything there. Returning 2 as well would be
        harmless in Cursor and is still wrong to rely on."""
        code, out, err = self.respond_deny({"cursor_version": "3.13.21"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["permission"], "deny")
        self.assertEqual(err, "")

    def test_a_claude_denial_is_exit_two_with_the_reason_on_stderr(self) -> None:
        """Documented, not measured — Claude Code is not installed here. M4-13 confirms it."""
        code, out, err = self.respond_deny({"session_id": "s"})
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("agent text", err)

    def test_an_unknown_caller_gets_the_shape_that_was_measured(self) -> None:
        code, out, _ = self.respond_deny({})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["permission"], "deny")

    def test_cursor_is_answered_with_json_and_exit_zero(self) -> None:
        """Measured: exit code 2 is ignored by Cursor even though its docs list it as
        blocking, so the JSON is the only thing that refuses anything there."""
        result = self.run_hook(self.denying_event(cursor_version="3.13.21"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout.decode())["permission"], "allow")

    def test_the_exit_code_finding_is_recorded_where_it_will_be_found(self) -> None:
        """Losing this measurement means the next person unifies the two branches and the
        control stops working in Cursor without failing anything."""
        measured = (ROOT / "aios" / "bin" / "probe" / "results"
                    / "hook-event-2026-08-01.md").read_text(encoding="utf-8")
        self.assertIn("Exit code 2 does not deny in Cursor", measured)


class TestTheClaudeSideIsLabelledUnverified(unittest.TestCase):
    def test_the_settings_file_says_so(self) -> None:
        """An unmeasured contract presented as a measured one is how M2-08 happened. The
        label is the difference between a known gap and a false assurance."""
        comment = " ".join(load(CLAUDE)["_comment"])
        self.assertIn("UNVERIFIED", comment)
        self.assertIn("M4-13", comment)


if __name__ == "__main__":
    unittest.main(verbosity=2)
