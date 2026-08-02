#!/usr/bin/env python3
"""Allowlist MCP servers, and fail when the two tool configs disagree about them.

PROVISIONAL. Moves into the binary at `M1-08`.

An MCP server is a channel through which content the agent did not write arrives in its
context, and a set of tools it can call. Both halves matter: tool output is untrusted input
(07 §1.3), and a server with write access is a capability the permission layer cannot see.

Three checks, each answering a different way this goes wrong:

- **Unlisted.** A server configured in a tool file but absent from `aios/config.yml`. That is
  how a server arrives without anyone deciding it should.
- **Unpinned.** A server on a floating version. The reviewed artifact and the running one are
  then different things, and nothing notices the day they diverge.
- **Drift.** `.mcp.json` and `.cursor/mcp.json` describing different sets. The tool nobody is
  looking at is the one that keeps the server somebody thought they removed.

The production-write rule is a *declaration* check, and deliberately so. Nothing here can tell
what a server reaches; what it can do is refuse an entry that admits to holding production
write access in a development profile, and make that admission the cheap path.

Usage:
    check-mcp.py                     check this repository
    check-mcp.py --dir <path>        check a fixture tree

Exit 0 pass, 1 fail, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config

# `<name>@<version>` plus optional `access=` and `env=` declarations.
ENTRY = re.compile(
    r"^(?P<name>[A-Za-z0-9._-]+)@(?P<version>\S+)"
    r"(?:\s+access=(?P<access>read|write))?"
    r"(?:\s+env=(?P<env>development|production))?$")

# A pin is a version, not a wish. These are the ways a config says "whatever is current".
FLOATING = re.compile(r"^(latest|main|master|\*|)$|[\^~><]|\.x$", re.IGNORECASE)

CONFIG_FILES = (".mcp.json", ".cursor/mcp.json")


def parse_entry(raw: str) -> tuple[dict | None, str | None]:
    match = ENTRY.match(raw.strip())
    if not match:
        return None, (f"mcp_servers: {raw!r} is not `<name>@<version>` with optional "
                      f"`access=read|write` and `env=development|production`")
    entry = match.groupdict()
    entry["access"] = entry["access"] or "read"
    entry["env"] = entry["env"] or "development"
    return entry, None


def servers_in(path: Path) -> tuple[dict | None, str | None]:
    """The `mcpServers` object, or None when the file is absent."""
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        return None, f"{path}: not valid JSON ({exc})"
    servers = data.get("mcpServers")
    if servers is None:
        return {}, None
    if not isinstance(servers, dict):
        return None, f"{path}: mcpServers is {type(servers).__name__}, expected an object"
    return servers, None


def check(root: Path, allowlist: list[str]) -> list[str]:
    problems: list[str] = []
    allowed: dict[str, dict] = {}

    for raw in allowlist:
        entry, problem = parse_entry(str(raw))
        if problem:
            problems.append(problem)
            continue
        if entry["name"] in allowed:
            problems.append(f"mcp_servers: {entry['name']!r} is listed twice")
        allowed[entry["name"]] = entry

        if FLOATING.search(entry["version"]):
            problems.append(
                f"mcp_servers: {entry['name']} is pinned to {entry['version']!r}, which "
                f"floats. The reviewed server and the running one must be the same thing.")
        if entry["access"] == "write" and entry["env"] == "production":
            problems.append(
                f"mcp_servers: {entry['name']} declares write access to production. No such "
                f"server belongs in a development profile (07 §1.3) — the permission layer "
                f"cannot see what an MCP tool reaches, so this one is decided here or not at "
                f"all.")

    present: dict[str, dict] = {}
    for name in CONFIG_FILES:
        servers, problem = servers_in(root / name)
        if problem:
            problems.append(problem)
            continue
        if servers is None:
            continue
        present[name] = servers
        for server in servers:
            if server not in allowed:
                problems.append(
                    f"{name}: {server!r} is configured but not in mcp_servers. A server "
                    f"arriving without a decision is the failure this allowlist exists for.")

    # Drift, compared on the parsed object so formatting differences are not reported as
    # disagreement and reordering is not either.
    if len(present) == 2:
        first, second = CONFIG_FILES
        if present[first] != present[second]:
            only_first = sorted(set(present[first]) - set(present[second]))
            only_second = sorted(set(present[second]) - set(present[first]))
            detail = []
            if only_first:
                detail.append(f"only in {first}: {only_first}")
            if only_second:
                detail.append(f"only in {second}: {only_second}")
            if not detail:
                detail.append("same servers, different definitions")
            problems.append(
                f"{first} and {second} disagree ({'; '.join(detail)}). Both are read, so the "
                f"one nobody is looking at is the one still holding a server somebody thought "
                f"they had removed.")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", help="repository root, for tests")
    args = parser.parse_args()

    try:
        if args.dir:
            root = Path(args.dir)
            config_path = root / "aios" / "config.yml"
            if not config_path.is_file():
                raise CouldNotRun(f"{config_path} does not exist")
        else:
            config_path = find_config()
            root = config_path.parent.parent
        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except (CouldNotRun, OSError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return 2

    allowlist = config.get("mcp_servers")
    if allowlist is None:
        print("could not run: mcp_servers is not set in config.yml", file=sys.stderr)
        return 2

    problems = check(root, list(allowlist))
    if problems:
        for problem in problems:
            print(f"  violation: {problem}")
        print(f"\n{len(problems)} violation(s).")
        return 1

    configured = sum(1 for name in CONFIG_FILES if (root / name).is_file())
    print(f"MCP: {len(allowlist)} server(s) allowlisted, {configured} tool config(s) present, "
          f"no drift.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
