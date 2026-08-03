#!/usr/bin/env python
"""Refuse a write outside the active mode's permission set.

PROVISIONAL. Moves into the binary with the rest of the hook logic (ADR-006, Q-005).

M4-03 requires a write outside the active mode to be refused *by the tool*, not by prose. In
Cursor that means a `preToolUse` hook, which is the only checked-in artifact that can decline
a tool call. Its event shape was measured rather than assumed —
[record](../probe/results/hook-event-2026-08-01.md) — because assuming it is what produced the
[fail-closed incident](../../incidents/2026-07-31-fail-closed-hook-blocked-every-command.md).

Two things from that measurement are load-bearing here:

- **stdin carries a UTF-8 BOM**, so the payload is decoded `utf-8-sig`. Decoding it as plain
  UTF-8 raises, and a hook that treats "I could not parse this" as "I have no input" is how
  the earlier hook came to refuse every command in the editor.
- **Creating and editing a file both arrive as `tool_name: "Write"`**, so there is one branch
  rather than two, and `tool_input.file_path` is where the path lives.

No mode means no restriction. That is deliberate: a template whose default is refusal blocks a
fresh clone before anyone has configured it, and the resulting instinct is to delete the hook
rather than to set a mode.
"""

from __future__ import annotations

import fnmatch
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import respond  # the shared response layer sits beside this file

ALLOW = {"permission": "allow"}
MODE_FILE = ".aios-mode"
SESSION_FILE = ".aios-session"
APPROVAL_FILE = ".aios-approval"
ATTEMPTS_FILE = ".aios-attempts"
WRITER_FILE = ".aios-writer"
WRITING_TOOLS = {"Write"}


def read_event() -> dict:
    """The measured contract: one JSON object on stdin, BOM-prefixed, CRLF-terminated.

    Read a *line*, not to end-of-stream, and the difference is not stylistic. `read()` waits
    for EOF, which never arrives if the caller holds the pipe open; measured, it hangs
    indefinitely where `readline()` returns in 0.3s on the identical input. A hook registered
    `failClosed` that hangs is every write in the editor refused when the timeout fires, with
    a message naming an exit code rather than a hang — which is how this cost a day across
    three incidents before anyone tested the read itself.
    """
    raw = sys.stdin.buffer.readline()
    return json.loads(raw.decode("utf-8-sig").strip())


def find_root(event: dict) -> Path | None:
    """`CURSOR_PROJECT_DIR` first: the measurement showed top-level `cwd` is absent on writes.

    Falling back to a field that is only sometimes there would produce a control that works
    on shell commands and quietly stops working on the tool it exists to govern.
    """
    for candidate in (os.environ.get("CURSOR_PROJECT_DIR"), event.get("cwd"), os.getcwd()):
        if not candidate:
            continue
        path = Path(candidate)
        if (path / "aios" / "config.yml").is_file():
            return path
    return None


def load_config(root: Path) -> dict:
    """Parsed without PyYAML: a hook runs on whatever interpreter the editor has, and a
    missing third-party import must not become a refusal. Only the shapes this file writes
    are supported, and anything unrecognised leaves the mode undefined rather than guessed."""
    modes: dict[str, list[str] | str] = {}
    text = (root / "aios" / "config.yml").read_text(encoding="utf-8")
    in_modes = False
    current: str | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            in_modes = line.strip() == "modes:"
            current = None
            continue
        if not in_modes:
            continue
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if indent == 2 and stripped.endswith(":"):
            current = stripped[:-1]
            modes[current] = []
        elif current and stripped.startswith("writes:"):
            value = stripped[len("writes:"):].strip()
            if value == "[]":
                modes[current] = []
            elif value:
                modes[current] = value
        elif current and stripped.startswith("- "):
            entry = modes.get(current)
            if isinstance(entry, list):
                entry.append(stripped[2:].strip().strip('"\''))
    return modes


def active_mode(root: Path) -> tuple[str | None, str | None]:
    """`<mode>` or `<mode> <task-id>`, one line, uncommitted."""
    path = root / MODE_FILE
    if not path.is_file():
        return None, None
    parts = path.read_text(encoding="utf-8").split()
    if not parts:
        return None, None
    return parts[0], (parts[1] if len(parts) > 1 else None)


def task_file(root: Path, task_id: str | None) -> Path | None:
    if not task_id:
        return None
    for path in (root / "aios" / "tasks").rglob(f"{task_id}.md"):
        return path
    return None


def field_list(path: Path, field: str) -> list[str]:
    """A top-level list field from the task's frontmatter.

    An absent field and an empty one both return `[]`. Nothing here needs to tell them apart —
    a task with no `touches` and one with an empty `touches` both permit nothing, and the same
    holds for `duplicate_check` — and a distinction no caller reads is a branch that can rot
    without any test noticing.
    """
    entries, collecting = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(f"{field}:"):
            collecting = True
            inline = line[len(field) + 1:].strip()
            if inline and inline != "[]":
                return [inline.strip('"\'')]
            continue
        if collecting:
            if line.startswith("  - "):
                entries.append(line[4:].strip().strip('"\''))
            elif line.strip() and not line.startswith(" "):
                collecting = False
    return entries


def duplicate_check_missing(path: Path) -> bool:
    """M4-04: implementation may not begin until the search for what already exists has.

    Duplication rises and refactoring falls under AI assistance, and the counter is checking
    before writing — which only happens if something makes it happen. `aios start` was meant
    to be that something; it does not exist yet, and the first write in implement mode is the
    same moment by a different name.
    """
    entries = field_list(path, "duplicate_check")
    return not entries or not any(entry.strip() for entry in entries)


def autonomy_level(root: Path, task_path: Path) -> tuple[str, int]:
    """M4-05. `risk` × `tier` decides how many tasks may begin without a human.

    A0 is zero rather than one: the approval is what permits the first, so an A0 task without
    one has been permitted nothing. A1 is one — the default, and always-stop. A2 is the
    configured limit, and exists so trivial work does not consume the review attention that
    non-trivial work needs.

    The table lives in config.yml, which is outside the agent's write scope. Its invariants —
    `risk: high` never reaches A2, and autonomy only tightens as risk or tier rises — are
    checked by `check-autonomy.py` in CI, not here: a client-side control asserting its own
    policy is not evidence of anything.
    """
    text = (root / "aios" / "config.yml").read_text(encoding="utf-8")
    tier = ""
    limit = 1
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if line.startswith("tier:"):
            tier = line.split(":", 1)[1].strip().strip('"\'')
        elif line.strip().startswith("chain_limit:"):
            try:
                limit = int(line.split(":", 1)[1].strip())
            except ValueError:
                limit = 1
        elif line.strip().startswith('- "') and "low=" in line and "high=" in line:
            entry = line.strip()[3:].rstrip('"')
            name, _, rest = entry.partition(":")
            rows[name.strip()] = dict(
                pair.split("=", 1) for pair in rest.split() if "=" in pair)

    risk = (field_list(task_path, "risk") or [""])[0]
    level = rows.get(tier, {}).get(risk, "A1")  # unknown pairing gets the default, not more
    return level, {"A0": 0, "A1": 1}.get(level, limit)


def stuck_test(root: Path, limit: int = 3) -> str | None:
    """M4-06: the same test failed `limit` times since it last passed.

    Counted from the ledger `record-attempt.py` writes by observing test runs, not from
    anything the agent reports about itself — the rule exists precisely for the moment when
    self-reporting is least trustworthy. A pass clears the count, because the rule is about
    being stuck, not about having ever failed.
    """
    path = root / ATTEMPTS_FILE
    if not path.is_file():
        return None
    failures: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        verdict, _, name = line.strip().partition(" ")
        if not name:
            continue
        if verdict == "PASS":
            failures[name] = 0
        elif verdict == "FAIL":
            failures[name] = failures.get(name, 0) + 1
    for name, count in failures.items():
        if count >= limit:
            return name
    return None


def attempt_limit(root: Path) -> int:
    for line in (root / "aios" / "config.yml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("stop_after_failed_attempts:"):
            try:
                return int(line.split(":", 1)[1].strip())
            except ValueError:
                return 3
    return 3


def session_tasks(root: Path) -> list[str]:
    path = root / SESSION_FILE
    if not path.is_file():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def approved(root: Path, task_id: str) -> bool:
    path = root / APPROVAL_FILE
    return path.is_file() and task_id in path.read_text(encoding="utf-8").split()


def autonomy_refusal(root: Path, task_path: Path, task_id: str) -> dict | None:
    """Stop the chain at the point the next task's first write would happen.

    The ledger records which tasks have begun, so "one task, then stop" is a count rather than
    a promise. A task already in the ledger is never re-refused: stopping mid-task would make
    the limit a limit on writes rather than on tasks, and the review surface it protects is
    measured in tasks.
    """
    started = session_tasks(root)
    if task_id in started:
        return None

    level, limit = autonomy_level(root, task_path)

    if level == "A0":
        # Approved, A0 becomes A1: one task, then the diff review, which is its second
        # checkpoint. Approval permits a task, not a chain.
        limit = 1
    if level == "A0" and not approved(root, task_id):
        return {"permission": "deny",
                "user_message": f"{task_id} is A0: a human approves the approach before "
                                f"implementation. Add {task_id} to {APPROVAL_FILE}.",
                "agent_message": f"Refused: {task_id} resolves to A0, which has two "
                                 f"checkpoints — the approach and then the diff. Propose the "
                                 f"approach and stop. Approval is recorded by a human in "
                                 f"{APPROVAL_FILE}; recording your own would make the "
                                 f"checkpoint a formality."}

    if len(started) >= limit:
        chain = ", ".join(started)
        return {"permission": "deny",
                "user_message": f"{level}: {limit} task(s) without review, and {chain} "
                                f"already ran. Stop and let the chain be reviewed.",
                "agent_message": f"Refused: {task_id} would be task {len(started) + 1} of an "
                                 f"unreviewed chain, and {level} permits {limit}. Present "
                                 f"{chain} for review; the chain resumes when {SESSION_FILE} "
                                 f"is cleared, which is a human's action because the point of "
                                 f"the limit is that someone has looked."}

    try:
        with (root / SESSION_FILE).open("a", encoding="utf-8") as handle:
            handle.write(task_id + "\n")
    except OSError:
        pass  # a ledger that cannot be written must not become a refusal
    return None


def lease_window(root: Path) -> float:
    for line in (root / "aios" / "config.yml").read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("write_lease_minutes:"):
            try:
                return float(line.split(":", 1)[1].strip()) * 60
            except ValueError:
                break
    return 120.0


def foreign_writer(root: Path, event: dict, now: float | None = None) -> str | None:
    """M4-11: two writing agents in one worktree are forbidden. Returns the other one's id.

    A lease, not a lock, because nothing signals that a session ended — a claim that outlives
    its holder turns a closed window into a repository nobody can write to, and people respond
    to that by deleting the control rather than waiting it out.

    What makes this subtle is measured rather than assumed. The only identity on the event is
    the *chat*, not the window, so "a different holder" is usually the same person in their
    next chat and not a second agent at all. The lease therefore refuses a takeover only while
    the current claim is still fresh. That leaves one gap, stated rather than hidden: an agent
    that pauses longer than the window can be displaced by a genuinely concurrent one, and
    this will not notice.

    Separate worktrees need no special case. Each has its own root and therefore its own
    lease, which is exactly the permission the rule grants them.
    """
    me = event.get("session_id") or event.get("conversation_id")
    if not me:
        return None  # no identity, no claim to make; enforcing on a guess is worse than not

    now = time.time() if now is None else now
    path = root / WRITER_FILE
    try:
        if path.is_file():
            holder, _, stamp = path.read_text(encoding="utf-8").strip().partition(" ")
            try:
                age = now - float(stamp)
            except ValueError:
                age = None
            # No lower bound on age. A claim stamped in the future is not corrupt, it is
            # fresher than now — a rounded stamp or a second's clock skew — and treating that
            # as expired would release the lease exactly when it is most certainly held.
            if holder and holder != me and age is not None and age < lease_window(root):
                return holder
        path.write_text(f"{me} {now:.3f}\n", encoding="utf-8")
    except OSError:
        return None  # a lease that cannot be written must not become a refusal
    return None


def permitted(path: Path, root: Path, patterns: list[str]) -> bool:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return False  # outside the repository entirely
    for pattern in patterns:
        if fnmatch.fnmatch(relative, pattern):
            return True
        # `aios/tasks/**` should cover `aios/tasks/T-1.md`, which fnmatch's `**` does not
        # match on its own because it does not treat `/` specially.
        if pattern.endswith("/**") and relative.startswith(pattern[:-2]):
            return True
    return False


def decide(event: dict) -> dict:
    if event.get("tool_name") not in WRITING_TOOLS:
        return ALLOW

    root = find_root(event)
    if root is None:
        return ALLOW  # not this repository; not this control's business

    # Before the mode check, and unlike it, this applies with no mode set. A mode is a choice
    # about how to work and defaults to unrestricted; one-writer-per-worktree is an invariant
    # about what the worktree can survive, and it is not less true on a fresh clone.
    other = foreign_writer(root, event)
    if other:
        return {"permission": "deny",
                "user_message": f"Another session ({other[:8]}) wrote here in the last "
                                f"{lease_window(root) / 60:.0f} minute(s). If it has stopped, "
                                f"delete {WRITER_FILE}.",
                "agent_message": f"Refused: session {other[:8]} holds the write lease on this "
                                 f"worktree. Two writing agents in one worktree is the case "
                                 f"where implicit decisions conflict and neither agent can "
                                 f"see the other's. Parallel work belongs in separate "
                                 f"worktrees on tasks with disjoint `touches`; reading in "
                                 f"parallel is unrestricted."}

    mode, task_id = active_mode(root)
    if mode is None:
        return ALLOW

    modes = load_config(root)
    if mode not in modes:
        return {"permission": "deny",
                "user_message": f"{MODE_FILE} names mode {mode!r}, which is not defined in "
                                f"aios/config.yml.",
                "agent_message": f"Mode {mode!r} is not defined. Known modes: "
                                 f"{', '.join(sorted(modes))}."}

    allowed = modes[mode]
    if allowed == "touches":
        path = task_file(root, task_id)
        if path is None:
            return {"permission": "deny",
                    "user_message": f"Mode 'implement' needs a task: write "
                                    f"'implement <task-id>' into {MODE_FILE}.",
                    "agent_message": "Mode 'implement' permits exactly the active task's "
                                     "declared `touches`, and no task is named."}
        if duplicate_check_missing(path):
            return {"permission": "deny",
                    "user_message": f"{task_id} has no duplicate_check. Search for what "
                                    f"already does this before writing it again.",
                    "agent_message": f"Refused: implementation may not begin until {task_id} "
                                     f"records a duplicate_check. Ask the explorer subagent "
                                     f"whether this already exists, then record what you "
                                     f"searched for and what you found — including 'nothing', "
                                     f"which is a complete answer. Writing it again without "
                                     f"looking is the failure this field exists to catch."}
        stuck = stuck_test(root, attempt_limit(root))
        if stuck:
            return {"permission": "deny",
                    "user_message": f"{stuck} has failed {attempt_limit(root)} times without "
                                    f"passing. Stop and report rather than trying again.",
                    "agent_message": f"Refused: {stuck} has failed {attempt_limit(root)} times "
                                     f"since it last passed. Past this the attempts are "
                                     f"guesses, and guessing next to a test is one step from "
                                     f"weakening it. Report what you have tried and what you "
                                     f"now believe is wrong — including the possibility that "
                                     f"the test is right and the task is wrong. Clearing "
                                     f"{ATTEMPTS_FILE} is a human's decision."}

        refusal = autonomy_refusal(root, path, task_id)
        if refusal:
            return refusal
        allowed = field_list(path, "touches") or []

    target = event.get("tool_input", {}).get("file_path", "")
    if not target:
        return ALLOW
    if permitted(Path(target), root, allowed):
        return ALLOW

    scope = ", ".join(allowed) if allowed else "nothing"
    return {"permission": "deny",
            "user_message": f"Mode '{mode}' may write to: {scope}.",
            "agent_message": f"Refused: mode '{mode}' does not permit writing "
                             f"{Path(target).name}. Its permitted set is {scope}. Change the "
                             f"mode deliberately, or change the task's `touches` — both are "
                             f"visible decisions, which is the point of the mode."}


def log_failure(stage: str, exc: BaseException) -> None:
    """Append a traceback beside the repository, best-effort and never raising.

    The hook's stderr goes nowhere a person can read: the editor reports an exit code and
    discards the rest. So a failure here has been invisible twice, and both times the visible
    symptom was every write refused with a number attached. A file is the only channel out.
    """
    try:
        import traceback
        root = Path(os.environ.get("CURSOR_PROJECT_DIR") or os.getcwd())
        with (root / ".aios-hook-error.log").open("a", encoding="utf-8") as handle:
            handle.write(f"--- check-mode {stage} at {time.time():.3f}\n")
            handle.write("".join(traceback.format_exception(exc)))
    except Exception:
        pass


def main() -> int:
    try:
        event = read_event()
    except Exception as exc:
        log_failure("read_event", exc)
        # A control that cannot read its input must say so rather than decide. Denying here
        # would repeat the incident; allowing silently would be a control that is absent
        # without anyone noticing, so it allows *and* reports.
        return respond.allow({}, f"check-mode could not read its input ({exc}); it allowed "
                                 f"this call and enforced nothing.")

    try:
        decision = decide(event)
    except Exception as exc:
        log_failure("decide", exc)
        # Same policy as unreadable input, for the same reason and one more. This hook is
        # registered failClosed, so an exception is not "the control did not apply" — it is
        # every write in the editor refused until someone reads a stack trace. That has
        # happened twice here already. A control that cannot decide reports that it could not,
        # and does not convert its own defect into an outage.
        return respond.allow(event, f"check-mode failed while deciding ({exc}); it allowed "
                                    f"this call and enforced nothing.")

    # Answering is its own failure mode, separate from deciding. Everything above this line was
    # already guarded; the reply was not, and a reply that raises is indistinguishable from a
    # control that refused — the editor reports an exit code either way.
    try:
        if decision.get("permission") == "deny":
            return respond.deny(event, decision["user_message"], decision["agent_message"])
        return respond.allow(event)
    except Exception as exc:
        log_failure("respond", exc)
        return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except BaseException as exc:
        # The last resort, and the one that matters. This hook is registered failClosed, so any
        # escape from here is not "the control did not apply" — it is every write in the editor
        # refused until somebody reads a stack trace that was never written down. Three
        # incidents in this repository have that shape.
        log_failure("toplevel", exc)
        raise SystemExit(0) from None
