#!/usr/bin/env python3
"""Tests for override recording.

Run: python -m unittest discover -s tests -v

These build real repositories with real commits. The range half of the gate reads commit
messages and compares a file against its state at the base ref, and neither can be faked with
a directory of loose files — which is the same reason the secrets scanner's history tests
commit before they assert.
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
SCRIPT = ROOT / ".github" / "scripts" / "check-overrides.py"

CLEAN, VIOLATION, CANNOT_RUN = 0, 1, 2
TODAY = "2026-07-31"

GATES = """\
gates:
  - id: quality.secrets
    title: No credential in the working tree or history
    class: contract
    blocking: step
    workflow: secrets.yml
    step: No credential in the working tree or history

  - id: quality.complexity
    title: Complexity report
    class: advisory
    blocking: continue
    workflow: hygiene.yml
    step: Complexity report
"""

REASON = ("The vendored fixture contains a revoked test credential that the scanner cannot "
          "distinguish from a live one, and rotating it would invalidate the fixture.")


BODY = "# 2026-07-31 — Override\n\nFull detail of what was accepted and why.\n"


def record(gate: str = "quality.secrets", date: str = TODAY, approved_by: str = "N Ramesh",
           reason: str = REASON, body: str = BODY) -> str:
    frontmatter = textwrap.dedent(f"""\
        ---
        override: {gate}
        date: {date}
        approved_by: {approved_by}
        reason: >-
          {reason}
        ---
        """)
    return f"{frontmatter}\n{body}"


class OverrideCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "incidents").mkdir(parents=True)
        (self.dir / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        (self.dir / "aios" / "gates.yml").write_text(GATES, encoding="utf-8")

    def write(self, name: str, text: str) -> None:
        (self.dir / "aios" / "incidents" / name).write_text(text, encoding="utf-8")

    def check(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.dir), "--today", TODAY, *extra],
            capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    # -- git helpers, used only by the range tests --------------------------------------
    def git(self, *arguments: str) -> str:
        result = subprocess.run(["git", "-C", str(self.dir), *arguments],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def init_repo(self) -> None:
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "Test")
        self.git("add", "-A")
        self.git("commit", "-qm", "base")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", message)


class TestRecordShape(OverrideCase):
    def test_a_repository_with_no_overrides_is_clean(self) -> None:
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)
        self.assertIn("0 record(s)", out)

    def test_an_ordinary_incident_is_not_an_override(self) -> None:
        """Most incidents carry no frontmatter. Absence must be silence, not a finding."""
        self.write("2026-07-31-something.md", "# 2026-07-31 — A normal incident\n\nProse.\n")
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)
        self.assertIn("0 record(s)", out)

    def test_a_well_formed_record_passes(self) -> None:
        self.write("2026-07-31-override.md", record())
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)
        self.assertIn("1 record(s)", out)

    def test_each_required_field_is_required(self) -> None:
        for field in ("date", "approved_by", "reason"):
            with self.subTest(field=field):
                text = record()
                if field == "reason":
                    text = text.replace(f"reason: >-\n  {REASON}\n", "")
                else:
                    line = [ln for ln in text.splitlines() if ln.startswith(f"{field}:")][0]
                    text = text.replace(line + "\n", "")
                self.write("2026-07-31-override.md", text)
                code, out = self.check()
                self.assertEqual(code, VIOLATION, out)
                self.assertIn(field, out)

    def test_frontmatter_without_an_override_key_is_not_an_override(self) -> None:
        """`override` is what identifies the record, so its absence cannot be a violation.

        Treating it as one would make every incident that ever grows frontmatter — for any
        other purpose — into a malformed override.
        """
        self.write("2026-07-31-something.md",
                   "---\nseverity: low\n---\n\n# Not an override\n\nProse.\n")
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)
        self.assertIn("0 record(s)", out)

    def test_a_thin_reason_is_not_a_reason(self) -> None:
        self.write("2026-07-31-override.md", record(reason="because"))
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("not a reason", out)

    def test_a_record_with_no_body_trips(self) -> None:
        self.write("2026-07-31-override.md", record(body=""))
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("no body", out)

    def test_a_future_date_trips(self) -> None:
        self.write("2026-07-31-override.md", record(date="2027-01-01"))
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("in the future", out)

    def test_a_malformed_date_trips(self) -> None:
        self.write("2026-07-31-override.md", record(date="last Tuesday"))
        self.assertEqual(self.check()[0], VIOLATION)

    def test_broken_frontmatter_is_reported_not_ignored(self) -> None:
        self.write("2026-07-31-override.md", "---\noverride: [unclosed\n---\n\nBody.\n")
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)


class TestTheGateBeingOverridden(OverrideCase):
    def test_an_unknown_gate_trips(self) -> None:
        self.write("2026-07-31-override.md", record(gate="quality.imaginary"))
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("not in aios/gates.yml", out)

    def test_overriding_a_non_contract_gate_trips(self) -> None:
        """Only a Contract gate blocks, so only a Contract gate can be overridden.

        An override of an Advisory check is a record of nothing, and it would still feed the
        demotion counter — inflating the count on a gate that never stopped anybody.
        """
        self.write("2026-07-31-override.md", record(gate="quality.complexity"))
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("not contract", out)

    def test_class_is_resolved_at_the_configured_tier(self) -> None:
        (self.dir / "aios" / "gates.yml").write_text(
            "gates:\n  - id: quality.sast\n    title: SAST\n"
            "    class:\n      prototype: advisory\n      internal: ratchet\n"
            "      production: contract\n      regulated: contract\n"
            "    blocking: script\n    workflow: sast.yml\n    step: SAST\n", encoding="utf-8")
        self.write("2026-07-31-override.md", record(gate="quality.sast"))
        self.assertEqual(self.check("--tier", "prototype")[0], VIOLATION)
        self.assertEqual(self.check("--tier", "production")[0], CLEAN)


class TestRangeAgreement(OverrideCase):
    """Both directions: a claim without a record, and a record without a claim."""

    def test_a_trailer_with_no_record_is_an_unrecorded_bypass(self) -> None:
        self.init_repo()
        (self.dir / "note.txt").write_text("work\n", encoding="utf-8")
        self.commit("Do the work\n\nOverride: quality.secrets\nhuman: N Ramesh")
        code, out = self.check("--range", "main~1..main")
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("unrecorded bypass", out)

    def test_a_record_with_no_trailer_is_smuggled_in(self) -> None:
        self.init_repo()
        self.write("2026-07-31-override.md", record())
        self.commit("Add a record quietly\n\nhuman: N Ramesh")
        code, out = self.check("--range", "main~1..main")
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("smuggled in", out)

    def test_a_matching_pair_passes(self) -> None:
        self.init_repo()
        self.write("2026-07-31-override.md", record())
        self.commit("Accept the risk\n\nOverride: quality.secrets\nhuman: N Ramesh")
        code, out = self.check("--range", "main~1..main")
        self.assertEqual(code, CLEAN, out)

    def test_an_override_with_no_human_trailer_trips(self) -> None:
        self.init_repo()
        self.write("2026-07-31-override.md", record())
        self.commit("Accept the risk\n\nOverride: quality.secrets")
        code, out = self.check("--range", "main~1..main")
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("human:", out)


class TestTheListCannotBeEdited(OverrideCase):
    """06 §1: the agent cannot edit the override list.

    Enforceable because it is a property of the diff rather than of who produced it.
    """

    def commit_a_record(self) -> None:
        self.init_repo()
        self.write("2026-07-31-override.md", record())
        self.commit("Accept the risk\n\nOverride: quality.secrets\nhuman: N Ramesh")

    def test_editing_an_existing_record_trips(self) -> None:
        self.commit_a_record()
        self.write("2026-07-31-override.md", record(reason=REASON.replace("revoked", "live")))
        self.commit("Adjust wording")
        code, out = self.check("--range", "main~1..main")
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("modified or deleted", out)

    def test_deleting_an_existing_record_trips(self) -> None:
        self.commit_a_record()
        (self.dir / "aios" / "incidents" / "2026-07-31-override.md").unlink()
        self.commit("Tidy up")
        code, out = self.check("--range", "main~1..main")
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("modified or deleted", out)

    def test_an_unrelated_incident_may_still_be_edited(self) -> None:
        """Ordinary incidents are not frozen; only override records are."""
        self.init_repo()
        self.write("2026-07-31-normal.md", "# Normal\n\nFirst draft.\n")
        self.commit("Record an incident")
        self.write("2026-07-31-normal.md", "# Normal\n\nSecond draft with more detail.\n")
        self.commit("Expand it")
        code, out = self.check("--range", "main~1..main")
        self.assertEqual(code, CLEAN, out)


class TestListOutput(OverrideCase):
    def test_list_emits_what_the_demotion_counter_needs(self) -> None:
        """M3-08 counts three overrides of one gate in thirty days, so it needs gate and date.

        Emitting it here means that counter never re-parses this format, and the two cannot
        drift into disagreeing about what an override is.
        """
        import json

        self.write("2026-07-31-override.md", record())
        code, out = self.check("--list")
        self.assertEqual(code, CLEAN, out)
        payload = json.loads(out[out.index("["):out.index("]") + 1])
        self.assertEqual(payload[0]["gate"], "quality.secrets")
        self.assertEqual(payload[0]["date"], TODAY)
        self.assertEqual(payload[0]["approved_by"], "N Ramesh")


class TestCannotRun(OverrideCase):
    def test_a_missing_gate_registry_cannot_run(self) -> None:
        (self.dir / "aios" / "gates.yml").unlink()
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)

    def test_an_unknown_tier_cannot_run(self) -> None:
        (self.dir / "aios" / "config.yml").write_text("tier: whenever\n", encoding="utf-8")
        self.assertEqual(self.check()[0], CANNOT_RUN)


class TestThisRepository(unittest.TestCase):
    def test_this_repository_has_consistent_overrides(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, CLEAN, result.stdout + result.stderr)

    def test_the_check_is_registered_as_a_gate(self) -> None:
        import yaml

        document = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        ids = {entry.get("id") for entry in document.get("gates") or []}
        self.assertIn("process.overrides", ids)


if __name__ == "__main__":
    unittest.main(verbosity=2)
