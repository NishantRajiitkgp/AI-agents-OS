#!/usr/bin/env python3
"""Conformance checks for the cross-ecosystem invocation contract (ADR-013).

Run: python -m unittest discover -s tests -v

Q-002 requires the contract to be written down before the test, so the test can fail it.
These checks are written against ADR-013 and not against any implementation — nothing here
imports the binary's source, and every check runs an executable as a subprocess the way a
host project in another ecosystem would.

That raises the obvious question: how do you trust a conformance suite whose subject does not
exist yet? By running it against stand-ins that violate the contract on purpose. Each check
below is exercised against a conforming stand-in and at least one that breaks exactly the
clause under test. A check that cannot fail is not a check, and a suite written for an absent
subject is the easiest place in this repository to accidentally write one.

The stand-ins are Python. That is not a claim about the implementation language — the contract
is deliberately about observable behaviour at the process boundary, which is what makes it a
cross-ecosystem contract at all. A stand-in that had to be Rust would be testing ADR-005
rather than ADR-013.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ADR = ROOT / "docs" / "decisions" / "ADR-013-the-cross-ecosystem-invocation-contract.md"

PASSED, FAILED, COULD_NOT_RUN = 0, 1, 2
RESERVED = range(3, 126)

# A stand-in that honours ADR-013. Written once and mutated per test, so that a test showing a
# violation is showing exactly one difference from a conforming subject.
CONFORMING = '''\
import json, os, sys
from pathlib import Path

STATES = {"todo", "doing", "review", "done", "waiting", "dropped"}

def find_root(argv):
    if "--root" in argv:
        return Path(argv[argv.index("--root") + 1])
    if os.environ.get("AIOS_ROOT"):
        return Path(os.environ["AIOS_ROOT"])
    for candidate in [Path.cwd(), *Path.cwd().parents]:
        if (candidate / ".git").exists():
            return candidate
    return None

argv = sys.argv[1:]
if "--version" in argv:
    print("aios 0.1.0")
    sys.exit(0)

root = find_root(argv)
if root is None:
    print("could not run: no repository root above the working directory", file=sys.stderr)
    sys.exit(2)

config = Path(os.environ.get("AIOS_CONFIG") or (root / "aios" / "config.yml"))
if "--config" in argv:
    config = Path(argv[argv.index("--config") + 1])
if not config.is_file():
    print(f"could not run: no config at {config}", file=sys.stderr)
    sys.exit(2)

findings = []
for task in sorted((root / "aios" / "tasks").glob("*.md")):
    for line in task.read_text(encoding="utf-8").splitlines():
        if line.startswith("status:") and line.split(":", 1)[1].strip() not in STATES:
            findings.append(f"{task.name}: status {line.split(':', 1)[1].strip()}")

verdict = "fail" if findings else "pass"
print(f"aios validate: reading {root}", file=sys.stderr)
if "--format" in argv and argv[argv.index("--format") + 1] == "json":
    print(json.dumps({"verdict": verdict, "root": str(root), "findings": findings}))
else:
    print(f"{verdict}: {root}")
sys.exit(1 if verdict == "fail" else 0)
'''


class ContractCase(unittest.TestCase):
    """A scratch host project, plus a stand-in executable to point at it.

    `SUBJECT_SOURCE` is a class attribute so the whole conformance suite can be re-run against
    a deliberately broken subject. That is what `TestTheChecksCanFail` does, and it is the
    only evidence that these checks check anything.
    """

    SUBJECT_SOURCE = CONFORMING

    #: The subcommand a host project calls, prepended to every invocation below.
    #:
    #: These checks invoked the executable bare until the first release build met them, on the
    #: reading that a tool whose job is checking should check when told nothing else. The
    #: binary reads being told nothing as a usage error instead, and argues it in a comment: a
    #: tool that exits zero when told nothing teaches a script that calling it wrong is fine.
    #: Both readings are defensible, so the disagreement was settled by giving the caller
    #: something explicit to call rather than by making silence mean something.
    COMMAND = ("validate",)

    #: Set by CI once a binary exists, so the same checks run against the real subject.
    #: Ignored by TestTheChecksCanFail, which must keep using stand-ins to stay meaningful.
    REAL = os.environ.get("AIOS_BINARY")

    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.project = self.dir / "host-project"
        (self.project / "aios" / "tasks").mkdir(parents=True)
        (self.project / ".git").mkdir()
        (self.project / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        (self.project / "src").mkdir()
        self.subject = self.write_subject(self.SUBJECT_SOURCE)

    def break_the_state(self) -> None:
        """Give the project a finding a real subject can actually have.

        This was an empty file named `BROKEN` at the root, which is a convention only a
        stand-in could honour — no implementation would ever look for it, so the clause "a
        failing check exits 1" could not be satisfied by the thing the clause is about. A
        status outside the state machine is the substitute: it is defined by the template
        rather than by any implementation, every subject has to recognise it to be capable of
        failing at all, and it is what the build asserts the binary already refuses.
        """
        (self.project / "aios" / "tasks" / "T-0001.md").write_text(
            "---\nid: T-0001\nstatus: nonsense\n---\n", encoding="utf-8")

    def write_subject(self, source: str, name: str = "aios-standin.py") -> Path:
        if self.REAL and source is self.SUBJECT_SOURCE:
            return Path(self.REAL)
        path = self.dir / name
        path.write_text(source, encoding="utf-8")
        return path

    def invoke(self, *args: str, cwd: Path | None = None,
               env: dict[str, str] | None = None,
               subject: Path | None = None) -> subprocess.CompletedProcess:
        environment = {**os.environ, **(env or {})}
        target = subject or self.subject
        # A stand-in is a script and needs an interpreter; the real subject is an executable
        # and must not be given one. Nothing else in the suite knows which it is looking at,
        # which is the property that lets the same checks judge both.
        command = ([str(target)] if self.REAL and target == self.subject
                   else [sys.executable, str(target)])
        return subprocess.run(
            [*command, *self.COMMAND, *args], cwd=str(cwd or self.project),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            env=environment)


class TestExitCodes(ContractCase):
    """ADR-013 §2. The 1-versus-2 distinction is the clause with teeth."""

    def test_a_passing_check_exits_zero(self) -> None:
        self.assertEqual(self.invoke().returncode, PASSED)

    def test_a_failing_check_exits_one(self) -> None:
        self.break_the_state()
        self.assertEqual(self.invoke().returncode, FAILED)

    def test_a_check_that_cannot_run_exits_two(self) -> None:
        (self.project / "aios" / "config.yml").unlink()
        self.assertEqual(self.invoke().returncode, COULD_NOT_RUN)

    def test_could_not_run_is_distinguishable_from_both(self) -> None:
        """The failure Q-002 names: could-not-run silently read as pass."""
        (self.project / "aios" / "config.yml").unlink()
        cannot = self.invoke().returncode
        (self.project / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        passes = self.invoke().returncode
        self.break_the_state()
        fails = self.invoke().returncode
        self.assertEqual(len({cannot, passes, fails}), 3,
                         "pass, fail and could-not-run must be three distinct codes")

    def test_the_reserved_range_is_not_used(self) -> None:
        for scenario in ([], ["--format", "json"]):
            with self.subTest(scenario=scenario):
                self.assertNotIn(self.invoke(*scenario).returncode, RESERVED)


class TestOutput(ContractCase):
    """ADR-013 §3. Human by default, machine behind a flag, streams split by role."""

    def test_the_default_is_human_readable(self) -> None:
        result = self.invoke()
        self.assertIn("pass", result.stdout)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(result.stdout)

    def test_format_json_puts_a_single_document_on_stdout(self) -> None:
        result = self.invoke("--format", "json")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["verdict"], "pass")

    def test_diagnostics_do_not_contaminate_the_machine_readable_stdout(self) -> None:
        """A host capturing stdout must get the verdict and nothing else.

        Asserted as "stdout parses and stderr is not silent" rather than by looking for a
        particular diagnostic. The stand-in printed the literal `working...`, and requiring
        that of the subject would have made the clause a check on one implementation's
        wording — which a real binary fails while conforming perfectly.
        """
        result = self.invoke("--format", "json")
        self.assertNotEqual(result.stderr.strip(), "",
                            "a subject that says nothing cannot show where it says it")
        self.assertEqual(json.loads(result.stdout)["verdict"], "pass")

    def test_diagnostics_are_on_stderr_in_human_mode_too(self) -> None:
        result = self.invoke()
        self.assertNotEqual(result.stderr.strip(), "")


class TestRootDiscovery(ContractCase):
    """ADR-013 §4. Upward from the working directory, refused rather than guessed."""

    def test_it_works_from_the_repository_root(self) -> None:
        self.assertEqual(self.invoke().returncode, PASSED)

    def test_it_works_from_a_subdirectory(self) -> None:
        deep = self.project / "src" / "deep" / "deeper"
        deep.mkdir(parents=True)
        result = self.invoke("--format", "json", cwd=deep)
        self.assertEqual(result.returncode, PASSED)
        self.assertEqual(Path(json.loads(result.stdout)["root"]), self.project)

    def test_it_refuses_outside_a_repository_rather_than_guessing(self) -> None:
        """The decoy carries a valid config, so only root discovery separates the outcomes.

        Without it a subject that treats the working directory as the root still exits 2 —
        because it then fails to find a config there — and passes this check by accident.
        """
        outside = self.dir / "not-a-repo"
        (outside / "aios").mkdir(parents=True)
        (outside / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        result = self.invoke(cwd=outside)
        self.assertEqual(result.returncode, COULD_NOT_RUN,
                         "a directory with a config but no repository root is not a root")
        self.assertIn("could not run", result.stderr)

    def test_the_root_flag_overrides_discovery(self) -> None:
        outside = self.dir / "not-a-repo"
        outside.mkdir()
        result = self.invoke("--root", str(self.project), "--format", "json", cwd=outside)
        self.assertEqual(result.returncode, PASSED)

    def test_the_environment_variable_overrides_discovery(self) -> None:
        outside = self.dir / "not-a-repo"
        outside.mkdir()
        result = self.invoke(cwd=outside, env={"AIOS_ROOT": str(self.project)})
        self.assertEqual(result.returncode, PASSED)

    def test_the_flag_beats_the_environment_variable(self) -> None:
        other = self.dir / "other-project"
        (other / "aios").mkdir(parents=True)
        (other / ".git").mkdir()
        (other / "aios" / "config.yml").write_text("tier: internal\n", encoding="utf-8")
        result = self.invoke("--root", str(self.project), "--format", "json",
                             env={"AIOS_ROOT": str(other)})
        self.assertEqual(Path(json.loads(result.stdout)["root"]), self.project)

    def test_config_is_read_from_the_fixed_path_under_the_root(self) -> None:
        moved = self.project / "aios" / "config.yml"
        moved.rename(self.project / "aios" / "elsewhere.yml")
        self.assertEqual(self.invoke().returncode, COULD_NOT_RUN)

    def test_the_config_override_is_honoured(self) -> None:
        elsewhere = self.dir / "custom.yml"
        elsewhere.write_text("tier: prototype\n", encoding="utf-8")
        (self.project / "aios" / "config.yml").unlink()
        self.assertEqual(self.invoke("--config", str(elsewhere)).returncode, PASSED)
        self.assertEqual(self.invoke(env={"AIOS_CONFIG": str(elsewhere)}).returncode, PASSED)


class TestTheHostProjectIsInAnotherEcosystem(ContractCase):
    """The point of the contract: called from a project that knows nothing about the OS.

    This exercises the call the way a host task runner makes it — a path, arguments, an exit
    code read as a number. It does not prove ADR-005's runtime-free claim, which needs the
    real binary; it proves the shape of the call does not require the host to know anything
    about the implementation.
    """

    def test_a_host_reads_the_verdict_without_parsing_prose(self) -> None:
        (self.project / "package.json").write_text(
            json.dumps({"name": "host", "scripts": {"check": "aios check"}}), encoding="utf-8")
        result = self.invoke("--format", "json")
        self.assertEqual(result.returncode, PASSED)
        self.assertEqual(json.loads(result.stdout)["verdict"], "pass")

    def test_a_host_that_maps_non_zero_to_failure_is_safe(self) -> None:
        """One of the two safe mappings §2 promises. Both must hold for every outcome."""
        for setup, expected_non_zero in (
            (lambda: None, False),
            (self.break_the_state, True),
            (lambda: (self.project / "aios" / "config.yml").unlink(), True),
        ):
            with self.subTest(expected_non_zero=expected_non_zero):
                self.setUp()
                setup()
                self.assertEqual(self.invoke().returncode != 0, expected_non_zero)


CONFORMANCE = (TestExitCodes, TestOutput, TestRootDiscovery,
               TestTheHostProjectIsInAnotherEcosystem)

# Each entry breaks exactly one clause of ADR-013, and names the class that must reject it.
# A suite written against an absent subject is the easiest place in this repository to write a
# check that cannot fail, and asserting the broken stand-in misbehaves would not show that;
# only re-running the real checks against it does.
#
# Naming the class rather than running all four is the stronger assertion as well as the
# cheaper one: it says the clause is covered by the checks that claim to cover it, rather than
# by something incidental elsewhere in the suite.
VIOLATIONS = {
    # Anchored on the config branch rather than on the first `sys.exit(2)` in the file. The
    # first one is the root-discovery refusal, and mutating it tests §4 while claiming to test
    # §2 — which is how a clause ends up covered only by something incidental elsewhere.
    "§2 conflates could-not-run with failure":
        ('no config at {config}", file=sys.stderr)\n    sys.exit(2)',
         'no config at {config}", file=sys.stderr)\n    sys.exit(1)', TestExitCodes),
    "§2 exits zero on a genuine failure":
        ('sys.exit(1 if verdict == "fail" else 0)', "sys.exit(0)", TestExitCodes),
    "§2 uses a reserved exit code":
        ('no config at {config}", file=sys.stderr)\n    sys.exit(2)',
         'no config at {config}", file=sys.stderr)\n    sys.exit(7)', TestExitCodes),
    "§3 prints diagnostics to stdout":
        ('print(f"aios validate: reading {root}", file=sys.stderr)',
         'print(f"aios validate: reading {root}")', TestOutput),
    "§3 has no machine-readable mode":
        ('if "--format" in argv and argv[argv.index("--format") + 1] == "json":',
         "if False:", TestOutput),
    "§3 makes json the default":
        ('print(f"{verdict}: {root}")',
         'print(json.dumps({"verdict": verdict}))', TestOutput),
    "§4 assumes the working directory is the root":
        ("    return None", "    return Path.cwd()", TestRootDiscovery),
    "§4 does not walk upward from a subdirectory":
        ("for candidate in [Path.cwd(), *Path.cwd().parents]:",
         "for candidate in [Path.cwd()]:", TestRootDiscovery),
    "§4 ignores the --root flag":
        ('if "--root" in argv:', "if False:", TestRootDiscovery),
    "§4 ignores AIOS_ROOT":
        ('if os.environ.get("AIOS_ROOT"):', "if False:", TestRootDiscovery),
    "§4 lets the environment beat the flag":
        ('    if "--root" in argv:\n        return Path(argv[argv.index("--root") + 1])\n',
         "", TestRootDiscovery),
    "§4 reads config from anywhere it can find one":
        ("if not config.is_file():", "if False:", TestRootDiscovery),
}


class TestTheChecksCanFail(unittest.TestCase):
    """Run the conformance suite against subjects that break the contract on purpose."""

    def run_suite_against(self, source: str,
                          cases: tuple[type, ...] = CONFORMANCE) -> unittest.TestResult:
        suite = unittest.TestSuite()
        for case in cases:
            # REAL is cleared deliberately: these subclasses must judge the stand-in they were
            # given, not whatever binary CI happens to have pointed the suite at.
            broken = type(f"Broken{case.__name__}", (case,),
                          {"SUBJECT_SOURCE": source, "REAL": None})
            suite.addTests(unittest.TestLoader().loadTestsFromTestCase(broken))
        with open(os.devnull, "w") as sink:
            return unittest.TextTestRunner(stream=sink, verbosity=0).run(suite)

    def test_the_conforming_subject_passes_every_check(self) -> None:
        """The control. Without it, a suite that fails everything would look rigorous."""
        result = self.run_suite_against(CONFORMING)
        self.assertEqual((len(result.failures), len(result.errors)), (0, 0),
                         f"{result.failures}{result.errors}")

    def test_every_violation_is_rejected_by_the_checks_that_claim_to_cover_it(self) -> None:
        for label, (old, new, case) in VIOLATIONS.items():
            with self.subTest(violation=label):
                self.assertIn(old, CONFORMING,
                              "the anchor no longer appears; this mutation tests nothing")
                result = self.run_suite_against(CONFORMING.replace(old, new, 1), (case,))
                self.assertGreater(
                    len(result.failures) + len(result.errors), 0,
                    f"{case.__name__} accepted a subject that {label}")


class TestTheHostProjectHarness(unittest.TestCase):
    """The cross-ecosystem side: a Node project calling the tool with no shared runtime.

    Node is a prerequisite of this suite rather than an optional extra. The alternative was a
    skip, and a skip is invisible in a green run — which for the one check that proves the
    OS imposes no runtime is the worst place in the repository to put something forgettable.
    """

    HOST = ROOT / "tests" / "host-project" / "check.mjs"

    def setUp(self) -> None:
        self.node = shutil.which("node")
        self.assertIsNotNone(
            self.node,
            "node is required: it is the ecosystem the cross-ecosystem proof is run from")
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def executable_standin(self, source: str) -> Path:
        """A stand-in the host can spawn as an executable, not as a script with an interpreter.

        The point of the harness is that the caller does not know what it is calling, so it
        must be handed something it can run directly.
        """
        script = self.dir / "standin.py"
        script.write_text(source, encoding="utf-8")
        if os.name == "nt":
            launcher = self.dir / "aios.cmd"
            launcher.write_text(f'@echo off\r\n"{sys.executable}" "{script}" %*\r\n',
                                encoding="ascii")
        else:
            launcher = self.dir / "aios"
            launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{script}" "$@"\n',
                                encoding="utf-8")
            launcher.chmod(0o755)
        return launcher

    def run_host(self, source: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.node, str(self.HOST), str(self.executable_standin(source))],
            capture_output=True, text=True, encoding="utf-8", errors="replace")

    def test_it_holds_against_a_conforming_subject(self) -> None:
        result = self.run_host(CONFORMING)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("held.", result.stdout)
        self.assertNotIn("FAIL", result.stdout)

    def test_it_reports_every_violation(self) -> None:
        """Same violations as the Python suite. A second implementation that agrees is
        evidence; one that passes everything is a second thing to fix."""
        for label, (old, new, _) in VIOLATIONS.items():
            with self.subTest(violation=label):
                result = self.run_host(CONFORMING.replace(old, new, 1))
                self.assertEqual(result.returncode, 1,
                                 f"the host accepted a subject that {label}\n{result.stdout}")

    def test_it_refuses_rather_than_reporting_a_subject_it_could_not_call(self) -> None:
        result = subprocess.run(
            [self.node, str(self.HOST), str(self.dir / "does-not-exist")],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("could not run", result.stderr)

    def test_the_host_project_has_no_dependencies(self) -> None:
        """A proof that the OS imposes no runtime must not pull in a dependency tree."""
        manifest = json.loads(
            (ROOT / "tests" / "host-project" / "package.json").read_text(encoding="utf-8"))
        self.assertNotIn("dependencies", manifest)
        self.assertNotIn("devDependencies", manifest)
        self.assertFalse((ROOT / "tests" / "host-project" / "node_modules").exists())


class TestTheProofThatIsStillOwed(unittest.TestCase):
    """A tripwire, not a placeholder.

    The end-to-end proof Q-002 demands needs a real binary, and M1-08 is held because the Rust
    toolchain is unreachable from this network. The honest options were a skipped test or
    nothing, and both are forgettable — a skip is invisible in a green run, and the
    test-integrity audit would flag one anyway.

    So this asserts the *blocked* state instead. The moment a built executable appears, this
    test fails and says what is now owed. It cannot be satisfied by waiting.
    """

    def candidates(self) -> list[Path]:
        binaries = ROOT / "aios" / "bin"
        return [path for path in (binaries / "aios", binaries / "aios.exe",
                                  ROOT / "target" / "release" / "aios",
                                  ROOT / "target" / "release" / "aios.exe")
                if path.is_file()]

    def test_when_a_binary_exists_the_conformance_run_is_owed(self) -> None:
        found = self.candidates()
        self.assertEqual(
            found, [],
            f"An executable now exists at {found}. The contract checks above have only ever "
            f"run against stand-ins. Point them at this one and run the cross-ecosystem proof "
            f"M3-11 asks for, then delete this test.")

    def test_the_contract_is_written_down(self) -> None:
        """Q-002 requires the contract to precede the test rather than describe it."""
        self.assertTrue(ADR.is_file())
        text = ADR.read_text(encoding="utf-8")
        for clause in ("Naming and discovery", "Exit codes", "Output", "Repository root"):
            self.assertIn(clause, text)

    def test_the_binary_uses_the_contract_codes(self) -> None:
        """§2 codifies measured practice; if the source drifts, it stops being measured.

        Searched across the crate rather than in main.rs, because the constants moved to the
        module that uses them when the subcommands were implemented. Pinning the assertion to
        one file would make it fail on a refactor that changed nothing about the contract,
        which is how a test earns the reputation that gets it deleted.
        """
        source = "\n".join(
            path.read_text(encoding="utf-8") for path in sorted((ROOT / "src").rglob("*.rs")))
        self.assertIn("const OK: u8 = 0;", source)
        self.assertIn("const FAILED: u8 = 1;", source)
        self.assertIn("const COULD_NOT_RUN: u8 = 2;", source)

    def test_every_subcommand_returns_through_the_contract(self) -> None:
        """No subcommand may reach `std::process::exit` and bypass the code mapping.

        The whole value of the 1-versus-2 distinction is that it holds everywhere. One early
        exit in one error path is enough to make a caller's `if code == 2` wrong, and that
        caller is a shell script in another ecosystem that nobody here will ever see fail.
        """
        for path in sorted((ROOT / "src").rglob("*.rs")):
            with self.subTest(file=path.name):
                self.assertNotIn("process::exit", path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
