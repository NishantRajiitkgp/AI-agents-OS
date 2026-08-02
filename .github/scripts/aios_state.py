#!/usr/bin/env python3
"""Loading and parsing of aios project state, shared by the validators.

PROVISIONAL. Moves into the aios binary at M1-14, per ADR-006.

This module parses and does not judge. Each validator decides what counts as a violation;
if the parser also had opinions, a rule would have two homes and they could drift.

It exists because the reference resolver needs to read requirements and tasks, and a second
copy of either parser is precisely the duplication P3 forbids — two parsers that can disagree
about what a requirement *is* would make the resolver's answers depend on which one ran.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - environment failure, not a test case
    print("could not run: PyYAML is not available", file=sys.stderr)
    raise SystemExit(2)

ROOT = Path(__file__).resolve().parents[2]

REQ_HEADING = re.compile(r"^##\s+([A-Z][A-Z0-9]*)-(\d+)\s+—\s+(.+?)\s*$")
FIELD = re.compile(r"^\*\*([A-Za-z][A-Za-z -]*):\*\*\s*(.*)$", re.S)
FIELD_START = re.compile(r"^\*\*[A-Za-z][A-Za-z -]*:\*\*")
HRULE = re.compile(r"^-{3,}$")
SUPERSEDED = re.compile(r"^superseded-by:\s*([A-Z][A-Z0-9]*-\d+)\s*$")
TASK_ID = re.compile(r"^T-[0-9a-f]{4}([0-9a-f]{2})?$")
REQ_ID = re.compile(r"^[A-Z][A-Z0-9]*-\d+$")


class CouldNotRun(Exception):
    """Raised where the check cannot run at all, which is distinct from failing."""


def find_config(marker: str = "requirements") -> Path:
    """Locate config.yml.

    Its path cannot be derived from paths.state_dir, because it lives inside the directory
    that key names. Conventional location first, then a single-level glob for a directory
    holding both config.yml and the marker subdirectory. Q-003 records that this bootstrap
    is convention rather than contract.
    """
    conventional = ROOT / "aios" / "config.yml"
    if conventional.exists():
        return conventional
    found = sorted(p for p in ROOT.glob("*/config.yml") if (p.parent / marker).is_dir())
    if len(found) > 1:
        raise CouldNotRun(f"several candidate config files: {[str(p) for p in found]}")
    return found[0] if found else conventional


def load_config() -> dict:
    config = find_config()
    if not config.exists():
        raise CouldNotRun(f"{config} does not exist")
    try:
        return yaml.safe_load(config.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise CouldNotRun(f"{config} is not valid YAML: {exc}") from exc


def state_dir(sub: str) -> Path:
    """Resolve a state subdirectory through paths.state_dir rather than hardcoding it."""
    try:
        name = load_config()["paths"]["state_dir"]
    except (KeyError, TypeError) as exc:
        raise CouldNotRun(f"paths.state_dir unreadable: {exc}") from exc
    return ROOT / name / sub


def relative(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.name  # a fixture outside the repository


# --------------------------------------------------------------------------- requirements

def paragraphs(lines: list[str]) -> list[str]:
    """Blank-line separated units, except that a bold field label always starts a new one.

    Fields are written on consecutive lines with no blank between them, so splitting on
    blank lines alone would fuse Status into Rationale and make the status unreadable.
    """
    out: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            out.append(" ".join(buf))
            buf.clear()

    for line in lines:
        text = line.strip()
        if not text or HRULE.match(text):
            flush()
            continue
        if FIELD_START.match(text):
            flush()
        buf.append(text)
    flush()
    return out


def parse_requirements(path: Path) -> list[dict]:
    """Split an area file into requirement sections with their fields and clauses."""
    sections: list[dict] = []
    current: dict | None = None

    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        match = REQ_HEADING.match(line)
        if match:
            current = {"area": match.group(1), "num": match.group(2), "title": match.group(3),
                       "id": f"{match.group(1)}-{match.group(2)}", "line": lineno,
                       "file": path, "raw": []}
            sections.append(current)
        elif line.startswith("## "):
            current = None  # a non-requirement heading ends the previous section
        elif current is not None:
            current["raw"].append(line)

    for section in sections:
        fields: dict[str, str] = {}
        clauses: list[str] = []
        for para in paragraphs(section["raw"]):
            match = FIELD.match(para)
            if match:
                fields[match.group(1).strip().lower()] = match.group(2).strip()
            else:
                clauses.append(para)
        section["fields"] = fields
        section["clauses"] = clauses
        section["status"] = fields.get("status", "").strip()
    return sections


def load_requirements(directory: Path) -> list[dict]:
    if not directory.is_dir():
        raise CouldNotRun(f"{directory} does not exist")
    files = sorted(directory.glob("*.md"))
    if not files:
        raise CouldNotRun(f"no area files in {directory}")
    return [section for path in files for section in parse_requirements(path)]


# --------------------------------------------------------------------------------- tasks

def parse_task(path: Path) -> tuple[dict | None, str, str | None]:
    """Return (frontmatter, body, error). A parse error is returned, never raised."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        return None, "", "no YAML frontmatter"
    end = text.find("\n---", 4)
    if end == -1:
        return None, "", "frontmatter is not terminated"
    try:
        data = yaml.safe_load(text[4:end])
    except yaml.YAMLError as exc:
        hint = ""
        if "alias" in str(exc).lower():
            # A scalar starting with `*` is an alias node, so an unquoted `**/x.py` in
            # `touches` breaks the whole file. The raw error names anchors and aliases and
            # never mentions globs, which sends people looking in the wrong place.
            hint = (' — a value beginning with "*" is a YAML alias; a glob like **/x.py '
                    'must be quoted')
        return None, "", f"frontmatter is not valid YAML: {exc}{hint}"
    if not isinstance(data, dict):
        return None, "", "frontmatter is not a mapping"
    return data, text[end + 4:], None


def load_tasks(directory: Path) -> list[dict]:
    """Every markdown file under tasks/, including the done/ subtree.

    Globbing on the expected T-*.md name would mean a file that got its name wrong is
    silently unchecked, which is the one result a validator must not produce.
    """
    if not directory.is_dir():
        raise CouldNotRun(f"{directory} does not exist")
    tasks = []
    for path in sorted(directory.rglob("*.md")):
        data, body, error = parse_task(path)
        tasks.append({"path": path, "data": data or {}, "body": body, "error": error,
                      "lines": len(path.read_text(encoding="utf-8").splitlines())})
    return tasks
