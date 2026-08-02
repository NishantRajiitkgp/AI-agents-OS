#!/usr/bin/env python3
"""Tests for modes as permission sets.

Run: python -m unittest discover -s tests -v

Every payload here is built from the shape measured on 2026-08-01
(`aios/bin/probe/results/hook-event-2026-08-01.md`), including the UTF-8 BOM that Cursor
prefixes to stdin. That detail is not decoration: decoding it as plain UTF-8 raises, and a
hook that reads a parse failure as "no input" is what refused every command in the editor
during M2-08. A fixture without the BOM would test a contract this editor does not send.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / "aios" / "bin" / "hooks" / "check-mode.py"

CONFIG = """\
tier: prototype
modes:
  explore:
    writes: []
  plan:
    writes:
      - "aios/tasks/**"
      - "aios/requirements/**"
      - "aios/open-questions.md"
  implement:
    writes: touches
  verify:
    writes: []
"""


def event(tool_name: str, **tool_input) -> bytes:
    """A preToolUse payload shaped like the measured one, BOM and all."""
    payload = {
        "conversation_id": "c", "generation_id": "g", "model": "claude-opus-5",
        "tool_name": tool_name, "tool_input": tool_input, "tool_use_id": "t",
        "session_id": "s", "hook_event_name": "preToolUse", "cursor_version": "3.13.21",
        "workspace_roots": ["/c:/repo"], "user_email": "x@example.com",
        "transcript_path": "t.jsonl",
    }
    return "\ufeff".encode() + json.dumps(payload).encode() + b"\r\n"


class ModeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "tasks").mkdir(parents=True)
        (self.dir / "aios" / "requirements").mkdir(parents=True)
        (self.dir / "src").mkdir()
        (self.dir / "aios" / "config.yml").write_text(CONFIG, encoding="utf-8")

    def set_mode(self, line: str | None) -> None:
        path = self.dir / ".aios-mode"
        if line is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(line + "\n", encoding="utf-8")

    def task(self, task_id: str, touches: list[str],
             duplicate_check: list[str] | None = ("searched thing — nothing found",)) -> None:
        listed = "\n".join(f'  - "{pattern}"' for pattern in touches)
        checked = ""
        if duplicate_check is not None:
            entries = "\n".join(f'  - "{entry}"' for entry in duplicate_check)
            checked = "duplicate_check:\n" + entries + "\n" if entries else "duplicate_check:\n"
        (self.dir / "aios" / "tasks" / f"{task_id}.md").write_text(
            textwrap.dedent(f"""\
                ---
                id: {task_id}
                title: A task
                status: doing
                touches:
                """) + listed + "\n" + checked + "---\n\nBody.\n", encoding="utf-8")

    def run_hook(self, payload: bytes) -> dict:
        result = subprocess.run(
            [sys.executable, str(HOOK)], input=payload, capture_output=True,
            env={"CURSOR_PROJECT_DIR": str(self.dir), "PATH": ""}, cwd=str(self.dir))
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        return json.loads(result.stdout.decode("utf-8"))

    def write_to(self, relative: str) -> dict:
        return self.run_hook(event("Write", file_path=str(self.dir / relative), content="x"))


class TestTheMeasuredContract(ModeCase):
    def test_a_bom_prefixed_payload_parses(self) -> None:
        """The exact fault that produced the incident, asserted rather than assumed fixed."""
        self.set_mode("explore")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "deny")

    def test_an_unparseable_payload_allows_and_says_it_enforced_nothing(self) -> None:
        """Denying here would repeat the incident; allowing silently would hide the outage."""
        self.set_mode("explore")
        decision = self.run_hook(b"not json at all")
        self.assertEqual(decision["permission"], "allow")
        self.assertIn("enforced nothing", decision["agent_message"])

    def test_a_non_writing_tool_is_not_the_controls_business(self) -> None:
        self.set_mode("explore")
        for tool, payload in (("Read", {"file_path": str(self.dir / "src/main.rs")}),
                              ("Shell", {"command": "ls", "cwd": str(self.dir),
                                         "timeout": 60000})):
            with self.subTest(tool=tool):
                self.assertEqual(self.run_hook(event(tool, **payload))["permission"], "allow")

    def test_the_root_comes_from_the_environment_not_the_event(self) -> None:
        """Measured: writes carry no top-level `cwd`. A control reading it would not fire."""
        self.set_mode("explore")
        decision = self.run_hook(event("Write", file_path=str(self.dir / "src/main.rs"),
                                       content="x"))
        self.assertEqual(decision["permission"], "deny")


class TestThePermissionSets(ModeCase):
    def test_explore_writes_nothing(self) -> None:
        self.set_mode("explore")
        for target in ("src/main.rs", "aios/tasks/T-1.md", "README.md"):
            with self.subTest(target=target):
                self.assertEqual(self.write_to(target)["permission"], "deny")

    def test_verify_writes_nothing(self) -> None:
        self.set_mode("verify")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "deny")

    def test_plan_writes_state_but_never_source(self) -> None:
        self.set_mode("plan")
        self.assertEqual(self.write_to("aios/tasks/T-1.md")["permission"], "allow")
        self.assertEqual(self.write_to("aios/requirements/state.md")["permission"], "allow")
        self.assertEqual(self.write_to("aios/open-questions.md")["permission"], "allow")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "deny")

    def test_implement_writes_exactly_the_declared_touches(self) -> None:
        self.task("T-abc", ["src/**", "tests/test_thing.py"])
        self.set_mode("implement T-abc")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "allow")
        self.assertEqual(self.write_to("tests/test_thing.py")["permission"], "allow")
        self.assertEqual(self.write_to("aios/tasks/T-abc.md")["permission"], "deny")

    def test_implement_without_a_task_refuses_rather_than_permitting_everything(self) -> None:
        self.set_mode("implement")
        decision = self.write_to("src/main.rs")
        self.assertEqual(decision["permission"], "deny")
        self.assertIn("needs a task", decision["user_message"])

    def test_an_undefined_mode_refuses(self) -> None:
        """A typo in the mode file must not read as 'no mode', which permits everything."""
        self.set_mode("implemnt")
        decision = self.write_to("src/main.rs")
        self.assertEqual(decision["permission"], "deny")
        self.assertIn("not defined", decision["user_message"])

    def test_a_write_outside_the_repository_is_refused(self) -> None:
        self.set_mode("plan")
        elsewhere = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, elsewhere, True)
        decision = self.run_hook(event("Write", file_path=str(elsewhere / "x.md"),
                                       content="x"))
        self.assertEqual(decision["permission"], "deny")


class TestTheDuplicateCheckGatesImplementation(ModeCase):
    """M4-04. `aios start` was to be the moment the check happens; it does not exist, and the
    first write in implement mode is the same moment reached by a different route."""

    def test_implementation_cannot_begin_without_the_check(self) -> None:
        self.task("T-abc", ["src/**"], duplicate_check=None)
        self.set_mode("implement T-abc")
        decision = self.write_to("src/main.rs")
        self.assertEqual(decision["permission"], "deny")
        self.assertIn("duplicate_check", decision["user_message"])

    def test_an_empty_check_is_not_a_check(self) -> None:
        self.task("T-abc", ["src/**"], duplicate_check=["   "])
        self.set_mode("implement T-abc")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "deny")

    def test_nothing_found_is_a_complete_check(self) -> None:
        """It is worth as much as a hit. A control that only accepts hits teaches people to
        invent them."""
        self.task("T-abc", ["src/**"],
                  duplicate_check=["mode permission sets — nothing found; searched mode, "
                                   "permission, preToolUse"])
        self.set_mode("implement T-abc")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "allow")

    def test_the_refusal_says_who_to_ask_and_what_to_record(self) -> None:
        self.task("T-abc", ["src/**"], duplicate_check=None)
        self.set_mode("implement T-abc")
        message = self.write_to("src/main.rs")["agent_message"]
        self.assertIn("explorer", message)
        self.assertIn("nothing", message)

    def test_the_other_modes_do_not_require_it(self) -> None:
        """Planning is where the check gets recorded, so requiring it to plan is a deadlock."""
        self.set_mode("plan")
        self.assertEqual(self.write_to("aios/tasks/T-1.md")["permission"], "allow")


class TestTheDefault(ModeCase):
    def test_no_mode_file_permits_everything(self) -> None:
        """A template defaulting to refusal blocks a fresh clone before it is configured."""
        self.set_mode(None)
        self.assertEqual(self.write_to("src/main.rs")["permission"], "allow")

    def test_an_empty_mode_file_permits_everything(self) -> None:
        self.set_mode("")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "allow")

    def test_a_repository_without_the_config_is_not_governed(self) -> None:
        (self.dir / "aios" / "config.yml").unlink()
        self.set_mode("explore")
        self.assertEqual(self.write_to("src/main.rs")["permission"], "allow")


class TestTheRefusalExplainsItself(ModeCase):
    def test_it_names_the_mode_and_the_permitted_set(self) -> None:
        self.set_mode("plan")
        decision = self.write_to("src/main.rs")
        self.assertIn("plan", decision["user_message"])
        self.assertIn("aios/tasks/**", decision["user_message"])

    def test_it_offers_the_two_deliberate_ways_out(self) -> None:
        """Both are visible decisions. A refusal with no route out gets the hook deleted."""
        self.set_mode("plan")
        message = self.write_to("src/main.rs")["agent_message"]
        self.assertIn("Change the mode", message)
        self.assertIn("touches", message)


class TestThisRepository(unittest.TestCase):
    def test_the_modes_are_configured(self) -> None:
        import yaml
        config = yaml.safe_load((ROOT / "aios" / "config.yml").read_text(encoding="utf-8"))
        self.assertEqual(sorted(config["modes"]),
                         ["explore", "implement", "plan", "verify"])
        self.assertEqual(config["modes"]["implement"]["writes"], "touches")

    def test_the_mode_file_is_not_committed(self) -> None:
        """It is session state. Committing it would make one developer's mode everyone's."""
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
        self.assertIn(".aios-mode", ignored)

    def test_the_hook_reads_the_config_without_a_third_party_import(self) -> None:
        """A hook runs on whatever interpreter the editor has; a missing import would be a
        crash on every write, and the crash path is the one that produced the incident."""
        source = HOOK.read_text(encoding="utf-8")
        self.assertNotIn("import yaml", source)

    def test_the_hook_is_registered_for_write(self) -> None:
        hooks = json.loads((ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        entries = hooks["hooks"].get("preToolUse", [])
        self.assertTrue(any("check-mode" in entry["command"] for entry in entries),
                        "the control is written but not wired, which enforces nothing")


class TestTheHookDoesNotWaitForEndOfStream(unittest.TestCase):
    """The measured contract says the payload is CRLF-*terminated*, which says nothing about
    the pipe being closed. `read()` waits for EOF; if the caller holds the pipe open it waits
    forever, the timeout fires, and a failClosed hook turns that into every write refused.

    This is asserted structurally as well as behaviourally, because the behavioural version
    can only prove the hook returns — it cannot prove the next person will not change it back.
    """

    def test_the_hooks_read_a_line_rather_than_to_eof(self) -> None:
        for name in ("check-mode.py", "record-attempt.py"):
            with self.subTest(hook=name):
                source = (ROOT / "aios" / "bin" / "hooks" / name).read_text(encoding="utf-8")
                self.assertNotIn("stdin.buffer.read()", source)
                self.assertIn("stdin.buffer.readline()", source)

    def test_a_hook_returns_while_the_pipe_is_still_open(self) -> None:
        payload = {"tool_name": "Write", "tool_input": {"file_path": "a.md", "content": "x"},
                   "cursor_version": "3.13.21", "session_id": "s"}
        raw = "\ufeff".encode() + json.dumps(payload).encode() + b"\r\n"
        for name in ("check-mode.py", "record-attempt.py"):
            with self.subTest(hook=name):
                process = subprocess.Popen(
                    [sys.executable, str(ROOT / "aios" / "bin" / "hooks" / name)],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    cwd=str(ROOT))
                self.addCleanup(process.kill)
                process.stdin.write(raw)
                process.stdin.flush()  # deliberately not closed
                deadline = time.time() + 15
                while time.time() < deadline and process.poll() is None:
                    time.sleep(0.1)
                self.assertIsNotNone(process.poll(),
                                     f"{name} is still running with the pipe open; it would "
                                     f"hit the hook timeout and refuse the write")


class TestADefectMustNotBecomeAnOutage(unittest.TestCase):
    """The hook is registered failClosed, so an exception is not "the control did not apply" —
    it is every write in the editor refused until someone reads a stack trace. That has now
    happened three times here, which makes it a design defect rather than three accidents.
    Input parsing was already guarded; the decision was not."""

    def test_a_crash_while_deciding_allows_and_says_so(self) -> None:
        harness = (
            "import importlib.util, sys\n"
            f"spec = importlib.util.spec_from_file_location('cm', {str(HOOK)!r})\n"
            "m = importlib.util.module_from_spec(spec)\n"
            "spec.loader.exec_module(m)\n"
            "def boom(event):\n"
            "    raise RuntimeError('injected')\n"
            "m.decide = boom\n"
            "raise SystemExit(m.main())\n"
        )
        payload = {"tool_name": "Write", "tool_input": {"file_path": "a.md", "content": "x"},
                   "cursor_version": "3.13.21", "session_id": "s"}
        result = subprocess.run(
            [sys.executable, "-c", harness],
            input="\ufeff".encode() + json.dumps(payload).encode() + b"\r\n",
            capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        decision = json.loads(result.stdout.decode("utf-8"))
        self.assertEqual(decision["permission"], "allow")
        self.assertIn("enforced nothing", decision["agent_message"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
