#!/usr/bin/env python3
"""Tests for the static-analysis gate and its tier behaviour.

Run: python -m unittest discover -s tests -v

SAST is the one row in 06 §3 that passes through all four classes in order, so it is the
clearest test of whether the tier mechanism is real. A suite that only exercised the
configured tier would prove the gate reports at prototype and nothing about the three tiers a
project actually raises itself to — which are the tiers where it blocks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-sast.py"

OK, BLOCKED, CANNOT_RUN = 0, 1, 2


def sarif(*findings: tuple[str, str]) -> str:
    """A SARIF document with severity carried on the rule, as CodeQL emits it."""
    rules = [{"id": rule, "properties": {"security-severity": severity}}
             for rule, severity in findings]
    results = [{"ruleId": rule,
                "locations": [{"physicalLocation": {"artifactLocation": {"uri": "a.py"}}}]}
               for rule, _ in findings]
    return json.dumps({"runs": [{"tool": {"driver": {"rules": rules}}, "results": results}]})


class SastCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir(parents=True)
        self.write_config("prototype")
        self.write_sarif(sarif(("py/command-injection", "9.8")))

    def write_config(self, tier: str) -> None:
        (self.dir / "aios" / "config.yml").write_text(f"tier: {tier}\n", encoding="utf-8")

    def write_sarif(self, text: str) -> None:
        (self.dir / "results.sarif").write_text(text, encoding="utf-8")

    def write_baseline(self, count: int) -> None:
        (self.dir / "aios" / "ratchets.yml").write_text(
            f"ratchets:\n  - id: sast_high_findings\n    direction: lower_is_better\n"
            f"    baseline: {count}\n", encoding="utf-8")

    def check(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--sarif", str(self.dir / "results.sarif"),
             "--root", str(self.dir), *extra], capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr


class TestClassByTier(SastCase):
    def test_advisory_at_prototype_reports_without_blocking(self) -> None:
        code, out = self.check("--tier", "prototype")
        self.assertEqual(code, OK, out)
        self.assertIn("advisory", out)
        self.assertIn("py/command-injection", out, "a finding must still be visible")

    def test_contract_at_production_blocks(self) -> None:
        code, out = self.check("--tier", "production")
        self.assertEqual(code, BLOCKED, out)
        self.assertIn("cannot be waived", out)

    def test_contract_at_regulated_blocks(self) -> None:
        self.assertEqual(self.check("--tier", "regulated")[0], BLOCKED)

    def test_contract_passes_when_there_are_no_findings(self) -> None:
        self.write_sarif(sarif())
        code, out = self.check("--tier", "production")
        self.assertEqual(code, OK, out)

    def test_every_tier_is_covered_by_the_mapping(self) -> None:
        for tier in ("prototype", "internal", "production", "regulated"):
            with self.subTest(tier=tier):
                self.write_baseline(5)
                _, out = self.check("--tier", tier)
                self.assertIn(f"at tier {tier}", out)


class TestRatchetTier(SastCase):
    def test_ratchet_refuses_without_a_measured_baseline(self) -> None:
        """Promoting to a ratcheting tier having never measured would ratchet against nothing.

        Refusing is the point: it forces the measurement before the promotion, rather than
        producing a gate that passes because it has no idea what it is comparing to.
        """
        code, out = self.check("--tier", "internal")
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("no sast_high_findings baseline", out)

    def test_ratchet_passes_at_the_baseline(self) -> None:
        self.write_baseline(1)
        code, out = self.check("--tier", "internal")
        self.assertEqual(code, OK, out)

    def test_ratchet_passes_below_the_baseline(self) -> None:
        self.write_baseline(5)
        self.assertEqual(self.check("--tier", "internal")[0], OK)

    def test_ratchet_blocks_above_the_baseline(self) -> None:
        self.write_baseline(0)
        code, out = self.check("--tier", "internal")
        self.assertEqual(code, BLOCKED, out)
        self.assertIn("worse than the baseline", out)


class TestSeverityThreshold(SastCase):
    def test_below_seven_is_not_high_severity(self) -> None:
        """06 §3 scopes this to high severity. A gate that flags everything gets ignored."""
        self.write_sarif(sarif(("py/weak-note", "6.9")))
        code, out = self.check("--tier", "production")
        self.assertEqual(code, OK, out)
        self.assertIn("0 high-severity", out)

    def test_seven_exactly_is_high_severity(self) -> None:
        self.write_sarif(sarif(("py/thing", "7.0")))
        self.assertEqual(self.check("--tier", "production")[0], BLOCKED)

    def test_severity_on_the_result_is_used_when_present(self) -> None:
        document = json.loads(sarif(("py/thing", "1.0")))
        document["runs"][0]["results"][0]["properties"] = {"security-severity": "9.1"}
        self.write_sarif(json.dumps(document))
        self.assertEqual(self.check("--tier", "production")[0], BLOCKED)

    def test_a_finding_with_no_severity_is_not_assumed_high(self) -> None:
        """Guessing high would make every unscored rule a blocker at production."""
        self.write_sarif(json.dumps({"runs": [{"tool": {"driver": {"rules": []}},
                                               "results": [{"ruleId": "py/unscored"}]}]}))
        self.assertEqual(self.check("--tier", "production")[0], OK)


class TestCannotRun(SastCase):
    def test_a_missing_sarif_cannot_run(self) -> None:
        (self.dir / "results.sarif").unlink()
        code, out = self.check("--tier", "prototype")
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("nothing was analysed", out)

    def test_malformed_sarif_cannot_run(self) -> None:
        self.write_sarif("{not json")
        self.assertEqual(self.check("--tier", "prototype")[0], CANNOT_RUN)

    def test_the_tier_comes_from_config_when_not_overridden(self) -> None:
        self.write_config("production")
        code, out = self.check()
        self.assertEqual(code, BLOCKED, out)
        self.assertIn("at tier production", out)

    def test_an_unknown_tier_in_config_cannot_run(self) -> None:
        self.write_config("whenever")
        self.assertEqual(self.check()[0], CANNOT_RUN)


class TestTheWorkflowMatchesTheGate(unittest.TestCase):
    def test_the_analyser_never_decides_the_outcome_itself(self) -> None:
        """The CodeQL step must not be the gate: a static flag cannot follow a moving class.

        The first attempt did exactly that and the gate registry rejected it.
        """
        text = (ROOT / ".github" / "workflows" / "sast.yml").read_text(encoding="utf-8")
        analyse = text.split("codeql-action/analyze")[1].split("- name:")[0]
        self.assertIn("continue-on-error: true", analyse,
                      "the analyser must not fail the job on its own")
        self.assertIn("check-sast.py", text, "the gate must be the tier-aware script")

    def test_every_action_in_the_sast_workflow_is_pinned(self) -> None:
        text = (ROOT / ".github" / "workflows" / "sast.yml").read_text(encoding="utf-8")
        for line in text.splitlines():
            if "uses:" in line:
                reference = line.split("uses:")[1].split("#")[0].strip().split("@")[1]
                self.assertRegex(reference, r"^[0-9a-f]{40}$")


if __name__ == "__main__":
    unittest.main(verbosity=2)
