#!/usr/bin/env python3
"""Tests for the gate registry validator.

Run: python -m unittest discover -s tests -v

The criterion M3-01 has to meet is "a check without a declared class fails to register", and
that has two halves. Rejecting a registry entry with no class is the easy half. The half that
carries the weight is rejecting a check that simply is not in the registry — because if
omission worked, declaring a class would be optional in practice and the register would list
only the checks that volunteered.
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
SCRIPT = ROOT / ".github" / "scripts" / "validate-gates.py"

VALID, FAIL, CANNOT_RUN = 0, 1, 2

ONE_GATE = """\
gates:
  - id: demo.check
    title: A demonstration check
    class: contract
    blocking: step
    workflow: demo.yml
    step: Checks something
"""

ONE_WORKFLOW = """\
name: Demo
on: [push]
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Checks something
        run: echo checking
"""


class GateCase(unittest.TestCase):
    """A fixture repository with one workflow and one registered gate."""

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("aios/gates.yml", ONE_GATE)
        self.write("aios/config.yml", "tier: prototype\n")
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW)

    def write(self, relative: str, text: str) -> Path:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")
        return path

    def check(self, tier: str | None = None) -> tuple[int, str]:
        command = [sys.executable, str(SCRIPT), "--root", str(self.dir)]
        if tier:
            command += ["--tier", tier]
        result = subprocess.run(command, capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def assertRejects(self, fragment: str, tier: str | None = None) -> None:
        code, out = self.check(tier)
        self.assertEqual(code, FAIL, f"expected rejection, got exit {code}\n{out}")
        self.assertIn(fragment, out)


class TestBaseline(GateCase):
    def test_a_registered_gate_with_a_class_passes(self) -> None:
        code, out = self.check()
        self.assertEqual(code, VALID, out)


class TestUnregisteredChecks(GateCase):
    """The criterion: a check that declares no class must fail to register."""

    def test_a_step_that_runs_a_command_and_is_not_registered_fails(self) -> None:
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW + """\
      - name: Checks something else
        run: echo also checking
""")
        self.assertRejects("is not in the gate registry")

    def test_a_whole_unregistered_workflow_fails(self) -> None:
        """Adding a workflow is the easiest way to add a check nobody classified."""
        self.write(".github/workflows/extra.yml", """\
            name: Extra
            on: [push]
            jobs:
              extra:
                runs-on: ubuntu-latest
                steps:
                  - name: Sneaks a check in
                    run: echo sneaky
            """)
        self.assertRejects("is not in the gate registry")

    def test_a_command_step_with_no_name_fails(self) -> None:
        """An unnamed step cannot be registered, so it must not be allowed to exist."""
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW + """\
      - run: echo anonymous
""")
        self.assertRejects("no name")

    def test_a_uses_step_needs_no_registration(self) -> None:
        """Actions are not checks. Requiring them would make the register mostly noise."""
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW + """\
      - name: Upload something
        uses: actions/upload-artifact@v4
""")
        self.assertEqual(self.check()[0], VALID)

    def test_not_a_gate_exempts_a_step(self) -> None:
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW + """\
      - name: Sets a variable
        run: echo x=1 >> $GITHUB_ENV
""")
        self.write("aios/gates.yml", ONE_GATE + """\
not_a_gate:
  - workflow: demo.yml
    step: Sets a variable
    reason: Exports a value. Asserts nothing.
""")
        self.assertEqual(self.check()[0], VALID)

    def test_not_a_gate_without_a_reason_fails(self) -> None:
        """Otherwise the exemption list is just a quieter way of not declaring a class."""
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW + """\
      - name: Sets a variable
        run: echo x=1 >> $GITHUB_ENV
""")
        self.write("aios/gates.yml", ONE_GATE + """\
not_a_gate:
  - workflow: demo.yml
    step: Sets a variable
""")
        self.assertRejects("no reason")


class TestClassDeclaration(GateCase):
    def test_a_gate_with_no_class_fails(self) -> None:
        self.write("aios/gates.yml", """\
            gates:
              - id: demo.check
                title: A demonstration check
                blocking: step
                workflow: demo.yml
                step: Checks something
            """)
        self.assertRejects("missing required field(s): class")

    def test_an_unknown_class_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE.replace("class: contract", "class: important"))
        self.assertRejects("is not one of")

    def test_an_unknown_blocking_mode_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE.replace("blocking: step", "blocking: sometimes"))
        self.assertRejects("is not one of")

    def test_a_duplicate_gate_id_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE + ONE_GATE.replace("gates:\n", ""))
        self.assertRejects("duplicate gate id")


class TestClassMatchesReality(GateCase):
    """A class nothing enforces is decoration, and one that contradicts CI is a lie."""

    def test_advisory_that_blocks_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE.replace("class: contract", "class: advisory"))
        self.assertRejects("so it blocks")

    def test_report_that_blocks_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE.replace("class: contract", "class: report"))
        self.assertRejects("so it blocks")

    def test_contract_that_cannot_block_fails(self) -> None:
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW.replace(
            "        run: echo checking", "        continue-on-error: true\n"
                                          "        run: echo checking"))
        self.write("aios/gates.yml", ONE_GATE.replace("blocking: step", "blocking: continue"))
        self.assertRejects("cannot block")

    def test_declaring_continue_without_continue_on_error_fails(self) -> None:
        """The registry must not be able to describe a workflow that does not exist."""
        self.write("aios/gates.yml", ONE_GATE
                   .replace("class: contract", "class: advisory")
                   .replace("blocking: step", "blocking: continue"))
        self.assertRejects("has no continue-on-error")

    def test_declaring_step_while_carrying_continue_on_error_fails(self) -> None:
        self.write(".github/workflows/demo.yml", ONE_WORKFLOW.replace(
            "        run: echo checking", "        continue-on-error: true\n"
                                          "        run: echo checking"))
        self.assertRejects("carries continue-on-error")

    def test_script_controlled_blocking_needs_a_note(self) -> None:
        """`script` is the escape hatch from workflow verification, so it must be justified."""
        self.write("aios/gates.yml", ONE_GATE.replace("blocking: step", "blocking: script"))
        self.assertRejects("needs a note")

    def test_script_controlled_blocking_passes_with_a_note(self) -> None:
        self.write("aios/gates.yml", ONE_GATE.replace(
            "blocking: step", "blocking: script\n    note: The script reads the tier."))
        self.assertEqual(self.check()[0], VALID)


class TestRegistryPointsAtRealSteps(GateCase):
    def test_naming_a_missing_workflow_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE.replace("workflow: demo.yml",
                                                      "workflow: nonexistent.yml"))
        self.assertRejects("does not exist")

    def test_naming_a_missing_step_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE.replace("step: Checks something",
                                                      "step: Checks nothing"))
        self.assertRejects("no such step")


class TestPlannedGates(GateCase):
    def test_a_planned_gate_needs_a_class(self) -> None:
        self.write("aios/gates.yml", ONE_GATE + """\
planned:
  - id: future.check
    pending: M3-05
""")
        self.assertRejects("missing required field(s): class")

    def test_a_planned_gate_needs_an_implementing_task(self) -> None:
        """Otherwise `planned` becomes where checks go to be forgotten."""
        self.write("aios/gates.yml", ONE_GATE + """\
planned:
  - id: future.check
    class: contract
""")
        self.assertRejects("names no task")

    def test_a_planned_id_colliding_with_a_real_one_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE + """\
planned:
  - id: demo.check
    class: contract
    pending: M3-05
""")
        self.assertRejects("duplicate gate id")


VARYING = """\
gates:
  - id: demo.check
    title: A demonstration check
    class:
      prototype: advisory
      internal: contract
      production: contract
      regulated: contract
    blocking: script
    workflow: demo.yml
    step: Checks something
    note: The script reads the tier and decides.
"""


class TestTierMapping(GateCase):
    """06 §3: the gate set is identical at every tier; only the class assignment moves."""

    def test_a_varying_class_resolves_at_every_tier(self) -> None:
        self.write("aios/gates.yml", VARYING)
        for tier in ("prototype", "internal", "production", "regulated"):
            with self.subTest(tier=tier):
                code, out = self.check(tier)
                self.assertEqual(code, VALID, out)
                self.assertIn(f"valid at tier {tier}", out)

    def test_the_configured_tier_is_the_one_key(self) -> None:
        """Changing `tier` in config.yml, and nothing else, must change the resolution."""
        self.write("aios/gates.yml", VARYING)
        self.assertIn("1 advisory", self.check()[1])
        self.write("aios/config.yml", "tier: production\n")
        self.assertIn("1 contract", self.check()[1])

    def test_a_partial_tier_mapping_fails(self) -> None:
        """A gate undefined at a tier would silently not apply there."""
        self.write("aios/gates.yml", """\
            gates:
              - id: demo.check
                title: A demonstration check
                class:
                  prototype: advisory
                  internal: contract
                blocking: script
                workflow: demo.yml
                step: Checks something
                note: A note.
            """)
        self.assertRejects("does not say what it is at production, regulated")

    def test_an_unknown_tier_in_the_mapping_fails(self) -> None:
        self.write("aios/gates.yml", VARYING.replace("production:", "staging:"))
        self.assertRejects("unknown tier")

    def test_an_unknown_class_at_one_tier_fails(self) -> None:
        self.write("aios/gates.yml", VARYING.replace("internal: contract",
                                                     "internal: important"))
        self.assertRejects("class at internal")

    def test_a_varying_class_cannot_be_enforced_by_a_static_step(self) -> None:
        """The claim under test: raising a tier is a config change, not a migration.

        A workflow step is static. If a varying gate could declare `blocking: step`, raising
        the tier would change the register and nothing else, and the migration would still be
        there — just invisible.
        """
        self.write("aios/gates.yml", VARYING.replace("blocking: script", "blocking: step")
                                            .replace("    note: The script reads the tier "
                                                     "and decides.\n", ""))
        self.assertRejects("its class cannot follow the tier")

    def test_an_invariant_class_may_use_a_static_step(self) -> None:
        """Static enforcement is honest when the class genuinely never moves."""
        self.assertEqual(self.check()[0], VALID)

    def test_a_gate_that_does_not_run_at_this_tier_must_not_block(self) -> None:
        """The dashes in 06 §3 mean the check does not run there at all."""
        self.write("aios/gates.yml", VARYING.replace("prototype: advisory", "prototype: none")
                                            .replace("blocking: script", "blocking: step")
                                            .replace("    note: The script reads the tier "
                                                     "and decides.\n", ""))
        self.assertRejects("its class cannot follow the tier")

    def test_none_is_a_valid_class_at_a_tier(self) -> None:
        self.write("aios/gates.yml", VARYING.replace("prototype: advisory", "prototype: none"))
        code, out = self.check()
        self.assertEqual(code, VALID, out)
        self.assertIn("1 none", out)

    def test_a_planned_gate_may_vary_by_tier(self) -> None:
        self.write("aios/gates.yml", ONE_GATE + """\
planned:
  - id: future.check
    class:
      prototype: report
      internal: ratchet
      production: ratchet
      regulated: contract
    pending: M3-04
""")
        self.assertEqual(self.check()[0], VALID)

    def test_a_planned_gate_with_a_partial_mapping_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE + """\
planned:
  - id: future.check
    class:
      prototype: report
    pending: M3-04
""")
        self.assertRejects("does not say what it is at")

    def test_a_threshold_naming_an_unknown_tier_fails(self) -> None:
        self.write("aios/gates.yml", ONE_GATE + "    threshold: {mostly: '>=80%'}\n")
        self.assertRejects("threshold names unknown tier")


class TestTierComesFromConfig(GateCase):
    def test_a_missing_config_cannot_run(self) -> None:
        (self.dir / "aios" / "config.yml").unlink()
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("no tier to resolve", out)

    def test_an_unknown_tier_cannot_run(self) -> None:
        self.write("aios/config.yml", "tier: whenever\n")
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("not one of", out)


class TestCannotRun(GateCase):
    def test_a_missing_registry_cannot_run(self) -> None:
        (self.dir / "aios" / "gates.yml").unlink()
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)
        self.assertIn("no gate registry", out)

    def test_an_unparseable_registry_cannot_run(self) -> None:
        self.write("aios/gates.yml", "gates:\n  - id: *broken\n")
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)

    def test_missing_workflows_cannot_run(self) -> None:
        shutil.rmtree(self.dir / ".github" / "workflows")
        code, out = self.check()
        self.assertEqual(code, CANNOT_RUN, out)


class TestThisRepositoryIsValid(unittest.TestCase):
    def test_every_check_in_this_repository_declares_a_class(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, VALID, result.stdout + result.stderr)

    def test_this_repository_resolves_at_every_tier(self) -> None:
        """The test per tier that M3-02 asks for, against the real table rather than a fixture.

        A suite that only exercised the configured tier would have proved the mechanism works
        at prototype and nothing about the three tiers a real project raises itself to.
        """
        for tier in ("prototype", "internal", "production", "regulated"):
            with self.subTest(tier=tier):
                result = subprocess.run(
                    [sys.executable, str(SCRIPT), "--root", str(ROOT), "--tier", tier],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, VALID,
                                 result.stdout + result.stderr)

    def test_raising_the_tier_never_weakens_a_gate(self) -> None:
        """The table's shape, asserted rather than assumed: classes only ever harden.

        06 §3 has no row that relaxes as the tier rises, and a row that did would be a typo
        rather than a policy. Nothing else in the system would notice it.
        """
        import yaml
        strength = {"none": 0, "report": 1, "advisory": 2, "ratchet": 3, "contract": 4}
        registry = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        tiers = ("prototype", "internal", "production", "regulated")

        for entry in (registry.get("gates") or []) + (registry.get("planned") or []):
            declared = entry["class"]
            if not isinstance(declared, dict):
                continue
            with self.subTest(gate=entry["id"]):
                levels = [strength[declared[tier]] for tier in tiers]
                self.assertEqual(levels, sorted(levels),
                                 f"{entry['id']} weakens as the tier rises: "
                                 f"{[declared[t] for t in tiers]}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
