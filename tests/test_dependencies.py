#!/usr/bin/env python3
"""Tests for the supply-chain controls.

Run: python -m unittest discover -s tests -v

M3-05's criterion is that each control has a fixture that trips it, so every check below has
one that fails and, where the distinction matters, a neighbour that passes.

The controls exist because package hallucination is the highest-probability AI-specific risk
here: ~19.7% of generated package references do not exist, and 43% of the invented names
repeat across identical prompts — repeatable enough to pre-register and wait for. The 90-day
minimum age is the counter, and it is the one worth having fixtures for in both directions,
since a control that rejects everything new would simply be turned off.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-dependencies.py"

CLEAN, VIOLATION, CANNOT_RUN = 0, 1, 2
TODAY = "2026-07-31"
SHA = "11d5960a326750d5838078e36cf38b85af677262"

ALLOWLIST = f"""\
policy:
  min_age_days: 90
  typosquat_distance: 2
dependencies:
  - name: actions/checkout
    ecosystem: github-actions
    version: {SHA}
    first_release: 2023-09-04
    reason: Every workflow needs the repository present before it can check anything at all.
"""

WORKFLOW = f"""\
name: Demo
on: [push]
jobs:
  demo:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@{SHA}
      - name: Check
        run: echo ok
"""


def network_available() -> bool:
    try:
        urllib.request.urlopen("https://pypi.org/pypi/PyYAML/json", timeout=10).close()
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


class DependencyCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.write("aios/dependencies.yml", ALLOWLIST)
        self.write(".github/workflows/demo.yml", WORKFLOW)

    def write(self, relative: str, text: str) -> None:
        path = self.dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text), encoding="utf-8")

    def check(self, *extra: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(self.dir), "--today", TODAY, *extra],
            capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr

    def assertTrips(self, fragment: str) -> None:
        code, out = self.check()
        self.assertEqual(code, VIOLATION, f"expected a violation, got exit {code}\n{out}")
        self.assertIn(fragment, out)


class TestBaseline(DependencyCase):
    def test_an_allowlisted_pinned_dependency_passes(self) -> None:
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)


class TestActionPinning(DependencyCase):
    def test_a_tag_pinned_action_trips(self) -> None:
        """A tag is mutable, and an action runs arbitrary code in CI holding a token."""
        self.write(".github/workflows/demo.yml", WORKFLOW.replace(SHA, "v4"))
        self.assertTrips("is a tag and not a commit")

    def test_an_undeclared_action_trips(self) -> None:
        self.write(".github/workflows/demo.yml", WORKFLOW + """\
      - uses: some-org/publish-action@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
""")
        self.assertTrips("is not in the allowlist")

    def test_a_sha_disagreeing_with_the_allowlist_trips(self) -> None:
        self.write(".github/workflows/demo.yml", WORKFLOW.replace(SHA, "b" * 40))
        self.assertTrips("but the allowlist says")


class TestMinimumAge(DependencyCase):
    """The specific counter to a pre-registered hallucinated name."""

    def test_a_package_under_ninety_days_trips(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST.replace("2023-09-04", "2026-07-01"))
        self.assertTrips("under the 90-day minimum")

    def test_a_package_over_ninety_days_passes(self) -> None:
        """A control that rejected everything new would simply be switched off."""
        self.write("aios/dependencies.yml", ALLOWLIST.replace("2023-09-04", "2026-01-01"))
        self.assertEqual(self.check()[0], CLEAN)

    def test_the_boundary_is_ninety_days_exactly(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST.replace("2023-09-04", "2026-05-02"))
        self.assertEqual(self.check()[0], CLEAN, "90 days exactly must pass")
        self.write("aios/dependencies.yml", ALLOWLIST.replace("2023-09-04", "2026-05-03"))
        self.assertEqual(self.check()[0], VIOLATION, "89 days must not")

    def test_a_missing_release_date_trips(self) -> None:
        self.write("aios/dependencies.yml",
                   ALLOWLIST.replace("first_release: 2023-09-04", "first_release: soon"))
        self.assertTrips("is not a date")


class TestTyposquats(DependencyCase):
    def test_two_names_within_the_distance_trip(self) -> None:
        """The lookalike sits beside the real one, where a reader's eye slides over it."""
        self.write("aios/dependencies.yml", ALLOWLIST + f"""\
  - name: actions/checkuot
    ecosystem: github-actions
    version: {SHA}
    first_release: 2023-09-04
    reason: This is the lookalike, and it should never be allowed to sit here quietly.
""")
        self.assertTrips("differ by")

    def test_clearly_different_names_pass(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST + f"""\
  - name: actions/setup-python
    ecosystem: github-actions
    version: {SHA}
    first_release: 2023-09-04
    reason: Needed so that the provisional Python gate layer has an interpreter to run on.
""")
        self.assertEqual(self.check()[0], CLEAN)

    def test_an_org_prefix_alone_does_not_trigger_it(self) -> None:
        """Otherwise every action from one organisation flags every other."""
        self.write("aios/dependencies.yml", ALLOWLIST + f"""\
  - name: other-org/checkout
    ecosystem: github-actions
    version: {SHA}
    first_release: 2023-09-04
    reason: A genuinely different organisation publishing an identically named action.
""")
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)


class TestDeclarationQuality(DependencyCase):
    def test_a_dependency_with_no_reason_trips(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST.replace(
            "reason: Every workflow needs the repository present before it can check anything "
            "at all.", "reason: needed"))
        self.assertTrips("no reason worth reading")

    def test_a_dependency_with_no_version_trips(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST.replace(f"    version: {SHA}\n", ""))
        self.assertTrips("declares no version")


class TestPythonDependencies(DependencyCase):
    def test_an_undeclared_third_party_import_trips(self) -> None:
        self.write(".github/scripts/thing.py", "import requests\n")
        self.assertTrips("is not in the allowlist")

    def test_a_stdlib_import_does_not_trip(self) -> None:
        self.write(".github/scripts/thing.py", "import json\nimport pathlib\n")
        self.assertEqual(self.check()[0], CLEAN)

    def test_a_local_module_import_does_not_trip(self) -> None:
        self.write(".github/scripts/helper.py", "x = 1\n")
        self.write(".github/scripts/thing.py", "import helper\n")
        self.assertEqual(self.check()[0], CLEAN)

    def test_prose_is_not_read_as_an_import(self) -> None:
        """A regex over the source reported a dependency named `in`, from a docstring.

        The line was a sentence ending "every non-stdlib / import in the gate scripts". The
        fix was to parse rather than pattern-match, which removes the class of bug instead of
        narrowing it.
        """
        self.write(".github/scripts/thing.py",
                   '"""Doc.\n\nWe scan every non-stdlib\nimport in the gate scripts.\n"""\n')
        code, out = self.check()
        self.assertEqual(code, CLEAN, out)

    def test_an_import_needs_a_pinned_requirements_file(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST + """\
  - name: requests
    ecosystem: pypi
    version: 2.32.3
    first_release: 2024-05-29
    reason: A fixture dependency, present only so the pinning rules have something to bite.
""")
        self.write(".github/scripts/thing.py", "import requests\n")
        self.assertTrips("is missing, so nothing pins")

    def test_requirements_without_hashes_trip(self) -> None:
        self.write(".github/scripts/thing.py", "import requests\n")
        self.write("aios/dependencies.yml", ALLOWLIST + """\
  - name: requests
    ecosystem: pypi
    version: 2.32.3
    first_release: 2024-05-29
    reason: A fixture dependency, present only so the pinning rules have something to bite.
""")
        self.write(".github/scripts/requirements.txt", "requests==2.32.3\n")
        self.assertTrips("pins no hashes")

    def test_requirements_without_an_exact_version_trip(self) -> None:
        self.write(".github/scripts/thing.py", "import requests\n")
        self.write("aios/dependencies.yml", ALLOWLIST + """\
  - name: requests
    ecosystem: pypi
    version: 2.32.3
    first_release: 2024-05-29
    reason: A fixture dependency, present only so the pinning rules have something to bite.
""")
        self.write(".github/scripts/requirements.txt",
                   "requests>=2.32\n    --hash=sha256:" + "a" * 64 + "\n")
        self.assertTrips("not pinned to an exact version")


class TestCargo(DependencyCase):
    def test_an_undeclared_crate_trips(self) -> None:
        self.write("Cargo.toml", "[package]\nname = \"aios\"\n\n[dependencies]\nserde = \"1\"\n")
        self.assertTrips("is not in the allowlist")

    def test_declared_crates_without_a_lockfile_trip(self) -> None:
        self.write("Cargo.toml", "[package]\nname = \"aios\"\n\n[dependencies]\nserde = \"1\"\n")
        self.write("aios/dependencies.yml", ALLOWLIST + """\
  - name: serde
    ecosystem: crates
    version: 1.0.210
    first_release: 2024-09-10
    reason: A fixture dependency, present only so the lockfile rule has something to bite.
""")
        self.assertTrips("no Cargo.lock committed")

    def test_no_dependencies_needs_no_lockfile(self) -> None:
        """This repository's real state: a manifest with an empty dependency table."""
        self.write("Cargo.toml", "[package]\nname = \"aios\"\n\n[dependencies]\n")
        self.assertEqual(self.check()[0], CLEAN)


class TestPlannedControls(DependencyCase):
    def test_a_planned_control_needs_a_task(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST + """\
planned:
  - id: sbom_per_release
    reason: There are no releases yet, and no binary that could be released either.
""")
        self.assertTrips("names no task")

    def test_a_planned_control_needs_a_reason(self) -> None:
        self.write("aios/dependencies.yml", ALLOWLIST + """\
planned:
  - id: sbom_per_release
    pending: M5-03
    reason: later
""")
        self.assertTrips("no reason")


class TestOnlineVerification(unittest.TestCase):
    """Existence checked against the registry, which is the only thing that can prove it."""

    @unittest.skipUnless(network_available(), "pypi.org is not reachable")
    def test_a_nonexistent_package_is_reported_as_hallucinated(self) -> None:
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "aios").mkdir(parents=True)
        (directory / "aios" / "dependencies.yml").write_text(
            "policy:\n  min_age_days: 90\ndependencies:\n"
            "  - name: aios-nonexistent-package-that-nobody-registered\n"
            "    ecosystem: pypi\n    version: 1.0.0\n    first_release: 2020-01-01\n"
            "    reason: A name chosen to not exist, so the existence check has a fixture.\n",
            encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(directory), "--today", TODAY,
             "--online"], capture_output=True, text=True)
        self.assertEqual(result.returncode, VIOLATION, result.stdout + result.stderr)
        self.assertIn("does not exist on PyPI", result.stdout + result.stderr)

    @unittest.skipUnless(network_available(), "pypi.org is not reachable")
    def test_a_nonexistent_version_of_a_real_package_is_reported(self) -> None:
        """The narrower half of the same attack: a real name, a version nobody published."""
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "aios").mkdir(parents=True)
        (directory / "aios" / "dependencies.yml").write_text(
            "policy:\n  min_age_days: 90\ndependencies:\n"
            "  - name: PyYAML\n"
            "    ecosystem: pypi\n    version: 99.99.99\n    first_release: 2011-07-01\n"
            "    reason: A real package pinned to a version that was never published.\n",
            encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(directory), "--today", TODAY,
             "--online"], capture_output=True, text=True)
        self.assertEqual(result.returncode, VIOLATION, result.stdout + result.stderr)
        self.assertIn("does not exist", result.stdout + result.stderr)

    @unittest.skipUnless(network_available(), "pypi.org is not reachable")
    def test_age_is_measured_from_the_name_not_the_pinned_version(self) -> None:
        """The distinction the control turns on, and the one this milestone got wrong first.

        The attack is a freshly registered name, so the age that matters belongs to the name.
        Measuring the pinned version's upload date instead would fail every current release of
        every package — which is how the first version of this read, and it would have banned
        an action whose major-version tag is moved on every release.
        """
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "aios").mkdir(parents=True)
        (directory / "aios" / "dependencies.yml").write_text(
            "policy:\n  min_age_days: 90\ndependencies:\n"
            "  - name: PyYAML\n"
            "    ecosystem: pypi\n    version: 6.0.3\n    first_release: 2011-07-01\n"
            "    reason: Fifteen years old by name; the pinned release is far more recent.\n",
            encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(directory), "--today", TODAY,
             "--online"], capture_output=True, text=True)
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, CLEAN, output)
        self.assertNotIn("too new", output)


class TestKnownVulnerabilities(unittest.TestCase):
    """The CVE half, which M3-05 deferred to here.

    GitHub's advisory database rather than OSV: it is the forge this repository already
    depends on (ADR-002) so adds no new trusted party, and api.osv.dev is filtered on the
    network this was written on, with the same connection-reset signature as the Rust hosts.
    A source that cannot be reached from the machine writing the check cannot be verified even
    once, and an unverifiable source is not a source.
    """

    def audit(self, text: str):
        directory = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, directory, True)
        (directory / "aios").mkdir(parents=True)
        (directory / "aios" / "dependencies.yml").write_text(text, encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(directory), "--today", TODAY,
             "--online"], capture_output=True, text=True)

    @unittest.skipUnless(network_available(), "pypi.org is not reachable")
    def test_a_package_with_a_critical_advisory_is_reported(self) -> None:
        """PyYAML 5.3.1 carries GHSA-8q59-q68h-6hv4, arbitrary code execution via full_load."""
        result = self.audit(
            "policy:\n  min_age_days: 90\n  block_severities: [critical, high]\n"
            "dependencies:\n  - name: PyYAML\n    ecosystem: pypi\n    version: 5.3.1\n"
            "    first_release: 2011-07-01\n"
            "    reason: A version with a real published advisory, as a fixture.\n")
        output = result.stdout + result.stderr
        self.assertEqual(result.returncode, VIOLATION, output)
        self.assertIn("GHSA-8q59-q68h-6hv4", output)
        self.assertIn("critical", output)

    @unittest.skipUnless(network_available(), "pypi.org is not reachable")
    def test_the_pinned_version_is_clean(self) -> None:
        result = self.audit(
            "policy:\n  min_age_days: 90\n  block_severities: [critical, high]\n"
            "dependencies:\n  - name: PyYAML\n    ecosystem: pypi\n    version: 6.0.3\n"
            "    first_release: 2011-07-01\n"
            "    reason: The version this repository actually pins.\n")
        self.assertEqual(result.returncode, CLEAN, result.stdout + result.stderr)

    @unittest.skipUnless(network_available(), "pypi.org is not reachable")
    def test_an_empty_severity_list_reports_nothing(self) -> None:
        """A list that flags everything gets ignored, so the threshold has to be a choice."""
        result = self.audit(
            "policy:\n  min_age_days: 90\n  block_severities: []\n"
            "dependencies:\n  - name: PyYAML\n    ecosystem: pypi\n    version: 5.3.1\n"
            "    first_release: 2011-07-01\n"
            "    reason: The same vulnerable version, with nothing declared blocking.\n")
        self.assertEqual(result.returncode, CLEAN, result.stdout + result.stderr)

    def test_the_configured_severities_are_high_and_critical(self) -> None:
        import yaml

        document = yaml.safe_load(
            (ROOT / "aios" / "dependencies.yml").read_text(encoding="utf-8"))
        self.assertEqual(sorted(document["policy"]["block_severities"]),
                         ["critical", "high"])


class TestThisRepository(unittest.TestCase):
    def test_this_repository_has_a_clean_supply_chain(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--root", str(ROOT)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, CLEAN, result.stdout + result.stderr)

    def test_no_workflow_uses_a_mutable_tag(self) -> None:
        """Stated separately because it is the finding this milestone actually produced.

        All five workflows ran actions/checkout@v4 until now.
        """
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if "uses:" in line and "@" in line:
                    reference = line.split("uses:")[1].split("#")[0].strip().split("@")[1]
                    with self.subTest(workflow=path.name):
                        self.assertRegex(reference, r"^[0-9a-f]{40}$",
                                         f"{path.name} uses a mutable reference")


if __name__ == "__main__":
    unittest.main(verbosity=2)
