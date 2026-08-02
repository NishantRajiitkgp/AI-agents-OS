#!/usr/bin/env python3
"""Tests for the three layers protecting the paths outside the agent's write scope.

M2-01 CODEOWNERS, M2-03 the generated tool deny lists, M2-04 the local hooks, and M2-10 the
deny-list hook now that it is registered against a measured event shape.

The three layers are tested separately and asserted about jointly, because the interesting
property is not that each works — it is that they disagree in a known direction. The regex
layer is precise and local, the prefix layer is coarse and local, and only the review
requirement is neither local nor removable by the party it constrains. A test suite that
treated them as interchangeable would be encoding the exact mistake the design warns about.

@satisfies STATE-6  malformed state is refused at the boundary — the generator refuses a
                    prefix map that has drifted from the pattern list rather than emitting a
                    file that is quietly missing rules
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"
HOOKS = ROOT / "aios" / "bin" / "hooks"


def load(path: Path, name: str):
    sys.path.insert(0, str(path.parent))
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load(SCRIPTS / "generate-deny-lists.py", "generate_deny_lists")
codeowners = load(SCRIPTS / "check-codeowners.py", "check_codeowners")
trailer = load(SCRIPTS / "check-human-trailer.py", "check_human_trailer")

# Imported, not loaded by path. Loading it by path builds a second module object with its own
# CouldNotRun class, and `assertRaises` against that one never matches the exception the
# scripts actually raise — the test passes the exception straight through and reports an
# error, which looks like a broken script and is a broken test.
from aios_state import CouldNotRun  # noqa: E402


class TestTheGeneratedDenyList(unittest.TestCase):
    """M2-03. One source, two consumers, no inference."""

    def test_a_pattern_with_no_declared_prefix_is_refused(self):
        with self.assertRaises(CouldNotRun) as caught:
            generator.deny_array({"deny_commands": ["rm\\s+-rf", "curl\\s+.*"],
                                  "deny_command_prefixes": {"rm\\s+-rf": ["rm -rf:*"]}})
        self.assertIn("no entry in deny_command_prefixes", str(caught.exception))

    def test_a_prefix_for_a_deleted_pattern_is_refused(self):
        with self.assertRaises(CouldNotRun) as caught:
            generator.deny_array({"deny_commands": [],
                                  "deny_command_prefixes": {"gone": ["gone:*"]}})
        self.assertIn("no longer in deny_commands", str(caught.exception))

    def test_an_empty_prefix_list_is_reported_not_dropped(self):
        """The honest answer for a pipeline is that no prefix expresses it.

        What must not happen is that it vanishes. The coverage difference between the two
        tools is a property of the system, and it belongs in the artifact rather than in the
        head of whoever last compared the files.
        """
        entries, gaps = generator.deny_array({
            "deny_commands": ["rm\\s+-rf", "curl.*\\|.*sh"],
            "deny_command_prefixes": {"rm\\s+-rf": ["rm -rf:*"], "curl.*\\|.*sh": []}})
        self.assertEqual(entries, ["Bash(rm -rf:*)"])
        self.assertEqual(gaps, ["curl.*\\|.*sh"])

    def test_two_patterns_widening_to_one_prefix_say_it_once(self):
        entries, _ = generator.deny_array({
            "deny_commands": ["rm.*-r.*-f", "rm.*-f.*-r"],
            "deny_command_prefixes": {"rm.*-r.*-f": ["rm -rf:*"], "rm.*-f.*-r": ["rm -rf:*"]}})
        self.assertEqual(entries, ["Bash(rm -rf:*)"])

    def test_reads_are_not_derived_from_commands(self):
        entries, _ = generator.deny_array({
            "deny_commands": [], "deny_command_prefixes": {}, "deny_reads": [".env"]})
        self.assertEqual(entries, ["Read(.env)"])

    def test_this_repository_is_in_sync(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "generate-deny-lists.py")],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)

    def test_the_checker_cannot_make_itself_pass(self):
        """`--write` is a separate mode, which is the whole point of a generated file.

        A check that regenerates before comparing always passes, and would have caught none of
        the drift it exists to catch.
        """
        source = (SCRIPTS / "generate-deny-lists.py").read_text(encoding="utf-8")
        checking = source.split("if args.write:")[1].split("return PASS")[1]
        self.assertNotIn("write_text", checking)


class TestCodeowners(unittest.TestCase):
    """M2-01. The only layer the constrained party does not control."""

    def test_the_placeholder_is_refused(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "check-codeowners.py")],
                             cwd=ROOT, capture_output=True, text=True)
        text = out.stdout + out.stderr
        if "@OWNER-PLACEHOLDER" in (ROOT / ".github" / "CODEOWNERS").read_text(
                encoding="utf-8"):
            self.assertEqual(out.returncode, 1)
            self.assertIn("does not reject an owner it cannot resolve", text)
        else:  # a real handle has been filled in; then it must pass outright
            self.assertEqual(out.returncode, 0, text)

    def test_every_protected_path_is_covered(self):
        """The coverage half must pass regardless of the placeholder.

        Asserted on the message rather than the exit code, because while the placeholder is
        present the exit code is 1 for a different reason and would hide this.
        """
        out = subprocess.run([sys.executable, str(SCRIPTS / "check-codeowners.py")],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertNotIn("and CODEOWNERS does not cover it", out.stdout + out.stderr)

    def test_a_directory_rule_covers_what_is_under_it(self):
        self.assertTrue(codeowners.covers("/aios/bin/", "aios/bin/**"))
        self.assertTrue(codeowners.covers("/.github/", "aios/bin/**") is False)

    def test_an_owner_that_is_not_a_handle_is_refused(self):
        parsed = codeowners.rules("/tests/ someone@example.com\n")
        self.assertFalse(codeowners.OWNER.match(parsed[0][1][0]))

    def test_a_rule_with_no_owner_is_refused(self):
        """Last-match-wins means an ownerless line silently unprotects a path."""
        parsed = codeowners.rules("/aios/bin/ @a\n/aios/bin/\n")
        self.assertEqual(parsed[-1][1], [])


class TestTheHumanTrailer(unittest.TestCase):
    """M2-04. The layer that is removed by the third day if it is slow or wrong."""

    def test_a_protected_path_needs_the_trailer(self):
        self.assertEqual(
            trailer.protected(["aios/bin/x.py", "README.md"], ["aios/bin/**"]),
            ["aios/bin/x.py"])

    def test_an_unprotected_change_is_not_asked_for_one(self):
        self.assertEqual(trailer.protected(["README.md"], ["aios/bin/**", "tests/**"]), [])

    def test_a_bare_glob_matches_anywhere(self):
        self.assertEqual(
            trailer.protected(["src/deep/thing_test.py"], ["**/*_test.*"]),
            ["src/deep/thing_test.py"])

    def test_a_trivial_name_is_not_a_name(self):
        self.assertIsNone(
            next((m for m in [trailer.TRAILER.search("Human: x")]
                  if m and len(m.group(1).strip()) >= trailer.MINIMUM_NAME), None))

    def test_the_key_is_matched_as_git_matches_it(self):
        for form in ("Human: N R", "human: N R", "HUMAN: N R"):
            with self.subTest(form=form):
                self.assertIsNotNone(trailer.TRAILER.search(f"subject\n\n{form}"))

    def test_it_is_not_found_mid_line(self):
        """`the human: someone` in a body is prose, not a trailer."""
        self.assertIsNone(trailer.TRAILER.search("asked the human: someone else"))


class TestTheDenyHook(unittest.TestCase):
    """M2-10. Registered at last, against the shape that was measured."""

    def event(self, payload: dict) -> tuple[int, dict]:
        out = subprocess.run([sys.executable, str(HOOKS / "deny-commands.py")],
                             cwd=ROOT, capture_output=True,
                             input=b"\xef\xbb\xbf" + json.dumps(payload).encode() + b"\r\n",
                             env={**os.environ, "CURSOR_PROJECT_DIR": str(ROOT)})
        line = out.stdout.decode("utf-8", "replace").strip().splitlines()
        return out.returncode, json.loads(line[0]) if line else {}

    def test_the_measured_pretooluse_shape_is_read(self):
        code, decision = self.event({"tool_name": "Shell", "cursor_version": "3.13",
                                     "tool_input": {"command": "git push --force"}})
        self.assertEqual(code, 0)
        self.assertEqual(decision["permission"], "deny")

    def test_the_documented_beforeshell_shape_is_still_read(self):
        """Both, so that re-registering it cannot silently make it allow everything."""
        _, decision = self.event({"command": "git push --force", "cursor_version": "3.13"})
        self.assertEqual(decision["permission"], "deny")

    def test_an_ordinary_command_runs(self):
        _, decision = self.event({"tool_name": "Shell", "cursor_version": "3.13",
                                  "tool_input": {"command": "git status"}})
        self.assertEqual(decision["permission"], "allow")

    def test_it_reads_a_line_rather_than_to_end_of_stream(self):
        """The hang that caused an outage, asserted structurally.

        `read()` waits for EOF and Cursor does not close the pipe, so the hook times out and
        is reported as a crashed process. There is no unit test for "returns promptly" that is
        not itself a race, so the contract is asserted on the source.
        """
        source = (HOOKS / "deny-commands.py").read_text(encoding="utf-8")
        self.assertIn("readline()", source)
        self.assertNotIn("sys.stdin.buffer.read()", source)
        self.assertNotIn("json.load(sys.stdin)", source)

    def test_it_allows_when_it_cannot_decide(self):
        """The reversal M2-10 was forced into, and the reason it is not an oversight.

        A Shell-matched hook that denies on failure removes the terminal that would fix it.
        Measured, not predicted: a half-written config.yml did exactly that. The layer is
        Advisory (ADR-012), so it is not worth a repository nobody can repair.
        """
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "aios"
            broken.mkdir()
            (broken / "config.yml").write_text("deny_commands: [", encoding="utf-8")
            out = subprocess.run(
                [sys.executable, str(HOOKS / "deny-commands.py")],
                cwd=tmp, capture_output=True,
                input=b'{"tool_name":"Shell","tool_input":{"command":"git status"}}\n',
                env={**os.environ, "CURSOR_PROJECT_DIR": tmp})
            decision = json.loads(out.stdout.decode("utf-8", "replace").splitlines()[0])
            self.assertEqual(decision["permission"], "allow")

    def test_it_is_registered_in_both_tools(self):
        cursor = json.loads((ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8"))
        entries = [h for h in cursor["hooks"]["preToolUse"] if "deny-commands" in h["command"]]
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["matcher"], "Shell")
        self.assertFalse(entries[0]["failClosed"], "see the comment in hooks.json")

        claude = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        commands = [h["command"] for group in claude["hooks"]["PreToolUse"]
                    for h in group["hooks"]]
        self.assertTrue(any("deny-commands" in c for c in commands))

    def test_both_tools_point_at_one_implementation(self):
        """M4-07's property, re-asserted for the entry M2-10 added.

        Two copies of a deny list drift, and the one nobody is looking at goes stale.
        """
        cursor = (ROOT / ".cursor" / "hooks.json").read_text(encoding="utf-8")
        claude = (ROOT / ".claude" / "settings.json").read_text(encoding="utf-8")
        for text in (cursor, claude):
            self.assertIn("aios/bin/hooks/deny-commands.py", text)


class TestTheLayersDisagreeInAKnownDirection(unittest.TestCase):
    def test_the_prefix_layer_is_never_narrower_than_the_regex_layer(self):
        """Widening is the safe direction; narrowing is a silent hole.

        Checked as a property of the declared map rather than by matching commands: a prefix
        that is a strict extension of what the regex names would refuse fewer commands, and
        that is the one direction a coarse matcher must not go.
        """
        sys.path.insert(0, str(SCRIPTS))
        from aios_state import load_config
        config = load_config()
        for regex, prefixes in config["deny_command_prefixes"].items():
            for prefix in prefixes:
                head = prefix.split(":")[0].split()[0]
                with self.subTest(regex=regex, prefix=prefix):
                    self.assertIn(head.lower().replace("-", ""),
                                  regex.lower().replace("\\s+", "").replace("-", ""),
                                  f"{prefix!r} names a command {regex!r} does not")


if __name__ == "__main__":
    unittest.main(verbosity=2)
