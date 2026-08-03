# AI Engineering OS

A repository template, plus a small binary, for running a software project with coding agents
as a normal part of the team. Project state — requirements, tasks, decisions, incidents —
lives in plain Markdown that both a human and an agent can read. What the project actually
depends on is enforced by gates that run where the agent cannot reach them.

The premise is that an agent applies facts reliably and follows written procedure
unreliably, so the system is built out of facts and checks rather than instructions and good
intentions.

## Status: early, and not yet tried on anything

The `aios` binary builds and ships. `v0.1.0` produced four platform binaries, deleted the Rust
toolchain from the runner and refused to continue until it was gone, then called the shipped
binary from a dependency-free project in another ecosystem — which is the claim this design
lives or dies on. There is still no quickstart, because a quickstart is a promise about
stability nothing here has earned. A check keeps this section honest: every command this file
displays has to be one that CI executes.

What the binary can do is read the project's state, refuse it when it is malformed, select the
next task deterministically, and move a task to `done` only after re-running its verification
commands. What it cannot do yet is own the gate logic, which still runs as inline steps in CI.

There is no bootstrap plan any more. It was a hand-written checklist for building the thing
meant to replace it, and it retired into `aios/tasks/` once the binary could select its own
next task — which is the condition it was written to be deleted on. What is open is what the
state directory says is open.

## What is here now

| Path | What it is |
|---|---|
| `docs/design/` | The design set: why the system is shaped this way. Twelve documents, written before any code. |
| `docs/decisions/` | ADRs. Immutable once accepted; a reversal is a new one that links back. |
| `aios/open-questions.md` | Known unknowns, each with a closing condition and a deadline. |
| `aios/incidents/` | Failures, each recorded with the control it produced. |
| `aios/bin/probe/results/` | Measurements of what coding tools actually load, which several decisions rest on. |
| `AGENTS.md` | The always-on context an agent gets on every turn, under a line budget. |
| `.github/workflows/hygiene.yml` | The gates that exist so far. |

## Reading order

Start with `docs/design/00-charter.md` for what the system is for, then
`docs/design/02-principles.md` for the eight principles every decision cites. If you only
read one thing after that, read `docs/design/01-evidence-base.md` — it is the evidence the
principles compress, and the rest of the design is downstream of it.

`docs/decisions/` is worth skimming in numerical order. Several of those ADRs correct the
design set rather than implement it, because the measurements in `aios/bin/probe/results/`
contradicted assumptions the design had made.

## A note on the stack

This repository chose Rust for its own reference implementation, and the reasoning is in
`docs/decisions/ADR-005-reference-implementation-ecosystem.md`. That choice binds this
repository only. A project cloned from the template picks its own ecosystem from its own
requirements; there is no default and no recommendation.
