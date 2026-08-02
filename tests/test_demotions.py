#!/usr/bin/env python3
"""Tests for the demotion counter.

Run: python -m unittest discover -s tests -v

M3-08's done condition is a boundary: the counter demotes on the third override and never on
the second. Most of what follows is that boundary approached from both sides — in count, and
in the width of the window.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-demotions.py"

CLEAN, VIOLATION, CANNOT_RUN = 0, 1, 2
TODAY = "2026-12-31"
START = dt.date(2026, 6, 1)

GATES = """\
gates:
  - id: quality.flaky
    title: An ordinary contract gate
    class: contract
    blocking: step
    workflow: hygiene.yml
    step: An ordinary contract gate

  - id: containment.secrets
    title: A security gate
    security: true
    class: contract
    blocking: step
    workflow: secrets.yml
    step: A security gate
"""

REASON = ("The vendored fixture holds a revoked credential the scanner cannot tell from a "
          "live one, and rotating it would invalidate the fixture entirely.")


class DemotionCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "incidents").mkdir(parents=True)
        (self.dir / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        (self.dir / "aios" / "gates.yml").write_text(GATES, encoding="utf-8")
        self.write_ledger([], [])

    def write_ledger(self, demotions: list, exempt: list) -> None:
        (self.dir / "aios" / "demotions.yml").write_text(
            yaml.safe_dump({"demotions": demotions, "exempt_crossings": exempt},
                           sort_keys=False), encoding="utf-8")

    def add_override(self, offset: int, gate: str = "quality.flaky") -> str:
        date = (START + dt.timedelta(days=offset)).isoformat()
        name = f"{date}-override-{gate.replace('.', '-')}-{offset}.md"
        (self.dir / "aios" / "incidents" / name).write_text(textwrap.dedent(f"""\
            ---
            override: {gate}
            date: {date}
            approved_by: N Ramesh
            reason: >-
              {REASON}
            ---

            # {date} — Override

            Detail of what was accepted.
            """), encoding="utf-8")
        return f"aios/incidents/{name}"

    def demote_in_registry(self, gate: str) -> None:
        text = (self.dir / "aios" / "gates.yml").read_text(encoding="utf-8")
        head, _, tail = text.partition(f"- id: {gate}\n")
        tail = tail.replace("class: contract", "class: ratchet", 1)
        (self.dir / "aios" / "gates.yml").write_text(f"{head}- id: {gate}\n{tail}",
                                                     encoding="utf-8")

    def check(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.dir), "--today", TODAY, *extra],
            capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def ledger(self) -> dict:
        return yaml.safe_load(
            (self.dir / "aios" / "demotions.yml").read_text(encoding="utf-8"))


class TestTheThreshold(DemotionCase):
    """The done condition: demotes on the third, never on the second."""

    def test_no_overrides_is_clean(self) -> None:
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)

    def test_one_override_does_not_demote(self) -> None:
        self.add_override(0)
        self.assertEqual(self.check()[0], CLEAN)

    def test_two_overrides_do_not_demote(self) -> None:
        self.add_override(0)
        self.add_override(5)
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)

    def test_the_third_override_demotes(self) -> None:
        self.add_override(0)
        self.add_override(5)
        self.add_override(10)
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("quality.flaky", out)

    def test_a_fourth_override_still_demotes(self) -> None:
        for offset in (0, 5, 10, 15):
            self.add_override(offset)
        self.assertEqual(self.check()[0], VIOLATION)


class TestTheWindow(DemotionCase):
    def test_three_inside_twenty_nine_days_demotes(self) -> None:
        for offset in (0, 1, 29):
            self.add_override(offset)
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)

    def test_three_spanning_exactly_thirty_days_does_not(self) -> None:
        """Thirty days apart is outside a thirty-day window, so the third does not join."""
        for offset in (0, 1, 30):
            self.add_override(offset)
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)

    def test_three_spread_far_apart_does_not_demote(self) -> None:
        for offset in (0, 90, 180):
            self.add_override(offset)
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)

    def test_a_later_cluster_of_three_demotes(self) -> None:
        """The window slides; it is not anchored to the first override ever recorded."""
        for offset in (0, 60, 120, 125, 130):
            self.add_override(offset)
        self.assertEqual(self.check()[0], VIOLATION)

    def test_the_verdict_does_not_depend_on_today(self) -> None:
        """A rule whose answer changes overnight, with nobody having touched anything, is one
        nobody can argue with in review."""
        for offset in (0, 5, 10):
            self.add_override(offset)
        first, _ = self.check("--today", "2026-07-01")
        second, _ = self.check("--today", "2030-01-01")
        self.assertEqual(first, second)
        self.assertEqual(first, VIOLATION)

    def test_two_gates_do_not_pool_their_overrides(self) -> None:
        self.add_override(0, "quality.flaky")
        self.add_override(1, "quality.flaky")
        self.add_override(2, "containment.secrets")
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)


class TestApplyAndRecord(DemotionCase):
    def cross_the_threshold(self) -> None:
        for offset in (0, 5, 10):
            self.add_override(offset)

    def test_apply_then_demoting_the_class_makes_it_clean(self) -> None:
        self.cross_the_threshold()
        self.assertEqual(self.check()[0], VIOLATION)
        code, out = self.check("--apply")
        self.assertEqual(code, CLEAN, out)
        self.demote_in_registry("quality.flaky")
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)

    def test_apply_records_what_a_reviewer_needs(self) -> None:
        self.cross_the_threshold()
        self.check("--apply")
        entry = self.ledger()["demotions"][0]
        self.assertEqual(entry["gate"], "quality.flaky")
        self.assertEqual(entry["from"], "contract")
        self.assertEqual(entry["to"], "ratchet")
        self.assertEqual(len(entry["triggered_by"]), 3)
        self.assertFalse(entry["closed"], "the report starts open for a human to close")
        self.assertIn("overridden", entry["report"])

    def test_apply_is_idempotent(self) -> None:
        self.cross_the_threshold()
        self.check("--apply")
        self.check("--apply")
        self.assertEqual(len(self.ledger()["demotions"]), 1)

    def test_recording_the_demotion_alone_is_not_enough(self) -> None:
        """The ledger entry without the class change leaves the gate blocking dishonestly."""
        self.cross_the_threshold()
        self.check("--apply")
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("still contract", out)

    def test_demoting_the_class_alone_is_not_enough(self) -> None:
        """The mirror of the test above, and the one the suite was missing.

        A gate quietly moved to ratchet with nothing in the ledger loses the only artefact
        that says why it stopped blocking. Every other test had the class still on contract,
        so that check masked this one and a mutation removing it survived.
        """
        self.cross_the_threshold()
        self.demote_in_registry("quality.flaky")
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("no entry exists in aios/demotions.yml", out)

    def test_a_demotion_nobody_earned_trips(self) -> None:
        """Otherwise the ledger is a way to switch off any gate by writing a line in it."""
        self.add_override(0)
        self.write_ledger([{"gate": "quality.flaky", "demoted_on": TODAY, "from": "contract",
                            "to": "ratchet", "triggered_by": [], "report": "x",
                            "closed": False}], [])
        self.demote_in_registry("quality.flaky")
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("nobody earned", out)

    def test_demoting_to_advisory_trips(self) -> None:
        self.cross_the_threshold()
        self.write_ledger([{"gate": "quality.flaky", "demoted_on": TODAY, "from": "contract",
                            "to": "advisory", "triggered_by": ["a", "b", "c"],
                            "report": "x", "closed": False}], [])
        self.demote_in_registry("quality.flaky")
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("not to anything weaker", out)

    def test_an_incomplete_ledger_entry_trips(self) -> None:
        self.cross_the_threshold()
        self.write_ledger([{"gate": "quality.flaky", "to": "ratchet"}], [])
        self.demote_in_registry("quality.flaky")
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("missing required field", out)


class TestTheSecurityExemption(DemotionCase):
    def cross(self) -> None:
        for offset in (0, 5, 10):
            self.add_override(offset, "containment.secrets")

    def test_a_security_gate_crossing_must_be_recorded(self) -> None:
        """Exemption from demotion is not exemption from being noticed."""
        self.cross()
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("exempt_crossings", out)

    def test_apply_records_the_crossing_without_demoting(self) -> None:
        self.cross()
        self.check("--apply")
        ledger = self.ledger()
        self.assertEqual(ledger["demotions"], [],
                         "a security gate must never be demoted")
        self.assertEqual(ledger["exempt_crossings"][0]["gate"], "containment.secrets")
        self.assertFalse(ledger["exempt_crossings"][0]["closed"])
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)

    def test_a_demoted_security_gate_trips(self) -> None:
        """The failure mode that matters: an important control quietly made optional."""
        self.cross()
        self.check("--apply")
        self.demote_in_registry("containment.secrets")
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("must not have been demoted", out)

    def test_an_exempt_crossing_nobody_earned_trips(self) -> None:
        self.write_ledger([], [{"gate": "containment.secrets", "noticed_on": TODAY,
                                "count": 3, "closed": False}])
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("never crossed", out)

    def test_a_non_security_gate_cannot_claim_exemption(self) -> None:
        for offset in (0, 5, 10):
            self.add_override(offset)
        self.write_ledger([], [{"gate": "quality.flaky", "noticed_on": TODAY,
                                "count": 3, "closed": False}])
        code, out = self.check()
        self.assertEqual(code, VIOLATION, out)
        self.assertIn("not in the security subset", out)


class TestAgreementWithTheOverrideGate(DemotionCase):
    def test_a_demoted_gate_does_not_invalidate_its_own_override_records(self) -> None:
        """The two checks must not contradict each other.

        Three overrides demote a gate to Ratchet; the override gate accepts only Contract
        gates; so without this the very records that caused the demotion become violations.
        A record is a statement about the past, judged against what the gate was.
        """
        for offset in (0, 5, 10):
            self.add_override(offset)
        self.check("--apply")
        self.demote_in_registry("quality.flaky")
        result = subprocess.run(
            [sys.executable, str(ROOT / ".github" / "scripts" / "check-overrides.py"),
             "--root", str(self.dir), "--today", TODAY], capture_output=True, text=True)
        self.assertEqual(result.returncode, CLEAN, result.stdout + result.stderr)


class TestCannotRun(DemotionCase):
    def test_a_missing_ledger_cannot_run(self) -> None:
        (self.dir / "aios" / "demotions.yml").unlink()
        self.assertEqual(self.check()[0], CANNOT_RUN)

    def test_an_unknown_tier_cannot_run(self) -> None:
        (self.dir / "aios" / "config.yml").write_text("tier: whenever\n", encoding="utf-8")
        self.assertEqual(self.check()[0], CANNOT_RUN)


class TestThisRepository(unittest.TestCase):
    def test_no_gate_here_is_being_overridden_routinely(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(ROOT)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, CLEAN, result.stdout + result.stderr)

    def test_the_security_subset_is_marked_in_the_registry(self) -> None:
        document = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        secure = {entry["id"] for entry in document["gates"] if entry.get("security")}
        for expected in ("containment.secrets", "containment.test_integrity",
                         "containment.scope", "process.overrides"):
            self.assertIn(expected, secure)

    def test_the_override_gate_itself_is_exempt(self) -> None:
        """A demotable override gate would be a way around every other gate at once."""
        document = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        entry = [e for e in document["gates"] if e["id"] == "process.overrides"][0]
        self.assertTrue(entry.get("security"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
