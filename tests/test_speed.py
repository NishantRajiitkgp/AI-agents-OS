#!/usr/bin/env python3
"""Tests for the feedback-speed budgets and the parallel test runner.

Run: python -m unittest discover -s tests -v

Timing is the one metric here whose measurement is noisy, so most of these are about the gate
behaving predictably despite that: tolerance applied only where declared, a tier that reports
before it blocks, and a path that could not be measured never reading as one that was fast.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SPEED = ROOT / ".github" / "scripts" / "measure-speed.py"
RATCHETS = ROOT / ".github" / "scripts" / "check-ratchets.py"
RUNNER = ROOT / ".github" / "scripts" / "run-tests.py"

ACCEPTABLE, BLOCKED, CANNOT_RUN = 0, 1, 2

CONFIG = """\
tier: prototype
budgets:
  pre_commit_seconds: 5
  check_seconds: 60
  ci_pr_seconds: 600
"""


class SpeedCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir(parents=True)
        (self.dir / ".github" / "scripts").mkdir(parents=True)
        (self.dir / "aios" / "config.yml").write_text(CONFIG, encoding="utf-8")
        self.write_ratchets([])
        # A stand-in for the secrets scan: the point is the harness, not the scanner.
        (self.dir / ".github" / "scripts" / "scan-secrets.py").write_text(
            "print('ok')\n", encoding="utf-8")

    def write_ratchets(self, entries: list[dict]) -> None:
        (self.dir / "aios" / "ratchets.yml").write_text(
            yaml.safe_dump({"ratchets": entries}, sort_keys=False), encoding="utf-8")

    def measure(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SPEED), "--root", str(self.dir), *extra],
            capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout + result.stderr


class TestClassByTier(SpeedCase):
    def test_prototype_reports_and_never_blocks(self) -> None:
        code, out = self.measure("--only", "pre_commit", "--tier", "prototype")
        self.assertEqual(code, ACCEPTABLE, out)
        self.assertIn("report at tier prototype", out)

    def test_an_overrun_at_prototype_is_reported_not_blocked(self) -> None:
        """The first red build must not also be the first measurement."""
        (self.dir / "aios" / "config.yml").write_text(
            CONFIG.replace("pre_commit_seconds: 5", "pre_commit_seconds: 0"),
            encoding="utf-8")
        # A zero-second budget cannot be met, so this measures the verdict, not the machine.
        code, out = self.measure("--only", "pre_commit", "--tier", "prototype")
        self.assertEqual(code, ACCEPTABLE, out)
        self.assertIn("OVER", out)
        self.assertIn("not blocking", out)

    def test_the_same_overrun_blocks_at_a_contract_tier(self) -> None:
        (self.dir / "aios" / "config.yml").write_text(
            CONFIG.replace("pre_commit_seconds: 5", "pre_commit_seconds: 0"),
            encoding="utf-8")
        code, out = self.measure("--only", "pre_commit", "--tier", "regulated")
        self.assertEqual(code, BLOCKED, out)
        self.assertIn("over budget at a contract tier", out)

    def test_the_ratchet_tier_refuses_without_a_baseline(self) -> None:
        code, out = self.measure("--only", "pre_commit", "--tier", "production")
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("no baseline is recorded", out)

    def test_the_ratchet_tier_passes_against_a_generous_baseline(self) -> None:
        self.write_ratchets([{"id": "pre_commit_seconds", "direction": "lower_is_better",
                              "baseline": 300}])
        code, out = self.measure("--only", "pre_commit", "--tier", "production")
        self.assertEqual(code, ACCEPTABLE, out)

    def test_the_ratchet_tier_blocks_a_regression(self) -> None:
        self.write_ratchets([{"id": "pre_commit_seconds", "direction": "lower_is_better",
                              "baseline": 0}])
        code, out = self.measure("--only", "pre_commit", "--tier", "production")
        self.assertEqual(code, BLOCKED, out)
        self.assertIn("worse than the baseline", out)

    def test_the_tolerance_is_applied_to_the_comparison(self) -> None:
        """Without it, a wall-clock ratchet fails on runner jitter and gets ignored."""
        self.write_ratchets([{"id": "pre_commit_seconds", "direction": "lower_is_better",
                              "baseline": 0, "tolerance_percent": 50}])
        blocked, _ = self.measure("--only", "pre_commit", "--tier", "production")
        # A baseline of zero cannot be rescued by a percentage of zero, so this still blocks —
        # which is the right answer and shows the tolerance is proportional, not additive.
        self.assertEqual(blocked, BLOCKED)


class TestItDoesNotMislead(SpeedCase):
    def test_an_unmeasurable_path_is_not_reported_as_fast(self) -> None:
        """Nothing outside Actions can time a CI job; a zero there would be a lie."""
        code, out = self.measure("--only", "ci_pr", "--tier", "prototype")
        self.assertEqual(code, ACCEPTABLE, out)
        self.assertIn("not measured", out)
        self.assertNotIn("0.0s against", out)

    def test_a_supplied_ci_duration_is_measured(self) -> None:
        code, out = self.measure("--only", "ci_pr", "--ci-seconds", "120")
        self.assertIn("120.0s against a 600s budget", out)
        self.assertIn("within", out)

    def test_a_supplied_ci_duration_over_budget_is_flagged(self) -> None:
        code, out = self.measure("--only", "ci_pr", "--ci-seconds", "900")
        self.assertIn("OVER", out)

    def test_a_missing_budget_cannot_run(self) -> None:
        (self.dir / "aios" / "config.yml").write_text("tier: prototype\nbudgets: {}\n",
                                                      encoding="utf-8")
        code, out = self.measure("--only", "pre_commit")
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("is not configured", out)

    def test_an_unknown_path_cannot_run(self) -> None:
        code, out = self.measure("--only", "nonsense")
        self.assertEqual(code, CANNOT_RUN, out)

    def test_out_writes_the_measurements(self) -> None:
        target = self.dir / "speed.json"
        code, _ = self.measure("--only", "ci_pr", "--ci-seconds", "42",
                               "--out", str(target))
        self.assertEqual(code, ACCEPTABLE)
        payload = json.loads(target.read_text(encoding="utf-8"))
        self.assertEqual(payload["ci_pr"]["seconds"], 42.0)
        self.assertEqual(payload["ci_pr"]["budget"], 600)


class TestTheTolerance(unittest.TestCase):
    """Tolerance in the general ratchet mechanism, not only in the speed gate."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir(parents=True)
        (self.dir / "AGENTS.md").write_text("x\n" * 100, encoding="utf-8")

    def write(self, entry: dict) -> None:
        (self.dir / "aios" / "ratchets.yml").write_text(
            yaml.safe_dump({"ratchets": [entry]}, sort_keys=False), encoding="utf-8")

    def check(self) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(RATCHETS), "--root", str(self.dir)],
            capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout + result.stderr

    def base(self, **extra) -> dict:
        return {"id": "agents_md_lines", "direction": "lower_is_better",
                "baseline": 95, **extra}

    def test_without_a_tolerance_a_regression_fails(self) -> None:
        self.write(self.base())
        code, out = self.check()
        self.assertEqual(code, 1, out)

    def test_a_declared_tolerance_absorbs_a_small_regression(self) -> None:
        self.write(self.base(tolerance_percent=10,
                             tolerance_reason="Wall clock on a shared runner moves on its own."))
        code, out = self.check()
        self.assertEqual(code, 0, out)
        self.assertIn("within tolerance", out)

    def test_a_tolerance_does_not_absorb_a_large_regression(self) -> None:
        self.write(self.base(baseline=50, tolerance_percent=10,
                             tolerance_reason="Wall clock on a shared runner moves on its own."))
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("tolerance", out)

    def test_a_tolerance_without_a_reason_is_rejected(self) -> None:
        """Otherwise it is slack for an inconvenient number rather than for a noisy one."""
        self.write(self.base(tolerance_percent=10))
        code, out = self.check()
        self.assertEqual(code, 1, out)
        self.assertIn("no reason worth reading", out)

    def test_an_absurd_tolerance_is_rejected(self) -> None:
        for value in (0, -5, 80, "lots"):
            with self.subTest(value=value):
                self.write(self.base(tolerance_percent=value,
                                     tolerance_reason="A reason long enough to pass."))
                code, out = self.check()
                self.assertEqual(code, 1, out)
                self.assertIn("tolerance_percent", out)


class TestTheParallelRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "tests").mkdir(parents=True)

    def write(self, name: str, text: str) -> None:
        (self.dir / "tests" / name).write_text(textwrap.dedent(text), encoding="utf-8")

    def run_runner(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--root", str(self.dir), *extra],
            capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout + result.stderr

    def test_it_runs_every_test_across_shards(self) -> None:
        for index in range(4):
            self.write(f"test_m{index}.py", f"""\
                import unittest

                class TestOne{index}(unittest.TestCase):
                    def test_a(self): pass
                    def test_b(self): pass
                """)
        code, out = self.run_runner("--jobs", "4")
        self.assertEqual(code, 0, out)
        self.assertIn("ran 8 test(s)", out)

    def test_a_failure_in_any_shard_fails_the_run(self) -> None:
        self.write("test_ok.py", """\
            import unittest

            class TestOk(unittest.TestCase):
                def test_a(self): pass
            """)
        self.write("test_bad.py", """\
            import unittest

            class TestBad(unittest.TestCase):
                def test_a(self): self.fail("deliberate")
            """)
        code, out = self.run_runner("--jobs", "2")
        self.assertEqual(code, 1, out)
        self.assertIn("deliberate", out)

    def test_a_base_class_holding_a_test_is_not_skipped(self) -> None:
        """Shared bases in this suite do carry tests; sharding on the name alone loses them."""
        self.write("test_base.py", """\
            import unittest

            class SharedBase(unittest.TestCase):
                def test_inherited(self): pass
            """)
        code, out = self.run_runner("--jobs", "2")
        self.assertEqual(code, 0, out)
        self.assertIn("ran 1 test(s)", out)

    def test_serial_and_parallel_run_the_same_tests(self) -> None:
        for index in range(3):
            self.write(f"test_s{index}.py", f"""\
                import unittest

                class TestS{index}(unittest.TestCase):
                    def test_a(self): pass
                    def test_b(self): pass
                    def test_c(self): pass
                """)
        _, parallel = self.run_runner("--jobs", "3")
        _, serial = self.run_runner("--serial")
        self.assertIn("ran 9 test(s)", parallel)
        self.assertIn("ran 9 test(s)", serial)

    def test_no_tests_cannot_run(self) -> None:
        code, out = self.run_runner()
        self.assertEqual(code, 2, out)

    def test_a_module_that_does_not_parse_cannot_run(self) -> None:
        self.write("test_broken.py", "class Test(:\n")
        code, out = self.run_runner()
        self.assertEqual(code, 2, out)
        self.assertIn("does not parse", out)


class TestThisRepository(unittest.TestCase):
    def test_the_budgets_are_configured(self) -> None:
        config = yaml.safe_load((ROOT / "aios" / "config.yml").read_text(encoding="utf-8"))
        for key in ("pre_commit_seconds", "check_seconds", "ci_pr_seconds"):
            self.assertIn(key, config["budgets"])

    def test_the_speed_gate_is_registered_and_varies_by_tier(self) -> None:
        registry = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        entry = [e for e in registry["gates"] if e["id"] == "process.feedback_speed"][0]
        self.assertIsInstance(entry["class"], dict)
        self.assertEqual(entry["blocking"], "script",
                         "a class that moves with the tier cannot be a static flag")

    def test_the_timing_baselines_say_why_they_are_not_measured_here(self) -> None:
        """A Windows baseline would be a baseline for a machine CI is not."""
        document = yaml.safe_load((ROOT / "aios" / "ratchets.yml").read_text(encoding="utf-8"))
        planned = {entry["id"]: entry for entry in document["planned"]}
        for metric in ("pre_commit_seconds", "check_seconds", "ci_pr_seconds"):
            self.assertIn(metric, planned)
            self.assertTrue(str(planned[metric].get("reason", "")).strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)
