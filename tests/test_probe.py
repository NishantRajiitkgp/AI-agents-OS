#!/usr/bin/env python3
"""Tests for the adapter probe's setup and teardown (M4-12).

Run: python -m unittest discover -s tests -v

Nearly all of these are about teardown, which is where the risk is. Staging is easy to get
right and easy to check by eye. Teardown runs against `AGENTS.md` and `.claude/`, both of which
are real now and were not when M0 ran, and a marker left in the always-on instruction layer is
the exact class of silent staleness this repository exists to catch.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "aios" / "bin" / "probe" / "probe-adapters.py"
MANIFEST = ".aios-probe.json"

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProbeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir()
        # The paths the probe appends to rather than creates. Their exact bytes are what
        # teardown has to bring back.
        (self.dir / "AGENTS.md").write_text("# Real instructions\n\nLine two.\n",
                                            encoding="utf-8")
        (self.dir / ".cursor" / "rules").mkdir(parents=True)
        (self.dir / ".cursor" / "rules" / "real.mdc").write_text("keep me\n", encoding="utf-8")
        (self.dir / ".claude" / "agents").mkdir(parents=True)
        (self.dir / ".claude" / "agents" / "explorer.md").write_text("real\n",
                                                                    encoding="utf-8")

    def run_probe(self, action: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), action, "--root", str(self.dir)],
            capture_output=True)
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")

    def manifest(self) -> dict:
        return json.loads((self.dir / MANIFEST).read_text(encoding="utf-8"))


class TestStaging(ProbeCase):
    def test_staging_writes_a_manifest_and_the_markers(self) -> None:
        code, out = self.run_probe("stage")
        self.assertEqual(code, PASS, out)
        self.assertTrue((self.dir / MANIFEST).is_file())
        self.assertEqual(len(self.manifest()["markers"]), 9)

    def test_every_marker_is_unique(self) -> None:
        """Markers are per label, not per run, so a reported marker names the file it came
        from. One shared marker would tell you a location was read but not which."""
        self.run_probe("stage")
        values = list(self.manifest()["markers"].values())
        self.assertEqual(len(values), len(set(values)))

    def test_two_runs_do_not_share_markers(self) -> None:
        """A repeated marker cannot be told apart from a tool remembering the last run."""
        self.run_probe("stage")
        first = set(self.manifest()["markers"].values())
        self.run_probe("teardown")
        self.run_probe("stage")
        self.assertFalse(first & set(self.manifest()["markers"].values()))

    def test_the_decoy_has_no_file(self) -> None:
        """The control that makes a null result trustworthy. If it ever gains a file it stops
        detecting invention and the whole matrix becomes unfalsifiable."""
        self.run_probe("stage")
        manifest = self.manifest()
        self.assertNotIn(manifest["decoy"], manifest["markers"])
        blob = "".join(p.read_text(encoding="utf-8", errors="replace")
                       for p in self.dir.rglob("*") if p.is_file() and p.name != MANIFEST)
        self.assertNotIn("AIOS-PROBE-DECOY", blob)

    def test_an_existing_file_is_appended_to_not_replaced(self) -> None:
        self.run_probe("stage")
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("# Real instructions", text)
        self.assertIn(self.manifest()["markers"]["ROOTMD"], text)

    def test_staging_twice_is_refused(self) -> None:
        """Staging over a staged tree would record the *staged* bytes as the baseline, and
        teardown would then restore the marker instead of removing it — permanently."""
        self.run_probe("stage")
        code, out = self.run_probe("stage")
        self.assertEqual(code, COULD_NOT_RUN)
        self.assertIn("already staged", out)

    def test_the_staged_command_file_satisfies_the_commands_gate(self) -> None:
        """A staged tree that fails the repository's own gates is indistinguishable from a
        broken one, and the person who finds it has no way to tell which they are looking at."""
        self.run_probe("stage")
        shutil.copytree(ROOT / ".github" / "scripts", self.dir / ".github" / "scripts")
        result = subprocess.run(
            [sys.executable, str(self.dir / ".github" / "scripts" / "check-commands.py"),
             "--dir", str(self.dir)], capture_output=True)
        self.assertEqual(result.returncode, PASS,
                         (result.stdout + result.stderr).decode("utf-8", "replace"))

    def test_nothing_staged_announces_the_probe(self) -> None:
        """M0 recorded the confound: an announcement in AGENTS.md was read by sessions, which
        then narrated their compliance. That measures willingness to perform, not discovery."""
        self.run_probe("stage")
        text = (self.dir / "AGENTS.md").read_text(encoding="utf-8").lower()
        for word in ("probe", "measur", "experiment", "test"):
            self.assertNotIn(word, text.replace("aios-probe-rootmd", ""))


class TestTeardown(ProbeCase):
    def test_every_path_returns_to_its_original_bytes(self) -> None:
        before = {p: sha(p) for p in self.dir.rglob("*") if p.is_file()}
        self.run_probe("stage")
        code, out = self.run_probe("teardown")
        self.assertEqual(code, PASS, out)
        after = {p: sha(p) for p in self.dir.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_the_created_files_are_gone(self) -> None:
        self.run_probe("stage")
        self.run_probe("teardown")
        for relative in ("probe-nested", ".claude/skills/aios-probe",
                         ".claude/commands/aios-probe.md",
                         ".cursor/rules/aios-probe-always.mdc"):
            self.assertFalse((self.dir / relative).exists(), relative)

    def test_a_real_neighbour_in_a_shared_directory_survives(self) -> None:
        """`.cursor/rules/` holds no-presumed-stack.mdc and `.claude/agents/` holds the
        explorer. The M0 teardown could delete directories wholesale; this one cannot."""
        self.run_probe("stage")
        self.run_probe("teardown")
        self.assertTrue((self.dir / ".cursor" / "rules" / "real.mdc").is_file())
        self.assertTrue((self.dir / ".claude" / "agents" / "explorer.md").is_file())

    def test_the_manifest_is_removed_on_success(self) -> None:
        self.run_probe("stage")
        self.run_probe("teardown")
        self.assertFalse((self.dir / MANIFEST).exists())

    def test_teardown_without_a_manifest_could_not_run(self) -> None:
        """Not a pass. Reporting success for a teardown that had nothing to work from would
        let a staged run be declared clean by a command that never looked at it."""
        code, out = self.run_probe("teardown")
        self.assertEqual(code, COULD_NOT_RUN)

    def test_a_marker_left_behind_fails_loudly(self) -> None:
        """The failure mode being defended against: teardown reporting success while the
        always-on instruction file still carries a marker."""
        self.run_probe("stage")
        manifest = self.manifest()
        for entry in manifest["files"]:
            if entry["path"] == "AGENTS.md":
                entry["original_base64"] = entry["original_base64"][:-4] + "AAAA"
        (self.dir / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        code, out = self.run_probe("teardown")
        self.assertEqual(code, FAIL)
        self.assertIn("original bytes", out)

    def test_a_failed_teardown_keeps_the_manifest(self) -> None:
        """So it can be retried. Deleting it would strand the staged files with nothing left
        that knows what they were."""
        self.run_probe("stage")
        manifest = self.manifest()
        for entry in manifest["files"]:
            if entry["path"] == "AGENTS.md":
                entry["original_sha256"] = "0" * 64
        (self.dir / MANIFEST).write_text(json.dumps(manifest), encoding="utf-8")
        self.run_probe("teardown")
        self.assertTrue((self.dir / MANIFEST).is_file())

    def test_an_edit_made_during_the_probe_is_reported(self) -> None:
        """Silently discarding it would make the probe capable of destroying work while
        reporting success."""
        self.run_probe("stage")
        (self.dir / "AGENTS.md").write_text("someone edited this\n", encoding="utf-8")
        code, out = self.run_probe("teardown")
        self.assertEqual(code, FAIL)
        self.assertIn("edited after staging", out)

    def test_a_directory_that_existed_before_is_not_removed(self) -> None:
        self.run_probe("stage")
        self.run_probe("teardown")
        self.assertTrue((self.dir / ".claude").is_dir())
        self.assertTrue((self.dir / ".cursor" / "rules").is_dir())


class TestStatus(ProbeCase):
    def test_status_lists_what_is_staged(self) -> None:
        self.run_probe("stage")
        code, out = self.run_probe("status")
        self.assertEqual(code, PASS)
        self.assertIn("AGENTS.md", out)
        self.assertIn("appended", out)
        self.assertIn("created", out)

    def test_status_says_the_tree_is_not_committable(self) -> None:
        """Staging genuinely raises the always-on count. Someone finding a staged tree needs
        to know the ratchet is reading high on purpose."""
        self.run_probe("stage")
        _, out = self.run_probe("status")
        self.assertIn("always-on", out)

    def test_status_notices_a_file_that_vanished(self) -> None:
        self.run_probe("stage")
        (self.dir / ".claude" / "commands" / "aios-probe.md").unlink()
        _, out = self.run_probe("status")
        self.assertIn("MISSING", out)

    def test_status_without_a_manifest_could_not_run(self) -> None:
        self.assertEqual(self.run_probe("status")[0], COULD_NOT_RUN)


class TestThisRepository(unittest.TestCase):
    def test_the_prompt_names_the_command_rather_than_manual_steps(self) -> None:
        """M4-12 is done when the quarterly re-run is one command plus the three protocols."""
        text = (ROOT / "aios" / "probe" / "prompt.md").read_text(encoding="utf-8") \
            if (ROOT / "aios" / "probe" / "prompt.md").exists() \
            else (ROOT / "aios" / "bin" / "probe" / "prompt.md").read_text(encoding="utf-8")
        self.assertIn("probe-adapters", text)
        self.assertNotIn("Remove-Item -LiteralPath", text)

    def test_the_manifest_is_not_committed(self) -> None:
        self.assertIn(MANIFEST, (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_no_run_is_staged_in_this_repository(self) -> None:
        """A committed manifest would mean a probe was left staged, which is the state where
        AGENTS.md carries a marker."""
        self.assertFalse((ROOT / MANIFEST).exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
