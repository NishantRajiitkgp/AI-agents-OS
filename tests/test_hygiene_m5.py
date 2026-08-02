#!/usr/bin/env python3
"""Tests for the M5 hygiene and longevity set.

Run: python -m unittest discover -s tests -v

Covers M5-03 (documentation classification), M5-04 (staleness), M5-05 (traceability),
M5-06 (`aios health`), M5-07 (`aios prune`), M5-08 (`aios board`), M5-09 (review debt),
M5-10 (`aios upgrade`), M5-11 (incident schema) and M5-12 (standards schema).

Grouped in one file because they share a fixture — a minimal repository — and eight files each
building one would be eight places to change when the fixture does.

The reports (M5-05 through M5-08) are tested for *not* failing as much as for their content. A
report that can exit non-zero is a gate wearing a report's name, and the whole argument for
them reporting rather than blocking is that the right fix is sometimes to change the
requirement.
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
SCRIPTS = ROOT / ".github" / "scripts"

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2

CONFIG = """\
tier: prototype
template:
  version: "0.1.0"
review_debt:
  window: 10
  max_uncommented_percent: 50
  max_diff_lines: 400
budgets:
  always_on_lines: 200
  agents_md_lines: 150
  growth_window_commits: 20
"""


class RepoCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir()
        (self.dir / "aios" / "config.yml").write_text(CONFIG, encoding="utf-8")
        for sub in ("incidents", "requirements", "tasks", "standards"):
            (self.dir / "aios" / sub).mkdir()
        (self.dir / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")

    def write(self, relative: str, text: str) -> None:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_script(self, name: str, *args: str) -> tuple[int, str]:
        result = subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                                capture_output=True, cwd=str(self.dir))
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")


# --------------------------------------------------------------------------- M5-03, M5-04

class TestDocumentClassification(RepoCase):
    def test_an_unclassified_document_fails_the_build(self) -> None:
        self.write("notes/thoughts.md", "Some prose.\n")
        code, out = self.run_script("check-docs.py", "--root", str(self.dir))
        self.assertEqual(code, FAIL, out)
        self.assertIn("unclassified", out)

    def test_location_classifies_without_a_marker(self) -> None:
        """A per-file marker would be a second place to keep in sync. `docs/decisions/` is
        immutable because it is the ADR directory, and no file needs to restate that."""
        self.write("docs/decisions/ADR-001-a.md", "# A decision\n")
        self.assertEqual(self.run_script("check-docs.py", "--root", str(self.dir))[0], PASS)

    def test_frontmatter_overrides_location(self) -> None:
        self.write("notes/thoughts.md", "---\ndoc_class: checked\n---\n\nProse.\n")
        self.assertEqual(self.run_script("check-docs.py", "--root", str(self.dir))[0], PASS)

    def test_an_invented_class_is_not_a_class(self) -> None:
        self.write("notes/thoughts.md", "---\ndoc_class: probably-fine\n---\n\nProse.\n")
        code, out = self.run_script("check-docs.py", "--root", str(self.dir))
        self.assertEqual(code, FAIL, out)
        self.assertIn("not one of them", out)

    def test_dated_and_owned_needs_an_owner(self) -> None:
        self.write("docs/runbooks/deploy.md", "---\nreview_by: 2030-01-01\n---\n\nSteps.\n")
        code, out = self.run_script("check-docs.py", "--root", str(self.dir))
        self.assertEqual(code, FAIL, out)
        self.assertIn("no owner", out)


class TestStaleness(RepoCase):
    def dated(self, review_by: str) -> None:
        self.write("docs/runbooks/deploy.md",
                   f"---\nowner: a person\nreview_by: {review_by}\nreview_months: 6\n"
                   f"---\n\nSteps.\n")

    def test_past_the_date_reports_but_does_not_block(self) -> None:
        self.dated("2026-06-01")
        code, out = self.run_script("check-docs.py", "--root", str(self.dir),
                                    "--today", "2026-08-02", "--tier", "production")
        self.assertEqual(code, PASS, out)
        self.assertIn("::warning::", out)

    def test_past_double_blocks_at_production(self) -> None:
        self.dated("2026-01-01")
        code, out = self.run_script("check-docs.py", "--root", str(self.dir),
                                    "--today", "2026-08-02", "--tier", "production")
        self.assertEqual(code, FAIL, out)

    def test_past_double_only_reports_at_prototype(self) -> None:
        """At prototype the right answer to a stale document is often deletion, and a blocked
        build cannot be answered with a deletion at three in the morning."""
        self.dated("2026-01-01")
        code, out = self.run_script("check-docs.py", "--root", str(self.dir),
                                    "--today", "2026-08-02", "--tier", "prototype")
        self.assertEqual(code, PASS, out)
        self.assertIn("::warning::", out)

    def test_a_future_date_is_silent(self) -> None:
        self.dated("2030-01-01")
        code, out = self.run_script("check-docs.py", "--root", str(self.dir),
                                    "--today", "2026-08-02", "--tier", "production")
        self.assertEqual(code, PASS, out)
        self.assertNotIn("::warning::", out)


# --------------------------------------------------------------------------- M5-11

class TestIncidentSchema(RepoCase):
    def incident(self, body: str, name: str = "2026-01-01-a-thing-broke.md") -> None:
        self.write(f"aios/incidents/{name}", body)

    def test_an_incident_with_no_control_is_a_regret(self) -> None:
        self.incident("---\ndate: 2026-01-01\ndetected_by: a person\n---\n\n# It broke\n")
        code, out = self.run_script("validate-incidents.py",
                                    "--dir", str(self.dir / "aios" / "incidents"))
        self.assertEqual(code, FAIL, out)
        self.assertIn("regret", out)

    def test_naming_no_practical_control_is_accepted(self) -> None:
        """A schema that will not accept 'there is no control' gets a fictional one instead."""
        self.incident("---\ndate: 2026-01-01\ndetected_by: a person\n"
                      "no_control_because: the block is network policy outside this "
                      "repository's reach\n---\n\n# It broke\n")
        self.assertEqual(self.run_script(
            "validate-incidents.py", "--dir", str(self.dir / "aios" / "incidents"))[0], PASS)

    def test_declaring_both_is_a_contradiction(self) -> None:
        self.incident("---\ndate: 2026-01-01\ndetected_by: a person\n"
                      "control: a gate that rejects the malformed input at the boundary\n"
                      "no_control_because: there is nothing practical to do about it here\n"
                      "---\n\n# It broke\n")
        code, out = self.run_script("validate-incidents.py",
                                    "--dir", str(self.dir / "aios" / "incidents"))
        self.assertEqual(code, FAIL, out)
        self.assertIn("one of them is not true", out)

    def test_a_token_control_is_not_a_control(self) -> None:
        self.incident("---\ndate: 2026-01-01\ndetected_by: a person\ncontrol: fixed\n"
                      "---\n\n# It broke\n")
        code, out = self.run_script("validate-incidents.py",
                                    "--dir", str(self.dir / "aios" / "incidents"))
        self.assertEqual(code, FAIL, out)
        self.assertIn("checkbox", out)

    def test_the_filename_date_must_match_the_field(self) -> None:
        self.incident("---\ndate: 2026-02-02\ndetected_by: a person\n"
                      "control: a gate that rejects it at the boundary now\n---\n\n# It\n")
        code, out = self.run_script("validate-incidents.py",
                                    "--dir", str(self.dir / "aios" / "incidents"))
        self.assertEqual(code, FAIL, out)
        self.assertIn("filed under", out)

    def test_blocks_work_must_be_a_boolean(self) -> None:
        self.incident("---\ndate: 2026-01-01\ndetected_by: a person\nblocks_work: 'yes'\n"
                      "control: a gate that rejects it at the boundary now\n---\n\n# It\n")
        code, out = self.run_script("validate-incidents.py",
                                    "--dir", str(self.dir / "aios" / "incidents"))
        self.assertEqual(code, FAIL, out)
        self.assertIn("truthy by accident", out)

    def test_this_repositorys_incidents_conform(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPTS / "validate-incidents.py")],
                                capture_output=True, cwd=str(ROOT))
        self.assertEqual(result.returncode, PASS,
                         (result.stdout + result.stderr).decode("utf-8", "replace"))


# --------------------------------------------------------------------------- M5-12

class TestStandardsSchema(RepoCase):
    def standard(self, body: str) -> list[str]:
        self.write("aios/standards/style.md", body)
        return self.run_script("validate-standards.py",
                               "--dir", str(self.dir / "aios" / "standards"))

    def test_a_rule_declaring_neither_is_prose_pretending(self) -> None:
        code, out = self.standard("## STYLE-1 — Name things well\nBe thoughtful.\n")
        self.assertEqual(code, FAIL, out)
        self.assertIn("sounds like a rule", out)

    def test_unenforceable_with_a_reason_is_accepted(self) -> None:
        code, out = self.standard(
            "## STYLE-1 — Name things well\n"
            "**Unenforceable:** no linter can tell a good name from a bad one\n"
            "Prose explaining what good means here.\n")
        self.assertEqual(code, PASS, out)

    def test_an_enforced_rule_may_not_restate_the_check(self) -> None:
        """Past two lines the file is a second, informal statement of what the linter says
        exactly — and when the two drift, people believe the prose."""
        code, out = self.standard(
            "## STYLE-1 — Name things well\n"
            '**Enforced by:** hygiene.yml step "Names conform"\n'
            "One.\nTwo.\nThree.\nFour.\n")
        self.assertEqual(code, FAIL, out)
        self.assertIn("cap is 2", out)

    def test_a_file_whose_rules_are_all_enforced_is_deleted(self) -> None:
        code, out = self.standard(
            '## STYLE-1 — A\n**Enforced by:** hygiene.yml step "A"\n\n'
            '## STYLE-2 — B\n**Enforced by:** hygiene.yml step "B"\n')
        self.assertEqual(code, FAIL, out)
        self.assertIn("Delete it", out)

    def test_a_mixed_file_survives(self) -> None:
        code, out = self.standard(
            '## STYLE-1 — A\n**Enforced by:** hygiene.yml step "A"\n\n'
            "## STYLE-2 — B\n**Unenforceable:** judgement about tone cannot be linted\n")
        self.assertEqual(code, PASS, out)

    def test_a_duplicate_rule_id_is_caught(self) -> None:
        code, out = self.standard(
            "## STYLE-1 — A\n**Unenforceable:** judgement about tone cannot be linted\n\n"
            "## STYLE-1 — B\n**Unenforceable:** judgement about tone cannot be linted\n")
        self.assertEqual(code, FAIL, out)
        self.assertIn("defined twice", out)

    def test_an_empty_directory_passes(self) -> None:
        code, out = self.run_script("validate-standards.py",
                                    "--dir", str(self.dir / "aios" / "standards"))
        self.assertEqual(code, PASS, out)
        self.assertIn("not yet needed", out)


# --------------------------------------------------------------------------- M5-05

class TestTraceability(unittest.TestCase):
    def run_report(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPTS / "report-traceability.py"), *args],
            capture_output=True, cwd=str(ROOT))
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")

    def test_it_reports_and_never_blocks(self) -> None:
        """The right fix is sometimes to change the requirement, and a gate presuming the code
        is wrong trains people to satisfy it dishonestly."""
        self.assertEqual(self.run_report()[0], PASS)

    def test_it_names_requirements_with_no_test(self) -> None:
        code, out = self.run_report("--format", "json")
        data = json.loads(out)
        self.assertIn("requirements_without_a_test", data)

    def test_the_annotation_is_what_gives_a_failure_a_reason(self) -> None:
        """STATE-7 is claimed by the validator tests. If that annotation is removed, a failure
        there stops saying which requirement it violates."""
        code, out = self.run_report("--format", "json")
        covered = json.loads(out)["covered"]
        self.assertIn("STATE-7", covered)
        self.assertIn("test_validators.py", covered["STATE-7"])

    def test_the_untestable_ones_are_not_falsely_claimed(self) -> None:
        """STATE-2 through STATE-5 describe what the binary does, and the binary does not
        exist. Annotating the nearest passing test would be the exact dishonesty the report
        exists to make visible."""
        data = json.loads(self.run_report("--format", "json")[1])
        for requirement in ("STATE-2", "STATE-3", "STATE-4", "STATE-5"):
            self.assertIn(requirement, data["requirements_without_a_test"])


# --------------------------------------------------------------------------- M5-06 .. M5-08

class TestTheReports(unittest.TestCase):
    def run_report(self, name: str, *args: str) -> tuple[int, str]:
        result = subprocess.run([sys.executable, str(SCRIPTS / name), *args],
                                capture_output=True, cwd=str(ROOT))
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")

    def test_health_runs_and_does_not_block(self) -> None:
        self.assertEqual(self.run_report("report-health.py")[0], PASS)

    def test_health_prints_what_it_cannot_measure(self) -> None:
        """A dashboard of the four things that happen to be computable, with the eight that
        are not left off, reads as a healthy system."""
        code, out = self.run_report("report-health.py")
        self.assertIn("not measurable yet", out)

    def test_health_reports_the_learning_ratio(self) -> None:
        """Incidents that produced a control over total incidents — the design's single best
        indicator that this is an operating system rather than a filing system."""
        data = json.loads(self.run_report("report-health.py", "--format", "json")[1])
        learning = data["learning"]["incidents_that_produced_a_control"]
        self.assertIsNotNone(learning["value"])

    def test_board_renders_and_stores_nothing(self) -> None:
        code, out = self.run_report("render-board.py")
        self.assertEqual(code, PASS, out)
        self.assertIn("stored nowhere", out)

    def test_no_board_file_is_committed(self) -> None:
        """A stored view is a second source of truth that looks authoritative while it drifts."""
        self.assertFalse((ROOT / "board.md").exists())
        self.assertIn("board", (ROOT / ".gitignore").read_text(encoding="utf-8"))

    def test_prune_proposes_and_never_deletes(self) -> None:
        code, out = self.run_report("propose-prune.py")
        self.assertEqual(code, PASS, out)
        before = {p.name for p in (ROOT / "aios" / "tasks").glob("*.md")}
        self.run_report("propose-prune.py")
        self.assertEqual(before, {p.name for p in (ROOT / "aios" / "tasks").glob("*.md")})


# --------------------------------------------------------------------------- M5-09

class TestReviewDebt(RepoCase):
    def reviews(self, entries: list[dict]) -> str:
        path = self.dir / "reviews.json"
        path.write_text(json.dumps(entries), encoding="utf-8")
        return str(path)

    def test_no_data_is_not_a_pass(self) -> None:
        """Zero merged pull requests is zero evidence about whether anyone is reading, and
        reporting that as healthy would be the failure this measure exists to catch."""
        code, out = self.run_script("check-review-debt.py", "--root", str(self.dir))
        self.assertEqual(code, COULD_NOT_RUN, out)
        self.assertIn("ADR-014", out)

    def test_engaged_reviews_pass(self) -> None:
        data = self.reviews([{"state": "APPROVED", "comments": 3, "diff_lines": 120}] * 4)
        code, out = self.run_script("check-review-debt.py", "--root", str(self.dir),
                                    "--reviews", data)
        self.assertEqual(code, PASS, out)

    def test_mostly_uncommented_approvals_stop_the_work(self) -> None:
        data = self.reviews([{"state": "APPROVED", "comments": 0, "diff_lines": 100}] * 3
                            + [{"state": "APPROVED", "comments": 2, "diff_lines": 100}])
        code, out = self.run_script("check-review-debt.py", "--root", str(self.dir),
                                    "--reviews", data)
        self.assertEqual(code, FAIL, out)
        self.assertIn("review is the bottleneck", out)

    def test_an_oversized_diff_is_reported_not_blocked(self) -> None:
        data = self.reviews([{"state": "APPROVED", "comments": 4, "diff_lines": 5000}] * 3)
        code, out = self.run_script("check-review-debt.py", "--root", str(self.dir),
                                    "--reviews", data)
        self.assertEqual(code, PASS, out)
        self.assertIn("::warning::", out)

    def test_the_dropped_half_is_recorded_as_a_decision(self) -> None:
        adr = ROOT / "docs" / "decisions" / "ADR-014-time-on-diff-is-not-measurable.md"
        self.assertTrue(adr.is_file())
        text = adr.read_text(encoding="utf-8")
        self.assertIn("dropped", text)
        self.assertNotIn("max_uncommented_fraction",
                         (SCRIPTS / "check-review-debt.py").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- M5-10

class TestUpgrade(RepoCase):
    CHANGELOG = """\
# Changelog

## 0.3.0
- **judgement** — adds a secrets-scanning gate at every tier

## 0.2.0
- **mechanical** — fixes an off-by-one in the ratchet comparison

## 0.1.0
- initial
"""

    def changelog(self, text: str | None = None) -> str:
        path = self.dir / "CHANGELOG.md"
        path.write_text(text or self.CHANGELOG, encoding="utf-8")
        return str(path)

    def test_it_separates_mechanical_from_judgement(self) -> None:
        code, out = self.run_script("check-upgrade.py", "--root", str(self.dir),
                                    "--changelog", self.changelog())
        self.assertEqual(code, FAIL, out)
        self.assertIn("mechanical", out)
        self.assertIn("judgement", out)

    def test_only_mechanical_changes_do_not_need_a_conversation(self) -> None:
        code, out = self.run_script(
            "check-upgrade.py", "--root", str(self.dir),
            "--changelog", self.changelog("# Changelog\n\n## 0.2.0\n- **mechanical** — a fix\n"
                                          "\n## 0.1.0\n- initial\n"))
        self.assertEqual(code, PASS, out)

    def test_an_unclassified_change_is_treated_as_judgement(self) -> None:
        """The safe direction costs a pull request nobody needed. The other silently adds a
        gate that starts failing builds on a Friday."""
        code, out = self.run_script(
            "check-upgrade.py", "--root", str(self.dir),
            "--changelog", self.changelog("# Changelog\n\n## 0.2.0\n- something changed\n"
                                          "\n## 0.1.0\n- initial\n"))
        self.assertEqual(code, FAIL, out)
        self.assertIn("unclassified", out)

    def test_being_on_the_newest_version_is_quiet(self) -> None:
        code, out = self.run_script(
            "check-upgrade.py", "--root", str(self.dir),
            "--changelog", self.changelog("# Changelog\n\n## 0.1.0\n- initial\n"))
        self.assertEqual(code, PASS, out)
        self.assertIn("newest", out)

    def test_an_unknown_pin_cannot_run_rather_than_claiming_current(self) -> None:
        """Comparing by position means an unrecognised pin would otherwise silently return
        nothing — a tool reporting 'up to date' because it could not read the file."""
        code, out = self.run_script(
            "check-upgrade.py", "--root", str(self.dir),
            "--changelog", self.changelog("# Changelog\n\n## 9.9.9\n- **mechanical** — x\n"))
        self.assertEqual(code, COULD_NOT_RUN, out)

    def test_nothing_is_fetched_implicitly(self) -> None:
        code, out = self.run_script("check-upgrade.py", "--root", str(self.dir),
                                    "--changelog", str(self.dir / "absent.md"))
        self.assertEqual(code, COULD_NOT_RUN, out)
        self.assertIn("on purpose", out)


class TestTheGatesAreRegistered(unittest.TestCase):
    def test_every_new_step_declares_a_class(self) -> None:
        import yaml
        gates = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        ids = {g["id"] for g in gates["gates"]}
        for expected in ("state.doc_classification", "state.incident_schema",
                         "state.standards_schema", "process.traceability"):
            self.assertIn(expected, ids)

    def test_the_traceability_report_is_report_class(self) -> None:
        import yaml
        gates = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        entry = next(g for g in gates["gates"] if g["id"] == "process.traceability")
        self.assertEqual(entry["class"], "report")


if __name__ == "__main__":
    unittest.main(verbosity=2)
