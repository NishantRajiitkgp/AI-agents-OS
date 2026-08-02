#!/usr/bin/env python3
"""Tests for the subagents and for the verifier's findings format.

Run: python -m unittest discover -s tests -v

The shared checks run over every file in `.claude/agents/`, discovered rather than listed, so
a third subagent cannot be added without meeting them. D-024 says there are exactly two; if
that changes, this is the first thing that should have an opinion about it.

The findings format is parsed here rather than only described in prose. `M4-10` retires the
verifier if findings-per-review trends to zero, and a revisit trigger that nothing can count
is decoration — so the format has a parser and the parser has tests, before the number is
needed.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / ".claude" / "agents"
SCRIPT = ROOT / ".github" / "scripts" / "check-always-on.py"

# The shape the verifier is told to emit. Kept here because this is what M4-10 will parse, and
# a format defined only in the instruction file is a format nothing can hold to.
FINDING = re.compile(r"^- \[(blocking|question|nit)\] (\S+?):(\d+) — (.+)$")
COUNT = re.compile(r"^verifier: (\d+) finding\(s\)$", re.MULTILINE)


def load(path: Path):
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


always_on = load(SCRIPT)


def parse_review(text: str) -> tuple[list[tuple[str, str, int, str]], int | None]:
    """Findings and the declared count. A missing count is None, not zero.

    The distinction is the point: a review that found nothing and a review that never ran must
    not parse to the same thing, or the second reads as approval.
    """
    findings = [(m.group(1), m.group(2), int(m.group(3)), m.group(4))
                for line in text.splitlines() if (m := FINDING.match(line.strip()))]
    declared = COUNT.search(text)
    return findings, int(declared.group(1)) if declared else None


def subagents() -> list[Path]:
    return sorted(AGENTS.glob("*.md"))


class TestEverySubagent(unittest.TestCase):
    """Discovered, not listed, so the next one is covered the day it lands."""

    def test_there_is_at_least_one(self) -> None:
        self.assertTrue(subagents(), "no subagents found; the glob or the location is wrong")

    def test_each_has_frontmatter_with_a_name_and_description(self) -> None:
        for path in subagents():
            with self.subTest(subagent=path.name):
                data = yaml.safe_load(
                    "\n".join(always_on.frontmatter(path.read_text(encoding="utf-8"))))
                self.assertEqual(data.get("name"), path.stem,
                                 "the declared name and the filename must agree")
                self.assertTrue(str(data.get("description", "")).strip())

    def test_none_holds_a_write_tool(self) -> None:
        """D-024: both subagents exist for context isolation. Neither is meant to change code."""
        for path in subagents():
            with self.subTest(subagent=path.name):
                data = yaml.safe_load(
                    "\n".join(always_on.frontmatter(path.read_text(encoding="utf-8"))))
                granted = {tool.strip() for tool in str(data["tools"]).split(",")}
                self.assertEqual(granted, {"Read", "Grep", "Glob"})

    def test_each_description_says_when_to_reach_for_it(self) -> None:
        """The description is what a caller routes on, and the only part always resident."""
        for path in subagents():
            with self.subTest(subagent=path.name):
                data = yaml.safe_load(
                    "\n".join(always_on.frontmatter(path.read_text(encoding="utf-8"))))
                self.assertIn("Use", data["description"])

    def test_each_description_stays_small(self) -> None:
        config = yaml.safe_load((ROOT / "aios" / "config.yml").read_text(encoding="utf-8"))
        cap = config["budgets"]["always_on_lines"] // 20
        for path in subagents():
            with self.subTest(subagent=path.name):
                self.assertLessEqual(
                    always_on.description_lines(path.read_text(encoding="utf-8")), cap)

    def test_each_treats_what_it_reads_as_data(self) -> None:
        """Both read attacker-influenced text on behalf of the context that called them."""
        for path in subagents():
            with self.subTest(subagent=path.name):
                self.assertIn("Untrusted content", path.read_text(encoding="utf-8"))

    def test_the_pair_is_the_pair_d024_named(self) -> None:
        self.assertEqual([path.stem for path in subagents()], ["explorer", "verifier"])


class TestTheExplorer(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (AGENTS / "explorer.md").read_text(encoding="utf-8")

    def test_it_is_where_the_measurement_says_cursor_looks(self) -> None:
        """ADR-009 §2, on the corrected M0 reading. The task text predates that correction."""
        self.assertTrue((AGENTS / "explorer.md").is_file())

    def test_it_states_that_not_found_is_an_answer(self) -> None:
        """An explorer that invents a location costs more than one that finds nothing."""
        self.assertIn("not here", self.text)


class TestTheVerifier(unittest.TestCase):
    def setUp(self) -> None:
        self.text = (AGENTS / "verifier.md").read_text(encoding="utf-8")

    def test_it_is_not_a_persona(self) -> None:
        """01: 3.1 is strong evidence that a role buys tone, not detection."""
        self.assertNotRegex(self.text.lower(), r"you are an? (senior|expert|experienced)")

    def test_it_says_why_it_is_not_a_persona(self) -> None:
        """Otherwise the next person to read it adds one, reasonably."""
        self.assertIn("persona", self.text.lower())

    def test_it_names_context_isolation_as_the_mechanism(self) -> None:
        self.assertIn("trajectory", self.text)

    def test_it_declares_zero_findings_acceptable(self) -> None:
        """The counter to the review-quota failure the charter documents."""
        self.assertIn("Zero findings is a complete review", self.text)

    def test_it_forbids_repeating_the_machine_pass(self) -> None:
        """A finding a gate already reports inflates the count M4-10 depends on."""
        self.assertIn("Do not repeat the machine pass", self.text)

    def test_the_documented_format_is_the_one_that_parses(self) -> None:
        """The examples in the file are the specification; drift between them is the bug."""
        examples = [line.strip() for line in self.text.splitlines()
                    if line.strip().startswith("- [")]
        self.assertEqual(len(examples), 3, "one example per severity")
        for line in examples:
            with self.subTest(example=line):
                self.assertRegex(line, FINDING)

    def test_the_documented_count_line_is_the_one_that_parses(self) -> None:
        self.assertIsNotNone(COUNT.search(self.text))


class TestTheFindingsFormat(unittest.TestCase):
    """M4-10 counts these. A trigger nothing can count cannot fire."""

    def test_a_review_with_findings_parses(self) -> None:
        findings, declared = parse_review(
            "- [blocking] src/main.rs:42 — acceptance criterion 2 is not satisfied\n"
            "- [nit] src/main.rs:9 — name reads oddly\n"
            "verifier: 2 finding(s)\n")
        self.assertEqual(len(findings), 2)
        self.assertEqual(declared, 2)
        self.assertEqual(findings[0][0], "blocking")
        self.assertEqual(findings[0][2], 42)

    def test_an_empty_review_is_distinguishable_from_a_missing_one(self) -> None:
        empty, declared = parse_review("Nothing to report.\nverifier: 0 finding(s)\n")
        self.assertEqual((empty, declared), ([], 0))
        missing, none = parse_review("Looks fine to me.\n")
        self.assertEqual((missing, none), ([], None),
                         "a review with no count must not read as zero findings")

    def test_a_miscounted_review_is_detectable(self) -> None:
        """The count and the lines can disagree, and something has to be able to see it."""
        findings, declared = parse_review(
            "- [blocking] a.py:1 — x\nverifier: 5 finding(s)\n")
        self.assertNotEqual(len(findings), declared)

    def test_an_unknown_severity_does_not_parse(self) -> None:
        findings, _ = parse_review("- [critical] a.py:1 — x\nverifier: 1 finding(s)\n")
        self.assertEqual(findings, [])

    def test_a_finding_without_a_location_does_not_parse(self) -> None:
        findings, _ = parse_review("- [blocking] the code is wrong\nverifier: 1 finding(s)\n")
        self.assertEqual(findings, [])


class TestTheReviewPacketPointsAtTheRightTask(unittest.TestCase):
    def test_the_verifier_section_does_not_cite_the_explorer_task(self) -> None:
        source = (ROOT / ".github" / "scripts" / "render-review-packet.py").read_text(
            encoding="utf-8")
        line = [l for l in source.splitlines() if "verifier subagent found" in l][0]
        index = source.splitlines().index(line)
        entry = "\n".join(source.splitlines()[index:index + 3])
        self.assertNotIn("M4-01", entry, "M4-01 is the explorer; the verifier is M4-02")


if __name__ == "__main__":
    unittest.main(verbosity=2)
