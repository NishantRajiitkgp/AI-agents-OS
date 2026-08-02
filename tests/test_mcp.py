#!/usr/bin/env python3
"""Tests for the MCP allowlist and drift check (M4-08, 07 §1.3, 03 §3.4).

Run: python -m unittest discover -s tests -v

This repository configures no MCP servers, so the check passes here by having nothing to
object to. That is the weakest possible evidence that it works, and the reason nearly every
test below builds a fixture tree with servers in it: a check whose only exercise is the empty
case is indistinguishable from a check that always passes.
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

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "check-mcp.py"

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2


class McpCase(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        (self.dir / "aios").mkdir()
        (self.dir / ".cursor").mkdir()

    def config(self, servers: list[str]) -> None:
        listed = "\n".join(f'  - "{entry}"' for entry in servers) or "  []"
        body = "tier: prototype\nmcp_servers:\n" + (listed if servers else "")
        if not servers:
            body = "tier: prototype\nmcp_servers: []\n"
        (self.dir / "aios" / "config.yml").write_text(body + "\n", encoding="utf-8")

    def tool_config(self, name: str, servers: dict) -> None:
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mcpServers": servers}, indent=2), encoding="utf-8")

    def run_check(self) -> tuple[int, str]:
        result = subprocess.run([sys.executable, str(SCRIPT), "--dir", str(self.dir)],
                                capture_output=True)
        return result.returncode, (result.stdout + result.stderr).decode("utf-8", "replace")

    def assertRejects(self, needle: str) -> None:
        code, out = self.run_check()
        self.assertEqual(code, FAIL, out)
        self.assertIn(needle, out)


class TestTheAllowlist(McpCase):
    def test_a_server_configured_but_not_allowlisted_is_rejected(self) -> None:
        """The failure this exists for: a server arriving without anyone deciding."""
        self.config([])
        self.tool_config(".mcp.json", {"github": {"command": "npx", "args": ["-y", "srv"]}})
        self.assertRejects("not in mcp_servers")

    def test_an_allowlisted_server_passes(self) -> None:
        self.config(["github@1.2.3"])
        self.tool_config(".mcp.json", {"github": {"command": "npx"}})
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)

    def test_a_floating_version_is_rejected(self) -> None:
        """The reviewed server and the running one have to be the same thing."""
        for version in ("latest", "^1.2.3", "~1.0", "1.x", ">=2", "main"):
            with self.subTest(version=version):
                self.config([f"github@{version}"])
                self.assertRejects("floats")

    def test_an_exact_version_is_accepted(self) -> None:
        for version in ("1.2.3", "2026.07.31", "0.1.0-rc.1"):
            with self.subTest(version=version):
                self.config([f"github@{version}"])
                code, out = self.run_check()
                self.assertEqual(code, PASS, out)

    def test_a_malformed_entry_is_rejected_rather_than_ignored(self) -> None:
        self.config(["github"])
        self.assertRejects("is not `<name>@<version>`")

    def test_a_duplicate_entry_is_rejected(self) -> None:
        """Two entries for one name means one of them is not doing what its author thinks."""
        self.config(["github@1.0.0 access=read", "github@2.0.0 access=write"])
        self.assertRejects("listed twice")


class TestProductionWrite(McpCase):
    def test_write_access_to_production_is_refused(self) -> None:
        self.config(["deployer@1.0.0 access=write env=production"])
        self.assertRejects("write access to production")

    def test_read_access_to_production_is_allowed(self) -> None:
        """Reading production is a different risk, and one this rule does not claim to cover."""
        self.config(["metrics@1.0.0 access=read env=production"])
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)

    def test_write_access_in_development_is_allowed(self) -> None:
        self.config(["scratch@1.0.0 access=write env=development"])
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)

    def test_the_default_is_the_safe_pairing(self) -> None:
        """An entry that declares nothing must not default into the refused combination, and
        must not default into silently claiming production write either."""
        self.config(["something@1.0.0"])
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)


class TestDrift(McpCase):
    def test_a_server_in_one_file_only_is_drift(self) -> None:
        self.config(["github@1.0.0"])
        self.tool_config(".mcp.json", {"github": {"command": "npx"}})
        self.tool_config(".cursor/mcp.json", {})
        self.assertRejects("only in .mcp.json")

    def test_the_same_server_defined_differently_is_drift(self) -> None:
        """Same names, different definitions — the case a set comparison would miss."""
        self.config(["github@1.0.0"])
        self.tool_config(".mcp.json", {"github": {"command": "npx", "args": ["a"]}})
        self.tool_config(".cursor/mcp.json", {"github": {"command": "npx", "args": ["b"]}})
        self.assertRejects("same servers, different definitions")

    def test_identical_files_are_not_drift(self) -> None:
        self.config(["github@1.0.0"])
        for name in (".mcp.json", ".cursor/mcp.json"):
            self.tool_config(name, {"github": {"command": "npx", "args": ["a"]}})
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)

    def test_formatting_and_key_order_are_not_drift(self) -> None:
        """Compared on the parsed object, so a reformat does not read as a disagreement —
        a check that cries wolf on whitespace is a check people delete."""
        self.config(["github@1.0.0"])
        (self.dir / ".mcp.json").write_text(
            '{"mcpServers":{"github":{"command":"npx","args":["a"]}}}', encoding="utf-8")
        (self.dir / ".cursor" / "mcp.json").write_text(textwrap.dedent("""\
            {
              "mcpServers": {
                "github": {
                  "args": ["a"],
                  "command": "npx"
                }
              }
            }
            """), encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)

    def test_one_file_present_and_one_absent_is_not_drift(self) -> None:
        """A tool that is not configured at all has not drifted from anything."""
        self.config(["github@1.0.0"])
        self.tool_config(".mcp.json", {"github": {"command": "npx"}})
        code, out = self.run_check()
        self.assertEqual(code, PASS, out)


class TestItCannotRunQuietly(McpCase):
    def test_a_missing_config_could_not_run(self) -> None:
        code, _ = self.run_check()
        self.assertEqual(code, COULD_NOT_RUN)

    def test_an_absent_allowlist_key_could_not_run(self) -> None:
        """Absent is not the same as empty. Treating it as empty would let deleting the key
        silently disable every check in this file."""
        (self.dir / "aios" / "config.yml").write_text("tier: prototype\n", encoding="utf-8")
        code, out = self.run_check()
        self.assertEqual(code, COULD_NOT_RUN, out)

    def test_unparseable_json_is_reported_not_skipped(self) -> None:
        self.config([])
        (self.dir / ".mcp.json").write_text("{not json", encoding="utf-8")
        self.assertRejects("not valid JSON")


class TestThisRepository(unittest.TestCase):
    def test_it_passes_here(self) -> None:
        result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, cwd=ROOT)
        self.assertEqual(result.returncode, PASS, result.stdout.decode())

    def test_the_gate_is_registered(self) -> None:
        import yaml
        gates = yaml.safe_load((ROOT / "aios" / "gates.yml").read_text(encoding="utf-8"))
        found = [g for g in gates["gates"] if g["id"] == "security.mcp_allowlist"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["class"], "contract")

    def test_the_config_key_is_no_longer_pending(self) -> None:
        import yaml
        schema = yaml.safe_load(
            (ROOT / "aios" / "config.schema.yml").read_text(encoding="utf-8"))
        entry = schema["keys"]["mcp_servers"]
        self.assertNotIn("pending", entry)
        self.assertIn("enforced_by", entry)


if __name__ == "__main__":
    unittest.main(verbosity=2)
