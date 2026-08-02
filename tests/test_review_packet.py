#!/usr/bin/env python3
"""Tests for the review packet and the gate runner behind it.

Run: python -m unittest discover -s tests -v

The packet's whole job is to tell a reviewer the truth in one place, so most of what follows
is about the ways a report can mislead without being wrong: a check that did not run reading
like one that passed, an empty section reading like a clean one, and a section 08 §2.2 asks
for quietly not being there at all.
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
RENDER = ROOT / ".github" / "scripts" / "render-review-packet.py"
RUNNER = ROOT / ".github" / "scripts" / "run-gates.py"

RENDERED, CANNOT_RUN = 0, 2

GATES = """\
gates:
  - id: state.tasks
    title: Task files conform to the schema
    class: contract
    blocking: step
    workflow: hygiene.yml
    step: Task files conform to the schema

  - id: quality.smell
    title: Complexity report
    class: advisory
    blocking: continue
    workflow: hygiene.yml
    step: Complexity report

  - id: quality.sast
    title: Static analysis
    class:
      prototype: advisory
      internal: ratchet
      production: contract
      regulated: contract
    blocking: script
    workflow: sast.yml
    step: Static analysis
"""

DIFF = """\
diff --git a/src/thing.py b/src/thing.py
--- a/src/thing.py
+++ b/src/thing.py
@@ -1 +1 @@
-old
+new
diff --git a/docs/unrelated.md b/docs/unrelated.md
--- a/docs/unrelated.md
+++ b/docs/unrelated.md
@@ -1 +1 @@
-a
+b
"""


class PacketCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "tasks").mkdir(parents=True)
        (self.dir / "aios" / "requirements").mkdir(parents=True)
        (self.dir / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        (self.dir / "aios" / "gates.yml").write_text(GATES, encoding="utf-8")
        self.write_task()
        (self.dir / "diff.txt").write_text(DIFF, encoding="utf-8")

    def write_task(self, touches: list[str] | None = None) -> None:
        # Dedent first, then substitute. textwrap.dedent measures the common indent of the
        # *result*, so interpolating a multi-line value straight into an indented template
        # lets one short line set the margin for every other line and silently wreck the YAML.
        # That is how the first version of this fixture passed with one pattern and produced
        # an unparseable task with two.
        template = textwrap.dedent("""\
            ---
            id: T-0001
            title: Do the thing
            status: doing
            satisfies:
              - STATE-1
            priority: 2
            risk: low
            touches:
            __TOUCHES__
            acceptance:
              - The system shall do the thing
            constraints:
              - Do not invent a dependency
            verify: python3 -m unittest
            ---

            ## Context

            Prose that a reviewer reads.
            """)
        patterns = touches if touches is not None else ["src/**"]
        rendered = "\n".join(f'  - "{pattern}"' for pattern in patterns)
        (self.dir / "aios" / "tasks" / "T-0001.md").write_text(
            template.replace("__TOUCHES__", rendered), encoding="utf-8")

    def test_the_fixture_itself_parses(self) -> None:
        """Guards the trap above: a task file that does not parse makes every other test here
        pass for the wrong reason, since an unresolved task still renders a packet."""
        self.write_task(["src/**", "tests/**"])
        text = (self.dir / "aios" / "tasks" / "T-0001.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        data = yaml.safe_load(text.split("---")[1])
        self.assertEqual(data["touches"], ["src/**", "tests/**"])

    def render(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(RENDER), "--root", str(self.dir),
             "--diff", str(self.dir / "diff.txt"), *extra],
            capture_output=True, text=True, encoding="utf-8")
        return result.returncode, result.stdout + result.stderr

    def write_json(self, name: str, payload) -> str:
        path = self.dir / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return str(path)


class TestWhatTheDoneConditionAsksFor(PacketCase):
    """Scope, gate results by class, and advisory findings, in one place."""

    def test_scope_is_grouped_by_the_declared_touches(self) -> None:
        code, out = self.render("--task", "T-0001")
        self.assertEqual(code, RENDERED, out)
        self.assertIn("src/**", out)
        self.assertIn("src/thing.py", out)

    def test_a_file_outside_the_scope_is_flagged(self) -> None:
        code, out = self.render("--task", "T-0001")
        self.assertIn("outside the declared scope", out)
        self.assertIn("docs/unrelated.md", out)

    def test_scope_declared_but_unused_is_called_out(self) -> None:
        self.write_task(["src/**", "tests/**"])
        code, out = self.render("--task", "T-0001")
        self.assertIn("declared but unused", out)

    def test_gates_are_grouped_by_class(self) -> None:
        results = self.write_json("r.json", {"state.tasks": "success",
                                             "quality.smell": "failure"})
        code, out = self.render("--task", "T-0001", "--results", results)
        self.assertEqual(code, RENDERED, out)
        self.assertIn("Contract", out)
        self.assertIn("Advisory", out)
        self.assertIn("cannot be waived", out)

    def test_a_failing_gate_is_visible(self) -> None:
        results = self.write_json("r.json", {"state.tasks": "failure"})
        _, out = self.render("--task", "T-0001", "--results", results)
        self.assertIn("**FAIL**", out)
        self.assertIn("1 failed", out)

    def test_advisory_findings_are_listed(self) -> None:
        advisory = self.write_json("a.json", [{"gate": "quality.smell",
                                               "summary": "Two functions over 60 lines."}])
        _, out = self.render("--task", "T-0001", "--advisory", advisory)
        self.assertIn("Two functions over 60 lines.", out)

    def test_the_task_is_shown_with_its_acceptance_and_constraints(self) -> None:
        _, out = self.render("--task", "T-0001")
        self.assertIn("The system shall do the thing", out)
        self.assertIn("Do not invent a dependency", out)


class TestItDoesNotMislead(PacketCase):
    """The ways a report can be wrong without stating anything false."""

    def test_no_results_supplied_is_not_reported_as_passing(self) -> None:
        _, out = self.render("--task", "T-0001")
        self.assertIn("No CI results were supplied", out)
        self.assertIn("not reported", out)
        self.assertNotIn("**FAIL**", out)

    def test_no_advisory_input_is_distinguished_from_no_findings(self) -> None:
        """"Nothing was found" and "nothing looked" render the same unless this is said."""
        _, out = self.render("--task", "T-0001")
        self.assertIn("No advisory results were supplied", out)

        advisory = self.write_json("a.json", [])
        _, supplied = self.render("--task", "T-0001", "--advisory", advisory)
        self.assertIn("ran and found nothing", supplied)
        self.assertNotIn("No advisory results were supplied", supplied)

    def test_an_unresolvable_task_says_so_rather_than_rendering_nothing(self) -> None:
        (self.dir / "aios" / "tasks" / "T-0001.md").unlink()
        code, out = self.render()
        self.assertEqual(code, RENDERED, out)
        self.assertIn("No task could be resolved", out)
        self.assertIn("2 file(s) changed", out)

    def test_the_missing_sections_name_their_blocker(self) -> None:
        """08 §2.2 asks for six things. A checklist quietly missing one is how it shrinks."""
        _, out = self.render("--task", "T-0001")
        self.assertIn("Not in this packet yet", out)
        self.assertIn("Verification record", out)
        self.assertIn("M1-13", out)
        self.assertIn("traceability", out)

    def test_task_prose_is_fenced_as_untrusted(self) -> None:
        """The packet is read by humans and agents, and prose can say "approve this"."""
        _, out = self.render("--task", "T-0001")
        self.assertIn("<!-- untrusted:", out)

    def test_the_class_shown_is_the_class_at_this_tier(self) -> None:
        results = self.write_json("r.json", {"quality.sast": "failure"})
        _, prototype = self.render("--task", "T-0001", "--results", results,
                                   "--tier", "prototype")
        _, production = self.render("--task", "T-0001", "--results", results,
                                    "--tier", "production")
        self.assertIn("resolved at tier **prototype**", prototype)
        advisory = prototype.split("**Advisory**")[1]
        self.assertIn("quality.sast", advisory)
        contract = production.split("**Contract**")[1].split("**Advisory**")[0]
        self.assertIn("quality.sast", contract)


class TestItSurvivesBadInput(PacketCase):
    def test_a_diff_with_undecodable_bytes_still_renders(self) -> None:
        """A packet that dies on one stray byte reports nothing about the other files."""
        (self.dir / "diff.txt").write_bytes(DIFF.encode("utf-8") + b"\xff\xfe binary")
        code, out = self.render("--task", "T-0001")
        self.assertEqual(code, RENDERED, out)

    def test_a_json_file_with_a_byte_order_mark_is_read(self) -> None:
        """PowerShell writes one by default, and these files are produced by hand."""
        path = self.dir / "r.json"
        path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"state.tasks": "success"}).encode())
        code, out = self.render("--task", "T-0001", "--results", str(path))
        self.assertEqual(code, RENDERED, out)
        self.assertIn("pass", out)

    def test_a_missing_results_file_cannot_run(self) -> None:
        code, out = self.render("--task", "T-0001", "--results", str(self.dir / "gone.json"))
        self.assertEqual(code, CANNOT_RUN, out)

    def test_malformed_results_cannot_run(self) -> None:
        (self.dir / "r.json").write_text("{not json", encoding="utf-8")
        code, _ = self.render("--task", "T-0001", "--results", str(self.dir / "r.json"))
        self.assertEqual(code, CANNOT_RUN)

    def test_out_writes_a_file(self) -> None:
        target = self.dir / "packet.md"
        code, _ = self.render("--task", "T-0001", "--out", str(target))
        self.assertEqual(code, RENDERED)
        self.assertIn("Review packet", target.read_text(encoding="utf-8"))


class TestTheGateRunner(unittest.TestCase):
    """Commands come from the registry, so the packet reports on the set that actually runs."""

    def plan(self, *extra: str) -> dict:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--root", str(ROOT), "--list", *extra],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_every_registered_gate_is_accounted_for(self) -> None:
        registry = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        plan = self.plan()
        for entry in registry["gates"]:
            self.assertIn(entry["id"], plan)

    def test_a_command_is_taken_from_the_workflow_step(self) -> None:
        plan = self.plan()
        self.assertIn("scan-secrets.py", plan["containment.secrets"]["command"])

    def test_an_action_step_is_skipped_not_reported_as_passing(self) -> None:
        """A gate that did not run must never be indistinguishable from one that passed."""
        plan = self.plan()
        skipped = [gate for gate, detail in plan.items() if "skip" in detail]
        for gate in skipped:
            self.assertNotIn("command", plan[gate])

    def test_skipping_a_workflow_skips_all_its_gates(self) -> None:
        plan = self.plan("--skip-workflow", "build.yml")
        registry = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        build = [e["id"] for e in registry["gates"] if e["workflow"] == "build.yml"]
        self.assertTrue(build)
        for gate in build:
            self.assertIn("build.yml is not run", plan[gate]["skip"])

    def test_an_unresolved_expression_is_skipped_rather_than_run_literally(self) -> None:
        """Running `--range origin/${{ github.base_ref }}..HEAD` verbatim would be nonsense."""
        plan = self.plan()
        for detail in plan.values():
            self.assertNotIn("${{", detail.get("command", ""))


class TestTheRunnerOnFixtures(unittest.TestCase):
    """Cases this repository does not currently contain.

    Every gate here happens to point at a `run:` step, so the branch handling an action step
    is unreachable from the real registry — a mutation deleting it survived. A control that
    only works because the situation has not arisen yet is untested, not correct.
    """

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios" / "requirements").mkdir(parents=True)
        (self.dir / ".github" / "workflows").mkdir(parents=True)
        (self.dir / ".github" / "workflows" / "w.yml").write_text(textwrap.dedent("""\
            name: W
            jobs:
              j:
                steps:
                  - name: An action step
                    uses: some/action@0000000000000000000000000000000000000000
                  - name: A command step
                    run: echo hello
            """), encoding="utf-8")
        (self.dir / "aios" / "gates.yml").write_text(textwrap.dedent("""\
            gates:
              - id: a.action
                title: An action step
                class: contract
                blocking: step
                workflow: w.yml
                step: An action step
              - id: a.command
                title: A command step
                class: contract
                blocking: step
                workflow: w.yml
                step: A command step
              - id: a.missing
                title: A step that is not there
                class: contract
                blocking: step
                workflow: w.yml
                step: No such step
            """), encoding="utf-8")

    def plan(self) -> dict:
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--root", str(self.dir), "--list"],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_an_action_step_is_skipped_with_a_reason(self) -> None:
        entry = self.plan()["a.action"]
        self.assertNotIn("command", entry)
        self.assertIn("action, not a command", entry["skip"])

    def test_a_command_step_yields_its_command(self) -> None:
        self.assertEqual(self.plan()["a.command"]["command"], "echo hello")

    def test_a_registry_pointing_at_a_missing_step_says_so(self) -> None:
        self.assertIn("does not exist", self.plan()["a.missing"]["skip"])

    def test_running_marks_the_skipped_ones_skipped_not_passed(self) -> None:
        out = self.dir / "results.json"
        result = subprocess.run(
            [sys.executable, str(RUNNER), "--root", str(self.dir), "--out", str(out)],
            capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        results = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(results["a.action"], "skipped")
        self.assertEqual(results["a.missing"], "skipped")
        self.assertEqual(results["a.command"], "success")

    def test_a_failing_command_is_recorded_as_failure(self) -> None:
        text = (self.dir / ".github" / "workflows" / "w.yml").read_text(encoding="utf-8")
        (self.dir / ".github" / "workflows" / "w.yml").write_text(
            text.replace("run: echo hello", "run: exit 3"), encoding="utf-8")
        out = self.dir / "results.json"
        subprocess.run([sys.executable, str(RUNNER), "--root", str(self.dir),
                        "--out", str(out)], capture_output=True, text=True)
        self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["a.command"], "failure")


class TestThisRepository(unittest.TestCase):
    def test_the_packet_renders_for_this_repository(self) -> None:
        diff = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached"],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
        path = Path(tempfile.mkdtemp()) / "d.diff"
        self.addCleanup(shutil.rmtree, path.parent, True)
        path.write_text(diff.stdout, encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(RENDER), "--root", str(ROOT), "--diff", str(path),
             "--task", "T-950a"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, RENDERED, result.stderr)
        self.assertIn("Review packet", result.stdout)

    def test_the_packet_is_registered_as_a_report(self) -> None:
        registry = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        entry = [e for e in registry["gates"] if e["id"] == "process.review_packet"][0]
        self.assertEqual(entry["class"], "report",
                         "a packet that can block is a second copy of the gates it reports on")

    def test_the_workflow_does_not_use_pull_request_target(self) -> None:
        """It renders branch-controlled prose; a writable token on that is 07 §1.3's warning.

        Parsed rather than searched as text, because the file explains in a comment why it
        does not use that trigger, and a substring check cannot tell an explanation from a use.
        """
        document = yaml.safe_load(
            (ROOT / ".github" / "workflows" / "review-packet.yml").read_text(encoding="utf-8"))
        triggers = document.get(True) or document.get("on")
        self.assertIn("pull_request", triggers)
        self.assertNotIn("pull_request_target", triggers)


if __name__ == "__main__":
    unittest.main(verbosity=2)
