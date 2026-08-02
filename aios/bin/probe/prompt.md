# Adapter probe — protocols and recording sheet

Used by `M0-02` through `M0-04`, and by the quarterly re-run in `S-01`. A run is three steps:

```
python aios/bin/probe/probe-adapters.py stage
```

then the three protocols below, from **fresh sessions**, then:

```
python aios/bin/probe/probe-adapters.py teardown
```

Staging generates fresh markers, writes them into every measured location, and records
`.aios-probe.json` — which is what teardown restores from, and why a run must be torn down
before another is staged.

The marker files sit at the **repository root**, which is the directory the tool treats as its
project. Probing a subdirectory measures nothing: tool discovery is anchored at its own root.
The `M0` run had a caveat here because the workspace root and the repository root were not yet
the same directory; `M1-01` settled that and the caveat is closed.

`.ps1` files cannot execute in this environment at all — see
[ADR-006](../../../docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md), which was written
because this document originally called one. The script above is provisional and becomes the
`aios probe-adapters` subcommand at `M1-08`; the interpreter it names is this machine's, not a
portable one (`Q-005`).

---

## Why there are three protocols

A single "repeat the marker" question conflates two very different answers. A location whose
contents sit in the system prompt on every turn is **always-on context** and spends the budget
that [P4](../../../docs/design/02-principles.md) exists to protect. A location loaded only
when something invokes it is **pull-only** and costs nothing until used — which is exactly the
progressive disclosure [05 §3.1](../../../docs/design/05-workflows.md) depends on.

Both would score "yes" on a naive probe, and the adapter design needs to tell them apart. So the
matrix records four values, not two:

| Value | Meaning |
|---|---|
| `always` | Surfaced under Protocol A, with no tool use |
| `scoped` | Surfaced only when working inside the governed path (Protocol B) |
| `on-demand` | Surfaced only after explicit invocation (Protocol C) |
| `no` | Did not surface under any protocol |

`.claude/commands/`, `.claude/agents/`, and skill *bodies* are expected to be `on-demand` and
that is not a failure — it is the finding. Skill and subagent *descriptions* are expected to be
`always`, which is why each carries a separate marker from its body.

---

## The question

Paste verbatim. The no-tools clause is the whole control: an agent with search can find any
marker on disk, which would measure the filesystem rather than the discovery mechanism.

> Answer from your loaded context only.
>
> Do NOT use any tool. Do not read files, search, grep, or list directories. If you cannot
> answer without a tool, the correct answer is NONE.
>
> Some files in this workspace contain a marker shaped `AIOS-PROBE-<LABEL>-<8 hex characters>`.
> For each label below, report the full marker if it appears anywhere in the instructions or
> context you were given, or `NONE` if it does not.
>
> ROOTMD · NESTED · CURSORALWAYS · CURSORGLOB · CLAUDEAGENTDESC · CLAUDEAGENTBODY ·
> CLAUDESKILLDESC · CLAUDESKILLBODY · CLAUDECMD · DECOY
>
> Output one line per label, in exactly this form, and nothing else:
>
> `<LABEL>: <full marker or NONE>`

**DECOY has no file.** Any marker reported for it means the tool fabricated a plausible-looking
answer, and the entire run is void — re-run with fresh markers. This is the control that keeps a
null result trustworthy.

---

## Who may answer

**Not the agent that staged the probe.** A fresh session is necessary and not sufficient: an
observer that wrote the marker files cannot distinguish reading them from remembering writing
them, and the decoy control does not catch that — the decoy detects invention, not recall.

Its *absences* remain usable, since an author cannot fabricate a location failing to appear. Its
positives are not. Record any such observation as provisional and outside the matrix.

## Protocol A — passive, from the workspace root

Fresh session. No file open, or a file at the root. Ask the question, change nothing else.

Establishes what is **always-on**. Everything scoring `always` here is spending context budget on
every single turn, which is the number `M1-02` has to live within.

## Protocol B — passive, working inside `probe-nested/`

Fresh session. Open `probe-nested/probe-target.txt` and ask the agent to make a trivial edit to
it, then ask the question.

Establishes **path scoping**, and this is the one that gates the adapter design. `M0-04` needs
two results, not one:

- `NESTED` surfaces here but **not** under Protocol A → nested `AGENTS.md` scoping works.
- `NESTED` surfaces under both → the file is always-on, so nesting is not scoping anything and
  the budget is larger than it appears.
- `NESTED` surfaces under neither → nesting does not work in this tool.

`CURSORGLOB` is the same test for Cursor's own glob mechanism, and exists so that a nested
`AGENTS.md` failure can be told apart from path scoping failing generally.

## Protocol C — on-demand

Fresh session per invocation. In each case ask the question *afterwards*, in the same turn:

1. Invoke the `/aios-probe` slash command.
2. Invoke the `aios-probe` subagent.
3. Trigger the `aios-probe` skill.

Establishes which locations are pull-only. A location scoring `on-demand` is safe to put content
in without budget cost, and is where anything large belongs.

---

## Recording sheet

Copy into `probe/results/probe-<YYYY-MM-DD>.md` and commit. **Record both tool versions** — a
matrix without them cannot be compared against the next quarterly run, which makes it worthless
for its actual purpose.

```markdown
# Adapter discovery matrix — <YYYY-MM-DD>

Run ID: <from the manifest>
Cursor: <version>   Claude Code: <version>
Decoy clean: <yes / NO — run void>

| Location | Marker label | Cursor | Claude Code |
|---|---|---|---|
| Root `AGENTS.md` | ROOTMD | | |
| Nested `AGENTS.md` | NESTED | | |
| `.cursor/rules/` alwaysApply | CURSORALWAYS | | |
| `.cursor/rules/` glob-scoped | CURSORGLOB | | |
| `.claude/agents/` description | CLAUDEAGENTDESC | | |
| `.claude/agents/` body | CLAUDEAGENTBODY | | |
| `.claude/skills/` description | CLAUDESKILLDESC | | |
| `.claude/skills/` body | CLAUDESKILLBODY | | |
| `.claude/commands/` | CLAUDECMD | | |

## Consequences for the adapter layer

<Which locations are always-on, and therefore in scope for the budget.>
<Whether nested AGENTS.md scoping works in both tools — the D-001 gate.>
<Anything that must change in 03 §3 as a result.>
```

---

## Confounds to rule out before recording a `no`

A null result has two causes and they are not the same finding. Before writing `no`, check:

1. **Wrong file format.** These schemas are undocumented and change between releases. Confirm the
   tool lists the skill, subagent, or command as available at all. If it does not, the finding is
   "format rejected", not "location not read" — fix the format and re-run.
2. **Stale session.** Most discovery happens at session start. A file written mid-session may
   legitimately not appear. Every protocol says *fresh session* for this reason.
3. **Context eviction.** On a long session an early-loaded marker can fall out. Ask the question
   as the first turn.

---

## Teardown

```
python aios/bin/probe/probe-adapters.py teardown
```

Removal is no longer unconditional and cannot be. When `M0` ran, every path the probe touched
was its own — `AGENTS.md`, `.claude/` and `.cursor/rules/` did not exist yet, so deleting them
outright was safe. All three are real now, and two are always-on context. The manifest
therefore records, per path, whether the file pre-existed and its exact bytes if it did;
teardown restores those bytes and verifies the hash, and exits non-zero if anything does not
come back to what it was.

That check is the point. A leftover marker in the real instruction file is the exact class of
silent staleness this project exists to catch, and a teardown that reports success while
leaving one behind poisons the next run as well.

`probe-adapters.py status` lists what is currently staged. While a run is staged the repository
is deliberately not committable: the probe adds always-on context, so that ratchet reads high
on purpose. Commit the results file, never the probe.
