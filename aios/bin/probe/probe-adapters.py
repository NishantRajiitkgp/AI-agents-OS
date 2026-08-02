#!/usr/bin/env python3
"""Stage, inspect and tear down an adapter-discovery probe run (M4-12).

PROVISIONAL. Becomes `aios probe-adapters` at `M1-08` — a subcommand and not a script, for the
reason in [ADR-006](../../../docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md), which
exists because the original version of this was a `.ps1` that could not execute at all.

What is automated here is setup, marker generation and teardown. Observation is not, and will
not be: it consists of asking a tool a question and reading its answer, which no script can do
([prompt.md](prompt.md) holds the question and the three protocols).

The hard part is teardown, and it got harder since `M0`. That run could delete everything it
staged unconditionally, because `AGENTS.md`, `.claude/` and `.cursor/rules/` did not exist
yet — every path it touched was its own. Today all three are real, and two of them are
always-on context. A probe that appends a marker to `AGENTS.md` and removes it *approximately*
leaves a marker in the file the entire instruction layer rests on, which is precisely the
class of silent staleness this project exists to catch.

So the manifest records, per path, whether the file existed before and its exact bytes if it
did, and teardown restores rather than deletes. Byte-exact, verified by hash, non-zero exit if
any file does not come back to what it was. A teardown that reports success while leaving the
repository changed is worse than one that fails loudly, because the next probe then measures
the previous one's residue.

Two smaller decisions worth stating. **Staged files conform to the repository's own gates** —
the probe command file is a real one-invocation command, the probe subagent is a real
subagent — so that a staged tree cannot be mistaken for a broken one. And **nothing staged
narrates that a probe is happening**: `M0` found that an announcement in `AGENTS.md` confounded
the behavioural half of the run, because sessions read it and performed compliance.

Usage:
    probe-adapters.py stage      write the marker files, record the manifest
    probe-adapters.py status     what is staged, and what it is costing
    probe-adapters.py teardown   restore every path to what it was

Exit 0 pass, 1 fail, 2 could not run (ADR-013).
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
from datetime import date
from pathlib import Path

MANIFEST = ".aios-probe.json"

PASS, FAIL, COULD_NOT_RUN = 0, 1, 2

# One label per measurable location. `DECOY` is the control and deliberately has no file: a
# tool that reports a marker for it invented one, and the run is void. Without it a null
# result cannot be told apart from a tool that answers plausibly rather than truthfully.
DECOY = "DECOY"


def markers(run: str) -> dict[str, str]:
    labels = ["ROOTMD", "NESTED", "CURSORALWAYS", "CURSORGLOB", "CLAUDEAGENTDESC",
              "CLAUDEAGENTBODY", "CLAUDESKILLDESC", "CLAUDESKILLBODY", "CLAUDECMD"]
    return {label: f"AIOS-PROBE-{label}-{secrets.token_hex(4)}" for label in labels}


def files(m: dict[str, str]) -> dict[str, str]:
    """Path → content. Appended to when the path already exists, written when it does not.

    Every body here is marker and structure only. Explaining the probe inside the probe is
    what `M0` did, and it measured the agent's willingness to perform rather than the tool's
    discovery.
    """
    return {
        "AGENTS.md": f"\n{m['ROOTMD']}\n",

        # Protocol B works a file inside this directory. The nested AGENTS.md is the D-001
        # test; the glob rule beside it is what tells "nested AGENTS.md does not work" apart
        # from "path scoping does not work here at all".
        "probe-nested/AGENTS.md": f"{m['NESTED']}\n",
        "probe-nested/probe-target.txt": "Edit this file when running Protocol B.\n",

        ".cursor/rules/aios-probe-always.mdc":
            f"---\nalwaysApply: true\n---\n\n{m['CURSORALWAYS']}\n",
        ".cursor/rules/aios-probe-glob.mdc":
            f"---\nglobs: probe-nested/**\n---\n\n{m['CURSORGLOB']}\n",

        # Description and body carry separate markers because they were measured to load
        # differently: a description is always-on and spends the budget, a body is pulled.
        ".claude/agents/aios-probe.md":
            f"---\nname: aios-probe\ndescription: {m['CLAUDEAGENTDESC']}\ntools: Read\n---\n\n"
            f"Read-only. Reports {m['CLAUDEAGENTBODY']} when asked.\n",
        ".claude/skills/aios-probe/SKILL.md":
            f"---\nname: aios-probe\ndescription: {m['CLAUDESKILLDESC']}\n---\n\n"
            f"{m['CLAUDESKILLBODY']}\n",

        # Shaped to satisfy check-commands.py: prose first, then exactly one invocation. A
        # staged tree that fails the repository's own gates would be indistinguishable from a
        # broken one.
        ".claude/commands/aios-probe.md":
            f"---\ndescription: Report the adapter probe marker.\n---\n\n"
            f"Reports the marker {m['CLAUDECMD']} for the current run.\n\n"
            f"```\npython .github/scripts/check-commands.py\n```\n",
    }


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stage(root: Path) -> int:
    manifest_path = root / MANIFEST
    if manifest_path.exists():
        print(f"could not run: {MANIFEST} exists, so a run is already staged. Tear it down "
              f"first — staging over it would record the staged state as the baseline and "
              f"make the marker permanent.", file=sys.stderr)
        return COULD_NOT_RUN

    run = secrets.token_hex(4)
    m = markers(run)
    entries = []

    for relative, content in files(m).items():
        path = root / relative
        existed = path.is_file()
        original = path.read_bytes() if existed else b""
        path.parent.mkdir(parents=True, exist_ok=True)
        staged = original + content.encode("utf-8") if existed else content.encode("utf-8")
        path.write_bytes(staged)
        entries.append({
            "path": relative,
            "pre_existing": existed,
            "original_sha256": digest(original) if existed else None,
            "original_base64": base64.b64encode(original).decode() if existed else None,
            "staged_sha256": digest(staged),
        })

    manifest_path.write_text(json.dumps({
        "run": run,
        "staged_on": date.today().isoformat(),
        "markers": m,
        "decoy": DECOY,
        "files": entries,
    }, indent=2) + "\n", encoding="utf-8")

    print(f"staged run {run}: {len(entries)} file(s), {len(m)} marker(s), decoy {DECOY}.")
    print(f"  {sum(1 for e in entries if e['pre_existing'])} pre-existing file(s) appended "
          f"to and restored on teardown; the rest are created and removed.")
    print(f"Ask the question in aios/bin/probe/prompt.md from a fresh session. Not this one: "
          f"an observer that wrote the markers cannot tell reading them from remembering "
          f"writing them.")
    return PASS


def load(root: Path) -> dict:
    path = root / MANIFEST
    if not path.is_file():
        raise FileNotFoundError(f"{MANIFEST} does not exist; nothing is staged")
    return json.loads(path.read_text(encoding="utf-8"))


def status(root: Path) -> int:
    try:
        manifest = load(root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    print(f"run {manifest['run']}, staged {manifest['staged_on']}")
    drifted = 0
    for entry in manifest["files"]:
        path = root / entry["path"]
        if not path.is_file():
            state = "MISSING"
            drifted += 1
        elif digest(path.read_bytes()) != entry["staged_sha256"]:
            state = "EDITED since staging"
            drifted += 1
        else:
            state = "appended" if entry["pre_existing"] else "created"
        print(f"  {state:<20} {entry['path']}")

    print("\nWhile staged, this repository is deliberately not in a committable state: the "
          "probe adds always-on context, so the always-on ratchet is expected to read high. "
          "Tear down before committing anything.")
    if drifted:
        print(f"{drifted} file(s) changed since staging. Teardown will report each one "
              f"rather than restoring silently over an edit that was not the probe's.")
    return PASS


def teardown(root: Path) -> int:
    try:
        manifest = load(root)
    except (FileNotFoundError, ValueError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    problems: list[str] = []
    for entry in manifest["files"]:
        path = root / entry["path"]
        relative = entry["path"]

        if path.is_file() and digest(path.read_bytes()) != entry["staged_sha256"]:
            problems.append(f"{relative} was edited after staging; the edit is being "
                            f"discarded with the marker. Recover it from git if it mattered.")

        if entry["pre_existing"]:
            original = base64.b64decode(entry["original_base64"])
            path.write_bytes(original)
            if digest(path.read_bytes()) != entry["original_sha256"]:
                problems.append(f"{relative} did not restore to its original bytes.")
        elif path.is_file():
            path.unlink()

    # Directories the probe created are removed only when empty, so a probe cannot take a
    # real directory with it on the way out.
    for entry in reversed(manifest["files"]):
        if entry["pre_existing"]:
            continue
        parent = (root / entry["path"]).parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent

    # There was a "still present after teardown" sweep here. A mutation proved it unreachable:
    # `unlink` raises rather than failing quietly, and that exception is a could-not-run at the
    # top level. An assertion no test can reach is not a safety net, it is a claim of one.

    if problems:
        for problem in problems:
            print(f"  {problem}")
        print(f"\nteardown incomplete. The manifest is kept so it can be retried; a probe "
              f"that reports success while leaving markers behind poisons the next run.")
        return FAIL

    (root / MANIFEST).unlink()
    print(f"run {manifest['run']} torn down: {len(manifest['files'])} path(s) restored, "
          f"verified by hash. Commit the results file, not the probe.")
    return PASS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["stage", "status", "teardown"])
    parser.add_argument("--root", help="repository root, for tests")
    args = parser.parse_args()

    root = Path(args.root) if args.root else Path(__file__).resolve().parents[3]
    if not (root / "aios").is_dir():
        print(f"could not run: {root} is not an aios repository", file=sys.stderr)
        return COULD_NOT_RUN

    try:
        return {"stage": stage, "status": status, "teardown": teardown}[args.action](root)
    except OSError as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN


if __name__ == "__main__":
    raise SystemExit(main())
