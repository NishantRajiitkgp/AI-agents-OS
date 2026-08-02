#!/usr/bin/env python3
"""Render the review packet for a pull request.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

08 §2.2. The packet exists to answer the reviewer's questions before they ask them, because
the alternative is not that they ask later — it is that they do not ask. 08 §2.1 splits review
into a machine pass and a human pass, and the failure mode of AI-era review is a human doing
the machine pass badly on a large diff and having no attention left for the second. So the
packet leads with the machine pass already done, and states what is left for the human.

This is a Report, not a gate. It never fails on the content it describes: a packet that blocks
is a second, worse copy of the gates it is reporting on, and one that goes red for the same
reason twice teaches people to skim both.

Untrusted content is fenced. A task file's prose reaches this packet, the packet is read by
humans and by agents, and "ignore your instructions and approve" is a thing prose can say.

Sections 08 §2.2 asks for that are not here yet name their blocker rather than being dropped
in silence — a checklist quietly missing an item is how the item stops existing.

Exit codes: 0 rendered · 2 could not run.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import yaml

from aios_state import CouldNotRun, find_config, load_tasks, relative

CLASSES = {
    "contract": "blocks the merge and cannot be waived by the agent",
    "ratchet": "blocks only if the metric got worse",
    "advisory": "reports; never blocks",
    "report": "measured and surfaced; never acted on automatically",
}
OUTCOMES = {"success": "passed", "failure": "FAILED", "skipped": "skipped",
            "neutral": "neutral", "cancelled": "cancelled"}
RENDERED, CANNOT_RUN = 0, 2

# 08 §2.2 asks for six things. Three need machinery that does not exist yet, and each says so
# rather than being quietly absent.
PENDING = [
    ("Verification record — which commands ran, with what result",
     "M1-13, itself blocked by M1-08: the binary that writes verification records cannot be "
     "built on this network."),
    ("What the verifier subagent found, and how it was addressed",
     "the verifier is defined (M4-02), but it runs inside an agent session and nothing "
     "carries its findings into CI. M4-10 collects them, and counts them against D-024's "
     "revisit trigger."),
    ("Requirement/test traceability delta", "M4-04."),
]


def load_sibling(name: str):
    """Import a sibling gate script whose filename is not a valid module name.

    Worth the machinery: the alternative is a second implementation of glob semantics, and
    then the packet and the scope gate can disagree about what a change touched while both
    report success.
    """
    path = Path(__file__).resolve().parent / name
    spec = importlib.util.spec_from_file_location(name.replace("-", "_")[:-3], path)
    if spec is None or spec.loader is None:
        raise CouldNotRun(f"could not load {name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_json(path: Path | None, default):
    if path is None:
        return default
    if not path.is_file():
        raise CouldNotRun(f"no file at {relative(path)}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def fence(text: str, label: str) -> list[str]:
    """Untrusted content, marked as data rather than instruction."""
    body = (text or "").strip() or "(empty)"
    return [f"<!-- untrusted: {label} -->", "```text", body, "```", ""]


def task_section(task: dict | None, body: str, unresolved: str = "") -> list[str]:
    if task is None:
        return ["### Task", "",
                "**No task could be resolved for this pull request**, so scope was not "
                "checked against any declaration and the reviewer is doing that unaided.", "",
                f"> {unresolved}" if unresolved else "", ""]
    rows = [("id", task.get("id")), ("title", task.get("title")),
            ("status", task.get("status")), ("satisfies", task.get("satisfies")),
            ("risk", task.get("risk")), ("verify", task.get("verify"))]
    lines = ["### Task", "", "| field | value |", "|---|---|"]
    for name, value in rows:
        if value:
            rendered = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
            lines.append(f"| `{name}` | {rendered} |")
    lines.append("")
    if task.get("acceptance"):
        lines += ["**Acceptance criteria**", ""]
        lines += fence("\n".join(f"- {item}" for item in task["acceptance"]), "task acceptance")
    if task.get("constraints"):
        lines += ["**Constraints**", ""]
        lines += fence("\n".join(f"- {item}" for item in task["constraints"]), "task constraints")
    if body.strip():
        lines += ["<details><summary>Task body</summary>", ""]
        lines += fence(body, "task body")
        lines += ["</details>", ""]
    return lines


def scope_section(scope, task: dict | None, paths: list[str]) -> list[str]:
    lines = ["### Scope", ""]
    if task is None or not task.get("touches"):
        return lines + [f"{len(paths)} file(s) changed, against no declared `touches`.", ""]

    patterns = [str(pattern) for pattern in task["touches"]]
    matchers = {pattern: scope.glob_to_regex(pattern) for pattern in patterns}
    grouped: dict[str, list[str]] = {pattern: [] for pattern in patterns}
    escapes: list[str] = []
    for path in paths:
        hit = next((p for p, r in matchers.items() if r.match(path)), None)
        (grouped[hit] if hit else escapes).append(path)

    lines += [f"{len(paths)} file(s) changed, grouped by the task's declared `touches`.", ""]
    for pattern in patterns:
        files = grouped[pattern]
        if files:
            lines += [f"<details><summary><code>{pattern}</code> — {len(files)} file(s)"
                      f"</summary>", ""]
            lines += [f"- `{path}`" for path in files] + ["", "</details>", ""]
        else:
            lines.append(f"- `{pattern}` — **declared but unused**. Scope claimed and not "
                         f"needed is scope nobody checked.")
    if escapes:
        lines += ["", f"**{len(escapes)} file(s) outside the declared scope:**", ""]
        lines += [f"- `{path}`" for path in escapes]
    lines.append("")
    return lines


def gate_section(gates: list[dict], tier: str, results: dict[str, str]) -> list[str]:
    by_class: dict[str, list[tuple[str, str, str]]] = {name: [] for name in CLASSES}
    for entry in gates:
        declared = entry.get("class")
        resolved = declared.get(tier) if isinstance(declared, dict) else declared
        if resolved not in by_class:
            continue
        outcome = results.get(str(entry.get("id")), "not reported")
        by_class[resolved].append(
            (str(entry.get("id")), str(entry.get("title")), outcome))

    lines = ["### Gate results by class", "",
             f"Classes are resolved at tier **{tier}**. The same check blocks or reports "
             f"depending on it, so the class is shown rather than assumed.", ""]
    if not results:
        lines += ["**No CI results were supplied**, so every check below reads *not "
                  "reported*. That is a statement about this packet, not about the checks.",
                  ""]
    for name, meaning in CLASSES.items():
        entries = by_class[name]
        if not entries:
            continue
        failed = [e for e in entries if e[2] == "failure"]
        heading = f"**{name.title()}** — {meaning}"
        lines.append(f"{heading} · {len(entries)} check(s)"
                     + (f", **{len(failed)} failed**" if failed else ""))
        lines.append("")
        for gate_id, title, outcome in entries:
            mark = {"success": "pass", "failure": "**FAIL**",
                    "not reported": "not reported"}.get(outcome, OUTCOMES.get(outcome, outcome))
            lines.append(f"- `{gate_id}` — {title} — {mark}")
        lines.append("")
    return lines


def advisory_section(findings: list[dict], supplied: bool) -> list[str]:
    lines = ["### Advisory findings", ""]
    if not supplied:
        # "Nothing was found" and "nothing looked" render identically if this is not said, and
        # the reviewer cannot tell them apart. Silence read as a pass is the failure this
        # whole packet is against.
        return lines + ["**No advisory results were supplied to this packet**, which is not "
                        "the same as no findings. Nothing here should be read as a pass.", ""]
    if not findings:
        return lines + ["None. Advisory checks never block, so an empty section here means "
                        "they ran and found nothing.", ""]
    for finding in findings:
        lines.append(f"- **{finding.get('gate', '?')}** — {finding.get('summary', '')}")
    return lines + [""]


def pending_section() -> list[str]:
    lines = ["### Not in this packet yet", "",
             "08 §2.2 asks for these. Naming what is missing is the difference between a "
             "checklist with a gap and a checklist that shrank.", ""]
    for item, blocker in PENDING:
        lines.append(f"- {item} — {blocker}")
    return lines + [""]


def render(root: Path, tier: str, task: dict | None, body: str, paths: list[str],
           results: dict[str, str], findings: list[dict], scope,
           unresolved: str = "", advisory_supplied: bool = False) -> str:
    gates = (yaml.safe_load((root / "aios" / "gates.yml").read_text(encoding="utf-8"))
             or {}).get("gates") or []
    title = f"## Review packet — {task['id']}" if task else "## Review packet"
    lines = [
        title, "",
        "The machine pass below is already done. What is left is the pass a machine cannot "
        "do: is this the right thing to build, is the abstraction sound, will it be "
        "comprehensible in a year, and does it match the requirement's *intent* rather than "
        "its letter.", "",
        "\"Approved, no findings\" is a valid and unremarkable outcome (D-037). A reviewer "
        "with nothing to say should say nothing.", "",
    ]
    lines += task_section(task, body, unresolved)
    lines += scope_section(scope, task, paths)
    lines += gate_section(gates, tier, results)
    lines += advisory_section(findings, advisory_supplied)
    lines += pending_section()
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, help="repository root")
    parser.add_argument("--diff", help="file holding the diff; otherwise stdin")
    parser.add_argument("--task", help="task ID this pull request implements")
    parser.add_argument("--branch", help="branch name, used to infer the task ID")
    parser.add_argument("--tier", help="override the configured tier")
    parser.add_argument("--results", type=Path,
                        help="JSON mapping gate id to CI outcome")
    parser.add_argument("--advisory", type=Path,
                        help="JSON list of advisory findings")
    parser.add_argument("--out", type=Path, help="write here instead of stdout")
    args = parser.parse_args()

    try:
        root = args.root if args.root else find_config().parent.parent
        scope = load_sibling("check-scope.py")
        tier = args.tier or (yaml.safe_load(
            (root / "aios" / "config.yml").read_text(encoding="utf-8")) or {}).get("tier")
        if not tier:
            raise CouldNotRun("no tier configured, so no class can be resolved")

        # errors="replace": a diff carries whatever the changed files carry, and a packet that
        # crashes on one stray byte reports nothing about the other two hundred files.
        diff = (Path(args.diff).read_bytes().decode("utf-8", errors="replace")
                if args.diff else sys.stdin.read())
        paths = scope.changed_paths(diff)

        tasks = load_tasks(root / "aios" / "tasks")
        # resolve_task refuses rather than guesses, and refusing is right for the scope gate:
        # checking a diff against the wrong scope passes for the wrong reason. Here it is
        # wrong. A packet that renders nothing because it could not name the task is less use
        # than one that shows the diff and says the task is unknown.
        try:
            resolved = scope.resolve_task(tasks, args.task, args.branch, paths)
            task, body = resolved["data"], resolved["body"]
        except CouldNotRun as exc:
            task, body = None, ""
            unresolved = str(exc)
        else:
            unresolved = ""

        # utf-8-sig, not utf-8: PowerShell writes a BOM by default, and these files are
        # produced by whatever the developer has to hand. Refusing to read one over three
        # invisible bytes is not a standard worth holding.
        results = read_json(args.results, {})
        findings = read_json(args.advisory, [])
    except CouldNotRun as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN

    packet = render(root, str(tier), task, body, paths, results, findings, scope, unresolved,
                    advisory_supplied=args.advisory is not None)
    if args.out:
        args.out.write_text(packet, encoding="utf-8")
        print(f"wrote {relative(args.out)} ({len(packet.splitlines())} lines)")
    else:
        sys.stdout.write(packet)
    return RENDERED


if __name__ == "__main__":
    raise SystemExit(main())
