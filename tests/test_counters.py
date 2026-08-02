#!/usr/bin/env python3
"""Tests for the two counters that judge the checks rather than the code.

M3-12 deletes an Advisory check ignored twenty times running; M4-10 measures whether the
verifier's findings ever cause a change. Both read history this repository does not have yet,
which is exactly why they are tested against fixtures now: a counter written after somebody
notices the logs starts counting from the day it was written, and the interesting number is
the one from the first real run.

Both are also, deliberately, mechanisms that can conclude their own subject is not worth
keeping. That is the point of the pair — a gate whose class does not match how people treat it
is lying, and the register is what should be corrected.
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"

sys.path.insert(0, str(SCRIPTS))


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


advisory = load(SCRIPTS / "check-advisory-deletion.py", "check_advisory_deletion")
verifier = load(SCRIPTS / "measure-verifier.py", "measure_verifier")


def runs(states: list[str], gate: str = "quality.dependency_audit") -> list[dict]:
    return [{"findings": {gate: state}} for state in states]


class TestTheAdvisoryCounter(unittest.TestCase):
    def test_twenty_in_a_row_reaches_the_limit(self) -> None:
        history = runs(["ignored"] * 20)
        self.assertEqual(
            advisory.consecutive_ignored(history, "quality.dependency_audit"), 20)

    def test_nineteen_is_not_twenty(self) -> None:
        """The threshold is a decision; an off-by-one turns it into a different decision."""
        history = runs(["ignored"] * 19)
        streak = advisory.consecutive_ignored(history, "quality.dependency_audit")
        self.assertLess(streak, advisory.CONSECUTIVE_LIMIT)

    def test_a_clean_run_breaks_the_streak(self) -> None:
        """A streak that was broken is not a streak.

        The question is which checks nobody is acting on *now*, not which ones had a bad
        quarter — a counter that never forgets eventually deletes everything.
        """
        history = runs(["ignored"] * 30 + ["clean"] + ["ignored"] * 3)
        self.assertEqual(
            advisory.consecutive_ignored(history, "quality.dependency_audit"), 3)

    def test_addressing_a_finding_breaks_the_streak(self) -> None:
        history = runs(["ignored"] * 5 + ["addressed"] + ["ignored"] * 2)
        self.assertEqual(
            advisory.consecutive_ignored(history, "quality.dependency_audit"), 2)

    def test_a_gate_that_did_not_run_breaks_the_streak(self) -> None:
        """Nobody was shown anything, so nobody ignored anything.

        Without this, switching a check off for a month would count as a month of being
        ignored and delete it — which would make disabling a check the way to get rid of it.
        """
        history = runs(["ignored"] * 10) + [{"findings": {}}] + runs(["ignored"] * 2)
        self.assertEqual(
            advisory.consecutive_ignored(history, "quality.dependency_audit"), 2)

    def test_it_counts_backwards_from_the_most_recent(self) -> None:
        history = runs(["clean"] + ["ignored"] * 4)
        self.assertEqual(
            advisory.consecutive_ignored(history, "quality.dependency_audit"), 4)

    def test_only_gates_advisory_at_the_active_tier_are_considered(self) -> None:
        """A gate Advisory at prototype and Contract at production must not be deleted."""
        ids = advisory.advisory_gates(ROOT, "prototype")
        self.assertIn("containment.scope", ids, "advisory at prototype")
        self.assertNotIn("containment.scope", advisory.advisory_gates(ROOT, "production"))

    def test_it_proposes_rather_than_deletes(self) -> None:
        source = (SCRIPTS / "check-advisory-deletion.py").read_text(encoding="utf-8")
        self.assertNotIn("unlink", source)
        self.assertIn("Proposed, not done", source)

    def test_no_history_is_reported_as_no_history(self) -> None:
        """Zero proposals over zero runs must not read as a clean bill of health."""
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "check-advisory-deletion.py")],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("not a clean bill of health", out.stdout)

    def test_a_gate_over_the_limit_is_proposed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history = Path(tmp) / "history.json"
            history.write_text(
                json.dumps(runs(["ignored"] * 25, "quality.dependency_audit")),
                encoding="utf-8")
            out = subprocess.run(
                [sys.executable, str(SCRIPTS / "check-advisory-deletion.py"),
                 "--history", str(history)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
            self.assertIn("quality.dependency_audit", out.stdout)
            self.assertIn("worth blocking on", out.stdout)


class TestTheVerifierMeasurement(unittest.TestCase):
    def test_a_structured_finding_parses(self) -> None:
        findings = verifier.parse_findings(
            "- [blocking] src/main.rs:42 - acceptance criterion 2 is not satisfied")
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["severity"], "blocking")
        self.assertEqual(findings[0]["file"], "src/main.rs")
        self.assertEqual(findings[0]["line"], 42)

    def test_prose_is_not_a_finding(self) -> None:
        self.assertEqual(verifier.parse_findings("I reviewed the diff and it looks fine."), [])

    def test_a_finding_with_no_location_is_malformed_not_dropped(self) -> None:
        """A verifier that formats badly must not look like one that found nothing.

        Those need opposite responses — fix the output contract, versus trust the silence.
        """
        findings = verifier.parse_findings("- [blocking] the error handling is wrong")
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0]["malformed"])

    def test_a_later_change_at_the_line_counts_as_survival(self) -> None:
        finding = {"file": "src/main.rs", "line": 42, "malformed": False}
        self.assertTrue(
            verifier.survived(finding, [{"file": "src/main.rs", "lines": [44]}]))

    def test_a_change_far_away_in_the_same_file_does_not(self) -> None:
        finding = {"file": "src/main.rs", "line": 42, "malformed": False}
        self.assertFalse(
            verifier.survived(finding, [{"file": "src/main.rs", "lines": [400]}]))

    def test_a_change_to_a_different_file_does_not(self) -> None:
        finding = {"file": "src/main.rs", "line": 42, "malformed": False}
        self.assertFalse(
            verifier.survived(finding, [{"file": "src/state.rs", "lines": [42]}]))

    def test_a_malformed_finding_never_survives(self) -> None:
        """It names nowhere, so nothing can be shown to have addressed it."""
        finding = {"file": None, "line": None, "malformed": True}
        self.assertFalse(
            verifier.survived(finding, [{"file": "src/main.rs", "lines": [1]}]))

    def test_the_survival_rate_is_computed_over_findings_not_reviews(self) -> None:
        reviews = [
            {"output": "- [blocking] a.rs:10 - x\n- [nit] a.rs:99 - y",
             "later_changes": [{"file": "a.rs", "lines": [10]}]},
            {"output": "- [major] b.rs:5 - z", "later_changes": []},
        ]
        stats = verifier.summarise(reviews)
        self.assertEqual(stats["findings"], 3)
        self.assertEqual(stats["survivors"], 1)
        self.assertEqual(stats["survival_percent"], 33)

    def test_severity_is_broken_out(self) -> None:
        """A verifier whose blocking findings survive and whose nits do not is working."""
        reviews = [{"output": "- [blocking] a.rs:10 - x\n- [nit] a.rs:99 - y",
                    "later_changes": [{"file": "a.rs", "lines": [10]}]}]
        stats = verifier.summarise(reviews)
        self.assertEqual(stats["by_severity"]["blocking"], [1, 1])
        self.assertEqual(stats["by_severity"]["nit"], [1, 0])

    def test_no_reviews_reports_unknown_rather_than_zero(self) -> None:
        """A zero survival rate and an unmeasured one are different facts.

        Printing 0% over no data would read as a verifier that says useless things, which is a
        conclusion nobody has earned the right to draw here.
        """
        out = subprocess.run(
            [sys.executable, str(SCRIPTS / "measure-verifier.py")],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("nothing to measure", out.stdout)
        self.assertIn("are unknown", out.stdout)

    def test_a_low_survival_rate_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reviews = Path(tmp) / "reviews.json"
            reviews.write_text(json.dumps(
                [{"output": "\n".join(f"- [nit] a.rs:{i} - x" for i in range(10)),
                  "later_changes": []}]), encoding="utf-8")
            out = subprocess.run(
                [sys.executable, str(SCRIPTS / "measure-verifier.py"),
                 "--reviews", str(reviews)],
                cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(out.returncode, 0, out.stderr)
            self.assertIn("nobody acts on is not neutral", out.stdout)

    def test_it_does_not_read_the_agents_own_verdict(self) -> None:
        """Survival is structural. Self-report is worth least where this is aimed."""
        source = (SCRIPTS / "measure-verifier.py").read_text(encoding="utf-8")
        for claim in ("self_assessed", "agent_says", "useful_flag"):
            self.assertNotIn(claim, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
