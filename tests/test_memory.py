#!/usr/bin/env python3
"""Tests for the memory-hygiene checks (M5-01).

Run: python -m unittest discover -s tests -v

The failure being defended against has one shape: an instruction that was true when written
and is not now. It reads exactly like a correct one, which is why it needs a machine.

Most of these tests are about *not* firing. A path checker's difficulty is not finding broken
references, it is not drowning them — the first draft of this one reported 104 problems in this
repository, of which none was real. A check nobody can act on gets switched off, so the tests
that pin the exclusions matter as much as the ones that pin the detections.
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-memory.py"
REFERENCES = ROOT / ".github" / "scripts" / "validate-references.py"

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2


def load(path: Path):
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(path.stem.replace("-", "_"), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


memory = load(SCRIPT)


class MemoryCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir()
        (self.dir / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")

    def write(self, relative: str, text: str) -> None:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def run_check(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.dir), *extra],
            capture_output=True)
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")

    def assertRejects(self, needle: str = "does not exist") -> None:
        code, out = self.run_check()
        self.assertEqual(code, FAIL, out)
        self.assertIn(needle, out)

    def assertAccepts(self) -> None:
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)


class TestBrokenReferences(MemoryCase):
    def test_a_broken_link_is_caught(self) -> None:
        self.write("AGENTS.md", "See [the ADR](docs/decisions/ADR-999-nope.md).\n")
        self.assertRejects()

    def test_a_resolving_link_is_not(self) -> None:
        self.write("docs/decisions/ADR-001.md", "text\n")
        self.write("AGENTS.md", "See [the ADR](docs/decisions/ADR-001.md).\n")
        self.assertAccepts()

    def test_a_broken_path_in_prose_is_caught(self) -> None:
        """Never clicked, and therefore never noticed. This is what an agent acts on: a
        sentence naming `aios/tasks/` is an instruction to look there."""
        self.write("AGENTS.md", "State lives in `aios/absent/`.\n")
        self.assertRejects()

    def test_a_glob_is_checked_down_to_its_literal_prefix(self) -> None:
        """The part a rename invalidates. The rest is unknown by construction."""
        self.write("AGENTS.md", "Tasks are `aios/gone/**/*.md`.\n")
        self.assertRejects()

    def test_a_glob_whose_prefix_exists_passes(self) -> None:
        (self.dir / "aios" / "tasks").mkdir()
        self.write("AGENTS.md", "Tasks are `aios/tasks/**/*.md`.\n")
        self.assertAccepts()

    def test_a_link_is_checked_even_where_prose_is_not(self) -> None:
        """A link is navigation. It is broken wherever it is, including in a document nobody
        may edit — an ADR whose link dead-ends does not become correct by being immutable."""
        self.write("docs/decisions/ADR-001.md", "See [gone](../../aios/absent.md).\n")
        self.assertRejects()

    def test_a_relative_link_resolves_from_the_file_not_the_root(self) -> None:
        self.write("docs/decisions/ADR-001.md", "text\n")
        self.write("docs/decisions/ADR-002.md", "See [one](ADR-001.md).\n")
        self.assertAccepts()


class TestWhatIsDeliberatelyNotChecked(MemoryCase):
    def test_prose_in_an_append_only_record_is_history_not_staleness(self) -> None:
        """An incident naming a file that was deliberately removed afterwards is describing
        what was true then. Demanding it resolve would either falsify the record or resurrect
        the file."""
        self.write("aios/incidents/2026-01-01-a.md", "The file `probe-nested/AGENTS.md` was "
                                                     "staged and later removed.\n")
        self.assertAccepts()

    def test_a_bare_name_resolves_anywhere_in_the_tree(self) -> None:
        """A sentence about `check-ratchets.py` is a correct sentence. Demanding the full path
        every time would make the writing worse to satisfy a checker, and the rename — which
        is the thing worth catching — is still caught."""
        self.write(".github/scripts/check-ratchets.py", "x\n")
        self.write("AGENTS.md", "The ratchets are in `check-ratchets.py`.\n")
        self.assertAccepts()

    def test_a_bare_name_that_exists_nowhere_is_still_caught(self) -> None:
        self.write("AGENTS.md", "The ratchets are in `check-deleted.py`.\n")
        self.assertRejects()

    def test_a_wrong_path_is_not_rescued_by_its_basename(self) -> None:
        """The leniency is for names written *as* names. Once prose commits to a directory it
        is making a claim about where the file is, and a claim that is wrong is worth exactly
        as much as a missing file — arguably more, since it sends the reader somewhere."""
        self.write(".github/scripts/check-ratchets.py", "x\n")
        self.write("AGENTS.md", "The ratchets are in `scripts/check-ratchets.py`.\n")
        self.assertRejects()

    def test_a_link_must_resolve_as_written_rather_than_by_name(self) -> None:
        """Prose is read; a link is clicked. Finding the file somewhere else does not make the
        link work, so the leniency that applies to a sentence cannot apply to a target."""
        self.write(".github/scripts/check-ratchets.py", "x\n")
        self.write("AGENTS.md", "See [the ratchets](check-ratchets.py).\n")
        self.assertRejects()

    def test_a_slash_command_is_not_a_path(self) -> None:
        self.write("AGENTS.md", "Run `/aios-check` to see the gates.\n")
        self.assertAccepts()

    def test_a_pinned_action_is_not_a_path(self) -> None:
        self.write("AGENTS.md", "Pinned as `actions/checkout@v4`.\n")
        self.assertAccepts()

    def test_a_bare_extension_is_a_file_type(self) -> None:
        self.write("AGENTS.md", "A `.ps1` cannot execute here.\n")
        self.assertAccepts()

    def test_a_placeholder_is_not_a_path(self) -> None:
        self.write("AGENTS.md", "Write `aios/tasks/<task-id>.md` and `$ARGUMENTS`.\n")
        self.assertAccepts()

    def test_a_url_is_not_checked(self) -> None:
        self.write("AGENTS.md", "See [docs](https://example.com/a/b.md) and [#anchor](#x).\n")
        self.assertAccepts()


class TestEscapingTheRepository(MemoryCase):
    def test_a_reference_that_climbs_out_is_caught(self) -> None:
        """Nothing here is checked against the filesystem outside the project, so this cannot
        be verified — and it should not be exempt either. The usual cause of one `../` too
        many is a directory move, which is what broke every relative path in this repository
        the day the tree was flattened."""
        self.write("AGENTS.md", "See [outside](../../../elsewhere/thing.md).\n")
        self.assertRejects()

    def test_climbing_and_returning_inside_is_fine(self) -> None:
        self.write("aios/glossary.md", "term\n")
        self.write("docs/runbooks/deploy.md", "See [glossary](../../aios/glossary.md).\n")
        self.assertAccepts()


# Review dates moved to `check-docs.py` at M5-04, which owns the dated-and-owned class and
# grades its response by tier. These tests moved with them — see test_hygiene_m5.py,
# TestStaleness. Leaving a copy here would be a second definition of when a document is stale.


class TestCouldNotRun(MemoryCase):
    def test_a_directory_that_is_not_a_repository(self) -> None:
        other = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, other, True)
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(other)],
                                capture_output=True)
        self.assertEqual(result.returncode, COULD_NOT_RUN)

    def test_a_malformed_today_is_not_a_verdict(self) -> None:
        self.assertEqual(self.run_check("--today", "not-a-date")[0], COULD_NOT_RUN)


class TestTheRuleHasOneImplementation(unittest.TestCase):
    """Link checking moved here from validate-references.py rather than being copied. Two
    implementations of one rule give two answers the day one is edited (D-040)."""

    def test_validate_references_no_longer_checks_links(self) -> None:
        text = REFERENCES.read_text(encoding="utf-8")
        self.assertNotIn("def check_links", text)
        self.assertNotIn("LINK.findall", text)

    def test_it_still_checks_the_id_graph(self) -> None:
        text = REFERENCES.read_text(encoding="utf-8")
        for name in ("check_ids_unique", "check_satisfies", "check_task_refs"):
            self.assertIn(name, text)

    def test_the_link_it_used_to_catch_is_still_caught(self) -> None:
        """The case moved with the rule. A requirement file linking at a missing ADR was
        rejected before and has to stay rejected, or the move quietly lost coverage."""
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "aios" / "requirements").mkdir(parents=True)
        (directory / "aios" / "requirements" / "state.md").write_text(
            "See [the ADR](../../docs/decisions/ADR-999-nope.md).\n", encoding="utf-8")
        result = subprocess.run([sys.executable, str(SCRIPT), "--root", str(directory)],
                                capture_output=True)
        self.assertEqual(result.returncode, FAIL)


class TestThisRepository(unittest.TestCase):
    def test_every_path_named_in_the_instruction_layer_exists(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, PASS,
                         (result.stdout + result.stderr).decode("utf-8", "replace"))

    def test_the_scope_covers_the_always_on_set(self) -> None:
        """Whatever else is checked, the files loaded on every turn must be. A stale line in
        AGENTS.md is followed by every session with full confidence."""
        covered = {p.relative_to(ROOT).as_posix() for p in memory.expand(ROOT,
                                                                        memory.INSTRUCTIONS)}
        self.assertIn("AGENTS.md", covered)
        self.assertIn(".cursor/rules/no-presumed-stack.mdc", covered)
        self.assertIn(".claude/agents/explorer.md", covered)

    def test_the_design_set_is_out_of_scope(self) -> None:
        """It does not ship in a clone (ADR-004) and is written as worked examples about a
        hypothetical project. Asserting illustrations exist would train people to create files
        to satisfy a checker."""
        covered = {p.relative_to(ROOT).as_posix() for p in memory.expand(ROOT,
                                                                        memory.NAVIGATION)}
        self.assertFalse([p for p in covered if p.startswith("docs/design/")])

    def test_the_gate_is_registered(self) -> None:
        import yaml
        gates = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        self.assertEqual(len([g for g in gates["gates"] if g["id"] == "state.memory_hygiene"]),
                         1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
