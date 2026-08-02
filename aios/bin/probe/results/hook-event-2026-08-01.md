# Cursor `preToolUse` event shape, measured 2026-08-01

**Cursor version:** 3.13.21 · **Platform:** Windows · **Method:** a probe registered at
`.cursor/hooks.json` that recorded stdin verbatim and always allowed. Six firings across
`Shell`, `Read` and `Write`.

This is `M2-10`'s measurement and the prerequisite for `M4-03`. It was taken rather than read
from documentation, because building on the documented contract is what produced the
[fail-closed incident](../../../incidents/2026-07-31-fail-closed-hook-blocked-every-command.md).

## What arrives

On **stdin**, as one JSON object, terminated `\r\n`.

Top-level keys present on every firing:

```
conversation_id  generation_id  model      tool_name  tool_input  tool_use_id
session_id       hook_event_name           cwd*       cursor_version
workspace_roots  user_email     transcript_path
```

`cwd` is starred because it is **not always present**: it appeared on `Shell` firings and was
absent on `Read` and `Write`. A hook that reads a top-level `cwd` will work until it is asked
about a file operation. `CURSOR_PROJECT_DIR` is in the environment on every firing and is the
reliable source.

`tool_input` varies by tool, and this is the part a permission control reads:

| `tool_name` | `tool_input` keys |
|---|---|
| `Shell` | `command`, `cwd`, `timeout` |
| `Read` | `file_path` |
| `Write` | `file_path`, `content` |

**Creating a file and editing an existing one both arrive as `Write`.** They were issued
through two different tools and reported as one, which is convenient — a write control needs
one branch, not two — but it is also the kind of thing that could change, and the reason this
file records the version it was measured against.

Paths in `tool_input.file_path` are absolute, with a lowercase Windows drive letter.

## The finding that matters

**stdin is prefixed with a UTF-8 byte-order mark.** The probe's own `json.loads` on the raw
bytes returned nothing parseable, on a payload that is otherwise perfectly well-formed.

This is very likely what actually happened during `M2-08`. The incident recorded "the hook
received empty stdin", which was the symptom as observed from inside a hook whose parse had
thrown; a BOM on the front of the document produces exactly that appearance if the failure is
handled as "no usable input". A hook that then fails closed refuses everything, which is what
was seen.

The repository has met this before and already has the answer: `utf-8-sig`, used in
`render-review-packet.py` for the same reason. It is now used here, and the encoding gate
added after the mojibake incident exists because of the same class of fault.

## Consequences

- **`preToolUse` can refuse a write**, which is what `M4-03` needs and what
  [ADR-012](../../../../docs/decisions/ADR-012-command-denial-is-asymmetric-across-tools.md)
  did not consider — it examined command denial specifically, and concluded correctly about
  that. `preToolUse` is a broader event and covers `Write` and `Read` as well as `Shell`.
- **`preToolUse` also supersedes `beforeShellExecution`** for this repository's purposes: it
  sees `Shell` firings with the same `command` field, so the deny list in
  `tests/test_deny_commands.py` can be wired through one hook instead of two.
- **The interpreter question (`Q-005`) is answered for this machine and not in general.**
  `python` works here; `python3` does not. Nothing measured here makes that portable, and the
  answer remains the one ADR-006 gives: ship it as a binary subcommand and name no interpreter.

## The post-execution events, measured the same day for `M4-06`

`M4-06` needs to know whether a test *failed*, which is an outcome, and `preToolUse` fires
before anything runs. Both post-execution events were probed with a deliberately failing
command.

| | `afterShellExecution` | `postToolUse` |
|---|---|---|
| command text | `command` | `tool_input.command` |
| output | `output` (plain string) | `tool_output` (JSON string) |
| exit code | **absent** | inside `tool_output` |
| also | `duration`, `sandbox` | `duration`, `cwd`, `tool_name`, `tool_use_id` |

So **only `postToolUse` can see whether something failed**, and only by parsing `tool_output`,
which arrives as a JSON *string* of the form `{"output": "...", "exitCode": 0}` — a second
decode inside the first.

**The exit code is the shell's, not the command's.** The probe ran a Python process that
exited 1, inside a PowerShell block whose last statement was a string, and `exitCode` was `0`.
That is not a bug in the event; it is what the shell returned. Anything reading this field to
decide whether a test passed will be wrong whenever the command is wrapped, which on this
machine is most of the time. A detector must therefore read the *output text* for the test
runner's own verdict and treat a non-zero exit as corroboration rather than as the signal.

## A registration change takes effect a turn late

Saving `hooks.json` does not arm the change for the command that follows it. Measured: a newly
registered hook did not fire on the next tool call, and did fire on the one after. An
unconditional tracer registered one call later did not fire at all while an entry registered
two calls earlier fired normally.

This cost a wrong conclusion before it was understood. A `matcher: "Shell"` on `postToolUse`
appeared not to work, was removed, appeared still not to work, and was then found to work
correctly once given a settling turn — the matcher had never been the problem. **Test a hook
registration across at least two tool calls before concluding anything about it**, which is
the same settling period M0 found for skill and subagent indexing, in a different subsystem.

## Exit code 2 does not deny in Cursor, though the documentation says it does

`M4-07` wanted one hook script registered in both tools, and the obstacle is the response
shape: Cursor accepts `{"permission": "deny"}` on stdout, Claude Code signals a block with
exit code 2 and a message on stderr. Cursor's documentation also lists exit code 2 as
blocking, which would have made one mechanism serve both.

It does not. A probe registered on `preToolUse`, matched to `Write`, fired on its sentinel
file, wrote to stderr, and exited 2 — **and the write completed**. The hook ran, its refusal
was ignored, and the log it left proves the firing rather than leaving the result ambiguous.

| | deny in Cursor | deny in Claude Code |
|---|---|---|
| `{"permission": "deny"}` on stdout | **measured, works** | not applicable |
| exit code 2 + stderr | **measured, ignored** | documented, unmeasured here |

So there is no portable response, and a shared hook has to branch. The discriminator is
`cursor_version`, present on every Cursor event measured and absent from Claude Code's
documented payload. `M4-07` is built on that branch rather than on a shared mechanism that
does not exist.

This is the fifth time a documented tool behaviour has not survived contact — after PowerShell
execution policy, nested `AGENTS.md` discovery, the toolchain's reachability, and the hook
input contract. The pattern is not that documentation is bad; it is that this repository's
design keeps depending on details thin enough to be wrong, and the only defence that has ever
worked is spending ten minutes measuring.

## Re-measure when

Cursor updates. The version is recorded above precisely so that a mismatch is visible rather
than assumed away, and `S-01`'s quarterly re-run covers it.

## `session_id` is the chat, not the window (M4-11)

The one-writer-per-worktree rule needs an identity for "a writing agent". The event carries
both `session_id` and `conversation_id`, and M0 recorded only that both exist.

Measured across consecutive `Write` firings in one chat:

```
session=9194e8c2-6de7-449b-9af9-a9729d298b32 conversation=9194e8c2-6de7-449b-9af9-a9729d298b32
```

**They hold the same value**, it is stable across turns, and it is the UUID of this chat's
transcript file. `generation_id` changes per turn, so it identifies a turn rather than an
agent.

The consequence is the one that would have been guessed wrong. A window is not a session:
starting a new chat in the same folder produces a new `session_id` with no signal that the
previous one ended. A write lease keyed on this field therefore cannot treat "a different
holder" as "a second concurrent agent" — most of the time it is the same person, in the next
chat, five minutes later.

So the lease refuses a takeover only while the current claim is **fresh**, and the freshness
window has to sit between two intervals rather than being chosen for comfort: longer than the
gap between one agent's consecutive writes, shorter than the gap between one working session
and the next. Two minutes. The residual gap is stated rather than hidden — an agent that
pauses longer than the window can be displaced by a genuinely concurrent one, and this
mechanism will not notice.
## Who closes the pipe (measured 2026-08-02, during M5-01)

The payload was recorded here as "one JSON object, BOM-prefixed, CRLF-terminated". Terminated
is not closed, and the difference is the whole of three incidents.

`sys.stdin.buffer.read()` waits for end-of-stream. Given a caller that writes the line and
holds the pipe open, it waits forever. Measured side by side on identical input:

| read | result |
|---|---|
| `read()` | still running after 4s |
| `readline()` | returned in 0.3s |

A hook registered `failClosed` that hangs is every write in the editor refused when the
timeout fires, reported as an exit code — a truthful description of the process and a
misleading description of the fault, since nothing crashed. Both hooks now read a line.

The lesson is not about stdin. This line was measured once, written down, and treated as
settled; the half that was never measured was who closes the stream, and it took a day across
three incidents to look at it.