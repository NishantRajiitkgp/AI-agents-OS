#!/usr/bin/env python3
"""Tests for the state validators.

Run: python3 -m unittest discover -s tests -v

stdlib `unittest` rather than a test framework, because the OS has to satisfy its own
supply-chain gates and every dependency is one it will have to justify (ADR-005). PyYAML is
already required by the validators themselves; nothing new is added here.

Each test names a failure mode and asserts the validator rejects it. The two that assert a
*non*-failure matter as much: EARS conformance and weasel words must warn without blocking,
and that behaviour would invert silently if the severities were ever collapsed.

What these tests cover, in the traceability sense (M5-05). The annotation is not decoration:
it is what lets a failure here report "STATE-7 is violated" rather than "assertion failed".

    @satisfies STATE-1  one file per unit of work — the task validator reads a directory of
                        single-task files and rejects anything that is not one
    @satisfies STATE-6  malformed state is refused at the boundary — every rejection test
                        below is an instance of this one requirement
    @satisfies STATE-7  identifiers are unique across the repository
    @satisfies STATE-8  a withdrawn requirement is retained, never removed — enforced by the
                        status vocabulary and the mandatory reason on superseded entries

STATE-2, STATE-3, STATE-4 and STATE-5 are deliberately not claimed here. They describe what
the binary does — computed progress, the verification record, the grader re-running it, the
deterministic selector — and the binary does not exist yet (`M1-08`). The traceability report
naming them as untested is correct, and papering over that with an annotation on the nearest
passing test is exactly the dishonesty the report is designed to make visible.

These are the tests M1-07's Done-when asks for. They replace the throwaway harnesses used
while building the earlier gates, which proved the checks worked at one moment and then
vanished — a check nothing re-runs is a check nobody knows still works.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / ".github" / "scripts"

PASS, FAIL, CANNOT_RUN = 0, 1, 2

GOOD_REQ = """## AREA-1 \u2014 A requirement

**Status:** active
**Rationale:** Because it is needed.

The system shall do the thing.
"""

GOOD_TASK = """---
id: T-950a
title: A task
status: todo
satisfies: [AREA-1]
priority: 1
risk: low
blocked_by: []
touches:
  - src/x.py
acceptance:
  - "The system shall do the thing"
verify:
  - python3 -c "pass"
---

## Context

Why this exists.
"""


def run(script: str, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        capture_output=True, text=True)
    return result.returncode, result.stdout + result.stderr


class ValidatorCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())

    def write(self, relative: str, text: str) -> Path:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def assertRejects(self, code: int, out: str, fragment: str) -> None:
        self.assertEqual(code, FAIL, f"expected rejection, got exit {code}\n{out}")
        self.assertIn(fragment, out)


class TestRequirementSchema(ValidatorCase):
    def check(self, text: str, name: str = "area.md") -> tuple[int, str]:
        self.write(name, text)
        return run("validate-requirements.py", "--dir", str(self.dir))

    def test_valid_file_passes(self) -> None:
        code, out = self.check(GOOD_REQ)
        self.assertEqual(code, PASS, out)

    def test_unknown_status_rejected(self) -> None:
        self.assertRejects(*self.check(GOOD_REQ.replace("active", "maybe")), "is not one of active")

    def test_deferred_without_reason_rejected(self) -> None:
        text = GOOD_REQ.replace("**Status:** active", "**Status:** deferred")
        self.assertRejects(*self.check(text), "requires a Reason")

    def test_dropped_without_reason_rejected(self) -> None:
        text = GOOD_REQ.replace("**Status:** active", "**Status:** dropped")
        self.assertRejects(*self.check(text), "requires a Reason")

    def test_active_without_rationale_rejected(self) -> None:
        text = GOOD_REQ.replace("**Rationale:** Because it is needed.\n", "")
        self.assertRejects(*self.check(text), "requires a Rationale")

    def test_area_must_match_filename(self) -> None:
        self.assertRejects(*self.check(GOOD_REQ, "other.md"), "does not match the filename")

    def test_duplicate_id_in_one_file_rejected(self) -> None:
        self.assertRejects(*self.check(GOOD_REQ + "\n" + GOOD_REQ), "duplicate ID")

    def test_missing_body_rejected(self) -> None:
        text = GOOD_REQ.replace("The system shall do the thing.\n", "")
        self.assertRejects(*self.check(text), "no requirement body")

    def test_file_with_no_requirements_rejected(self) -> None:
        self.assertRejects(*self.check("# nothing here\n"), "no requirements found")

    def test_non_ears_clause_warns_but_does_not_block(self) -> None:
        text = GOOD_REQ.replace("The system shall do the thing.", "It should probably work.")
        code, out = self.check(text)
        self.assertEqual(code, PASS, out)
        self.assertIn("matches no EARS template", out)

    def test_weasel_word_warns_but_does_not_block(self) -> None:
        text = GOOD_REQ.replace("do the thing.", "be fast.")
        code, out = self.check(text)
        self.assertEqual(code, PASS, out)
        self.assertIn("weasel word", out)

    def test_missing_directory_cannot_run(self) -> None:
        code, out = run("validate-requirements.py", "--dir", str(self.dir / "absent"))
        self.assertEqual(code, CANNOT_RUN, out)


class TestTaskSchema(ValidatorCase):
    def check(self, text: str, name: str = "T-950a.md", *extra: str) -> tuple[int, str]:
        self.write(name, text)
        return run("validate-tasks.py", "--dir", str(self.dir), *extra)

    def test_valid_task_passes(self) -> None:
        code, out = self.check(GOOD_TASK)
        self.assertEqual(code, PASS, out)

    # M4-04. The hook refuses the first write without a duplicate check; this is the same
    # rule stated where a pull request can fail on it, since the hook runs on a machine
    # nobody else can see.
    def test_a_task_in_progress_needs_a_duplicate_check(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: doing")
        self.assertRejects(*self.check(text), "requires duplicate_check")

    def test_todo_does_not_need_one(self) -> None:
        """The record is written while planning. Requiring it to leave `todo` is a deadlock."""
        code, out = self.check(GOOD_TASK)
        self.assertEqual(code, PASS, out)

    def test_a_recorded_check_satisfies_it(self) -> None:
        text = GOOD_TASK.replace(
            "status: todo",
            "status: doing\nduplicate_check:\n  - \"glob matching — found at check-scope.py\"")
        code, out = self.check(text)
        self.assertEqual(code, PASS, out)

    def test_an_entry_that_does_not_say_what_was_found_is_rejected(self) -> None:
        """'I looked' is an assertion. 'I looked for X and found Y' is evidence."""
        text = GOOD_TASK.replace(
            "status: todo", "status: doing\nduplicate_check:\n  - \"searched for it\"")
        self.assertRejects(*self.check(text), "does not say what was found")

    def test_nothing_found_is_accepted_when_it_says_where_it_looked(self) -> None:
        text = GOOD_TASK.replace(
            "status: todo",
            "status: doing\nduplicate_check:\n  - \"ratchet tolerance — nothing found; "
            "searched tolerance, ratchet, baseline\"")
        code, out = self.check(text)
        self.assertEqual(code, PASS, out)

    def test_unknown_field_rejected(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: todo\nflavour: spicy")
        self.assertRejects(*self.check(text), "the field list is closed")

    def test_deliberately_cut_field_named_as_such(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: todo\nstory_points: 5")
        code, out = self.check(text)
        self.assertRejects(code, out, "deliberately cut")
        self.assertNotIn("unknown field", out)

    def test_assignee_rejected(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: todo\nassignee: someone")
        self.assertRejects(*self.check(text), "deliberately cut")

    def test_missing_required_field_rejected(self) -> None:
        self.assertRejects(*self.check(GOOD_TASK.replace("risk: low\n", "")), "required field")

    def test_unknown_status_rejected(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: blocked")
        self.assertRejects(*self.check(text), "is not one of")

    def test_waiting_requires_waiting_on(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: waiting")
        self.assertRejects(*self.check(text), "requires waiting_on")

    def test_waiting_with_waiting_on_passes(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: waiting\nwaiting_on: a vendor reply")
        code, out = self.check(text)
        self.assertEqual(code, PASS, out)

    def test_waiting_on_without_waiting_rejected(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: todo\nwaiting_on: nothing")
        self.assertRejects(*self.check(text), "waiting_on is set but status is")

    def test_dropped_requires_reason(self) -> None:
        text = GOOD_TASK.replace("status: todo", "status: dropped")
        self.assertRejects(*self.check(text), "requires a reason")

    def test_priority_out_of_range_rejected(self) -> None:
        self.assertRejects(*self.check(GOOD_TASK.replace("priority: 1", "priority: 9")),
                           "integer from 1 to 3")

    def test_unknown_risk_rejected(self) -> None:
        self.assertRejects(*self.check(GOOD_TASK.replace("risk: low", "risk: spicy")),
                           "is not one of")

    def test_id_must_match_filename(self) -> None:
        self.assertRejects(*self.check(GOOD_TASK, "T-beef.md"), "does not match the filename")

    def test_empty_satisfies_rejected(self) -> None:
        text = GOOD_TASK.replace("satisfies: [AREA-1]", "satisfies: []")
        self.assertRejects(*self.check(text), "must not be empty")

    def test_malformed_requirement_reference_rejected(self) -> None:
        text = GOOD_TASK.replace("[AREA-1]", "[area-1]")
        self.assertRejects(*self.check(text), "is not a requirement ID")

    def test_malformed_task_reference_rejected(self) -> None:
        text = GOOD_TASK.replace("blocked_by: []", "blocked_by: [nope]")
        self.assertRejects(*self.check(text), "is not a task ID")

    def test_missing_body_rejected(self) -> None:
        self.assertRejects(*self.check(GOOD_TASK.split("## Context")[0]), "no body")

    def test_absent_frontmatter_rejected(self) -> None:
        self.assertRejects(*self.check("# just prose\n"), "no YAML frontmatter")

    def test_line_cap_enforced(self) -> None:
        self.assertRejects(*self.check(GOOD_TASK, "T-950a.md", "--cap", "5"), "cap is 5")

    def test_misnamed_file_is_not_silently_skipped(self) -> None:
        """The bug this was written for: globbing T-*.md made a misnamed file invisible."""
        self.assertRejects(*self.check(GOOD_TASK, "TASK-1.md"), "filename is not a task ID")

    def test_stray_file_under_tasks_rejected(self) -> None:
        self.write("T-950a.md", GOOD_TASK)
        self.write("notes.md", "# scratch\n")
        code, out = run("validate-tasks.py", "--dir", str(self.dir))
        self.assertRejects(code, out, "filename is not a task ID")

    def test_done_subtree_is_scanned(self) -> None:
        self.write("done/2026-07/T-beef.md", "# broken\n")
        code, out = run("validate-tasks.py", "--dir", str(self.dir))
        self.assertRejects(code, out, "no YAML frontmatter")


class TestReferences(ValidatorCase):
    def seed(self, req: str = GOOD_REQ, task: str | None = GOOD_TASK) -> tuple[int, str]:
        self.write("requirements/area.md", req)
        if task is not None:
            self.write("tasks/T-950a.md", task)
        else:
            self.dir.joinpath("tasks").mkdir(parents=True, exist_ok=True)
        return run("validate-references.py", "--state", str(self.dir))

    def test_resolving_references_pass(self) -> None:
        code, out = self.seed()
        self.assertEqual(code, PASS, out)

    def test_satisfies_a_requirement_that_does_not_exist(self) -> None:
        task = GOOD_TASK.replace("[AREA-1]", "[AREA-99]")
        self.assertRejects(*self.seed(task=task), "which does not exist")

    def test_satisfies_a_deferred_requirement_is_a_hard_error(self) -> None:
        """The anti-invention control: only an active requirement can justify work."""
        req = GOOD_REQ.replace("**Status:** active\n**Rationale:** Because it is needed.",
                               "**Status:** deferred\n**Reason:** Not now.")
        self.assertRejects(*self.seed(req=req), "Only an active requirement")

    def test_blocked_by_a_task_that_does_not_exist(self) -> None:
        task = GOOD_TASK.replace("blocked_by: []", "blocked_by: [T-abcd]")
        self.assertRejects(*self.seed(task=task), "blocked_by names T-abcd")

    def test_parent_that_does_not_exist(self) -> None:
        task = GOOD_TASK.replace("status: todo", "status: todo\nparent: T-abcd")
        self.assertRejects(*self.seed(task=task), "parent names T-abcd")

    def test_duplicate_id_across_requirements_and_tasks(self) -> None:
        self.write("requirements/area.md", GOOD_REQ)
        self.write("tasks/T-950a.md", GOOD_TASK)
        self.write("tasks/done/2026-07/T-950a.md", GOOD_TASK)
        code, out = run("validate-references.py", "--state", str(self.dir))
        self.assertRejects(code, out, "defined at both")

    def test_superseded_by_a_requirement_that_does_not_exist(self) -> None:
        req = GOOD_REQ.replace("**Status:** active", "**Status:** superseded-by: AREA-99")
        self.assertRejects(*self.seed(req=req, task=None), "which does not exist")

    # Link resolution moved to check-memory.py at M5-01, along with its test — see
    # tests/test_memory.py, TestTheRuleHasOneImplementation. It is not tested in both places,
    # because a rule tested against two implementations has two definitions of passing.

    def test_missing_state_directory_cannot_run(self) -> None:
        code, out = run("validate-references.py", "--state", str(self.dir / "absent"))
        self.assertEqual(code, CANNOT_RUN, out)


class TestRepositoryIsValid(unittest.TestCase):
    """The validators must pass against the real repository, not only against fixtures."""

    def test_config(self) -> None:
        code, out = run("validate-config.py")
        self.assertEqual(code, PASS, out)

    def test_requirements(self) -> None:
        code, out = run("validate-requirements.py")
        self.assertEqual(code, PASS, out)

    def test_tasks(self) -> None:
        code, out = run("validate-tasks.py")
        self.assertEqual(code, PASS, out)

    def test_references(self) -> None:
        code, out = run("validate-references.py")
        self.assertEqual(code, PASS, out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
