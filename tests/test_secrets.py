#!/usr/bin/env python3
"""Tests for the secrets scan.

Run: python3 -m unittest discover -s tests -v

Every planted credential here is assembled at runtime from fragments — `J("AKIA", "...")`
rather than the literal string. That is not decoration. A test file containing a
credential-shaped literal would be found by the scanner when it scans this repository, so the
suite would fail the gate it exists to prove. Building the strings at runtime means no
committed file ever contains one, which removes the need for an exclusion directory and the
blind spot that comes with it.

The paired structure matters as much as in the test-integrity audit, and for a sharper
reason: this gate is Contract at *every* tier and has no waiver comment by design. A false
positive is therefore an unmergeable pull request with no escape hatch at all, so every
detection test has a counterpart proving the obvious placeholder form stays silent.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "scan-secrets.py"

CLEAN, FOUND, CANNOT_RUN = 0, 1, 2


def J(*parts: str) -> str:
    """Assemble a credential-shaped string so no literal one is committed."""
    return "".join(parts)


# name -> (a string that must be caught, a placeholder form that must not be)
CREDENTIALS: dict[str, tuple[str, str | None]] = {
    "aws-access-key-id": (J("AKIA", "J7XQ2M5RVBN4KP9Z"), J("AKIA", "IOSFODNN7EXAMPLE")),
    "github-token": (J("ghp_", "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0hJ3kL6"),
                     J("ghp_", "EXAMPLEdE6gH9jK2mN5pQ8sT1vW4yZ7cF0hJ3")),
    "github-fine-grained-pat": (
        J("github_pat_", "11ABCDEFG0", "aBcDeFgHiJkLmNoPqRsTuVwXyZ0123456789abcdefghijklmnop"),
        None),
    "slack-token": (J("xox", "b-2451234567-1234567890123-abcdefghijklmnop"),
                    J("xox", "b-0000000000-EXAMPLE00000-abcdefghijklmnop")),
    "stripe-secret-key": (J("sk_", "live_", "4eC39HqLyjWDarjtT1zdp7dc"),
                          J("sk_", "live_", "EXAMPLE9HqLyjWDarjtT1zdp7")),
    "google-api-key": (J("AIza", "SyD3kL9mN2pQ5rT8vW1xY4zA7bC0dE6fG9h"),
                       J("AIza", "SyEXAMPLE2pQ5rT8vW1xY4zA7bC0dE6fG9h")),
    "openai-key": (J("sk-", "proj-", "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0hJ"), None),
    "npm-token": (J("npm_", "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0hJ3kL6"), None),
    "sendgrid-key": (J("SG.", "aB3dE6gH9jK2mN5pQ8sT1v", ".",
                       "W4yZ7cF0hJ3kL6mN9pQ2sT5vW8yZ1cF4hJ7kL0mN3pQ"), None),
    "twilio-key": (J("SK", "0123456789abcdef0123456789abcdef"), None),
    "private-key-block": (J("-----BEGIN ", "RSA PRIVATE KEY", "-----"), None),
    "json-web-token": (J("eyJ", "hbGciOiJIUzI1NiJ9", ".", "eyJ", "zdWIiOiIxMjM0NTY3ODkwIn0",
                         ".", "dBjftJeZ4CVPmB92K27uhbUJU1p1r_wW1gFWFOEjXk"), None),
    "azure-storage-key": (
        J("AccountKey=", "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7cF0hJ3kL6mN9pQ2sT5vW8yZ1cF4hJ7kL0mN3p"),
        None),
    "basic-auth-in-url": (
        J("https://", "deploy:", "s3cr3tP4ssw0rdV4lue", "@", "registry.acme-corp.net"),
        None),
}


class SecretsCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.git("init", "-q")

    def git(self, *args: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(self.dir), "-c", "user.name=t", "-c", "user.email=t@e",
             "-c", "commit.gpgsign=false", *args],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def write(self, name: str, content: str) -> None:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def scan(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.dir), *args],
            capture_output=True, text=True)
        return result.returncode, result.stdout + result.stderr


class TestCredentialFormats(SecretsCase):
    """Generated per credential format below."""


def _detect_case(name: str, secret: str):
    def test(self: SecretsCase) -> None:
        self.write("config.env", f"CREDENTIAL={secret}\n")
        self.commit("add config")
        code, out = self.scan()
        self.assertEqual(code, FOUND, f"{name} was not detected\n{out}")
        self.assertIn(f"[{name}]", out, out)
    return test


def _placeholder_case(name: str, placeholder: str):
    def test(self: SecretsCase) -> None:
        self.write("README.md", f"Set CREDENTIAL={placeholder}\n")
        self.commit("document config")
        code, out = self.scan()
        self.assertEqual(code, CLEAN, f"{name} placeholder was flagged\n{out}")
    return test


for _name, (_secret, _placeholder) in CREDENTIALS.items():
    _slug = _name.replace("-", "_")
    _d = _detect_case(_name, _secret)
    _d.__doc__ = f"{_name}: a real one is caught"
    setattr(TestCredentialFormats, f"test_{_slug}_is_detected", _d)
    if _placeholder is not None:
        _p = _placeholder_case(_name, _placeholder)
        _p.__doc__ = f"{_name}: the documentation placeholder is not"
        setattr(TestCredentialFormats, f"test_{_slug}_placeholder_is_ignored", _p)


class TestHistory(SecretsCase):
    def test_a_secret_committed_then_removed_is_still_found(self) -> None:
        """The half of M2-07 that matters: deleting a secret does not un-leak it."""
        self.write("deploy.sh", f"export AWS_KEY={CREDENTIALS['aws-access-key-id'][0]}\n")
        self.commit("add deploy script")
        (self.dir / "deploy.sh").unlink()
        self.commit("remove the secret")

        tree_code, tree_out = self.scan()
        self.assertEqual(tree_code, CLEAN,
                         f"the working tree should be clean after removal\n{tree_out}")

        code, out = self.scan("--history")
        self.assertEqual(code, FOUND, f"history scan missed the removed secret\n{out}")
        self.assertIn("[aws-access-key-id]", out)

    def test_a_secret_overwritten_in_place_is_still_found(self) -> None:
        self.write("deploy.sh", f"export AWS_KEY={CREDENTIALS['aws-access-key-id'][0]}\n")
        self.commit("add deploy script")
        self.write("deploy.sh", "export AWS_KEY=${AWS_KEY}\n")
        self.commit("read the key from the environment instead")

        self.assertEqual(self.scan()[0], CLEAN)
        self.assertEqual(self.scan("--history")[0], FOUND)

    def test_clean_history_passes(self) -> None:
        self.write("deploy.sh", "export AWS_KEY=${AWS_KEY}\n")
        self.commit("read the key from the environment")
        code, out = self.scan("--history")
        self.assertEqual(code, CLEAN, out)

    def test_a_repository_with_no_commits_is_clean_not_an_error(self) -> None:
        code, out = self.scan("--history")
        self.assertEqual(code, CLEAN, out)

    def test_all_scans_both(self) -> None:
        self.write("deploy.sh", f"export AWS_KEY={CREDENTIALS['aws-access-key-id'][0]}\n")
        self.commit("add deploy script")
        (self.dir / "deploy.sh").unlink()
        self.commit("remove the secret")
        code, out = self.scan("--all")
        self.assertEqual(code, FOUND, out)


class TestGenericDetection(SecretsCase):
    def test_high_entropy_assignment_is_caught(self) -> None:
        self.write("settings.py", 'API_KEY = "' + J("h7Kd", "9wQz2XmR4tYb", "8vNc1LpA6sEg") + '"\n')
        self.commit("settings")
        code, out = self.scan()
        self.assertEqual(code, FOUND, out)
        self.assertIn("[high-entropy-assignment]", out)

    def test_low_entropy_assignment_is_not_caught(self) -> None:
        self.write("settings.py", 'API_KEY = "aaaaaaaaaaaaaaaaaaaaaaaa"\n')
        self.commit("settings")
        code, out = self.scan()
        self.assertEqual(code, CLEAN, out)

    def test_environment_indirection_is_not_caught(self) -> None:
        self.write("settings.py", 'API_KEY = os.environ["SERVICE_API_KEY_NAME"]\n')
        self.commit("settings")
        self.assertEqual(self.scan()[0], CLEAN)

    def test_a_named_placeholder_is_not_caught(self) -> None:
        self.write("README.md", 'password: <your-password-goes-here>\n')
        self.commit("docs")
        self.assertEqual(self.scan()[0], CLEAN)

    def test_credentials_on_a_documentation_host_are_treated_as_documentation(self) -> None:
        """`user:pass@example.com` in a README is an illustration, not a leak.

        Found by a fixture that meant to plant a real one and used example.com out of habit.
        The suppression is right; what it needed was the counterpart test above, on a host
        that is not reserved for documentation.
        """
        self.write("README.md", J("https://", "deploy:", "s3cr3tP4ssw0rdV4lue", "@",
                                  "example.com") + "\n")
        self.commit("docs")
        self.assertEqual(self.scan()[0], CLEAN)

    def test_lockfile_integrity_hashes_do_not_false_positive(self) -> None:
        """High entropy, but the generic rule keys on the variable name, not entropy alone."""
        self.write("package-lock.json",
                   '"integrity": "sha512-' + J("h7Kd9wQz2XmR", "4tYb8vNc1LpA6sEg") + '"\n')
        self.write("Cargo.lock", 'checksum = "' + J("a3f8c21d", "9e4b7061f5") + '"\n')
        self.commit("lockfiles")
        self.assertEqual(self.scan()[0], CLEAN)

    def test_a_real_credential_in_a_lockfile_is_still_caught(self) -> None:
        """Lockfiles were skipped wholesale until a surviving mutation showed the cost.

        A private-registry URL carrying a token is one of the commoner ways a credential
        reaches a repository, and skipping the file it lives in would have hidden it.
        """
        self.write("package-lock.json",
                   '"resolved": "https://x-access-token:'
                   + CREDENTIALS["github-token"][0] + '@github.com/org/repo.git"\n')
        self.commit("lockfile with a token")
        code, out = self.scan()
        self.assertEqual(code, FOUND, out)
        self.assertIn("[github-token]", out)


class TestOutput(SecretsCase):
    def test_the_secret_is_never_printed_in_full(self) -> None:
        """CI logs are widely readable and often retained longer than the branch."""
        secret = CREDENTIALS["aws-access-key-id"][0]
        self.write("config.env", f"CREDENTIAL={secret}\n")
        self.commit("add config")
        code, out = self.scan()
        self.assertEqual(code, FOUND)
        self.assertNotIn(secret, out)
        self.assertIn(secret[:4], out)

    def test_the_message_says_to_rotate(self) -> None:
        self.write("config.env", f"CREDENTIAL={CREDENTIALS['aws-access-key-id'][0]}\n")
        self.commit("add config")
        _, out = self.scan()
        self.assertIn("Rotate", out)

    def test_a_missing_repository_cannot_run(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.dir / "nope")],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, CANNOT_RUN, result.stdout + result.stderr)


class TestThisRepository(unittest.TestCase):
    def test_the_repository_itself_is_clean(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(ROOT)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, CLEAN, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
