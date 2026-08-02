# AI Engineering OS — Design Documents

This directory is the **engineering plan** requested in `plan.txt`. It is not the operating system itself; it is the argued design for it, written to be reviewed and challenged before a line of the OS is built.

## What this is

A reusable repository template that a team clones before starting a new software project. Every project cloned from it inherits an architecture, a documented state system, engineering standards, agent rules, and quality gates that work for both humans and AI coding agents.

The design targets a **tool-agnostic core** (`AGENTS.md`) with thin adapters for Cursor and Claude Code.

## Read in this order

| # | Document | What it settles |
|---|---|---|
| 00 | [Charter](00-charter.md) | Mission, non-goals, what changed versus `plan.txt`, and the honest answer to "how is this different from a README?" |
| 01 | [Evidence base](01-evidence-base.md) | The research findings that constrain the design, with citations. Read this before disagreeing with anything downstream. |
| 02 | [Principles](02-principles.md) | Eight principles derived from the evidence. Every later decision traces to one. |
| 03 | [Repository architecture](03-repository-architecture.md) | Folder hierarchy, the tool adapter layer, documentation architecture. |
| 04 | [State and tasks](04-state-and-tasks.md) | Project memory, requirements, the task schema, and the deterministic next-task algorithm. |
| 05 | [Workflows](05-workflows.md) | Human workflow, agent workflow, autonomy tiers, stop conditions, review budget. |
| 06 | [Quality gates and testing](06-quality-gates-and-testing.md) | Gate classes, project tiers, the halt policy, testing strategy. |
| 07 | [Security and agent containment](07-security-and-agent-containment.md) | Security model, supply chain, and defending the OS against its own agents. |
| 08 | [Standards, review, deployment](08-standards-review-deployment.md) | Engineering standards, code review, branching, release, production readiness. |
| 09 | [Maintenance and evolution](09-maintenance-and-evolution.md) | How the OS avoids rotting, and how it changes itself. |
| 10 | [Decision register](10-decision-register.md) | **Every** design decision with alternatives considered and trade-offs accepted. The other documents link here. |
| 11 | [Implementation roadmap](11-implementation-roadmap.md) | What to build, in what order, and what the first milestone proves. |

## The design in one paragraph

Prose instructions to an AI agent are advisory and degrade as they lengthen; deterministic mechanisms are guarantees. So this OS puts almost nothing in always-on instruction files and instead invests in three things a document cannot provide: **project state an agent cannot fake** (the next task is computed from per-task files, not from checkboxes the agent ticks itself), **memory hygiene enforced as a failing build** (size caps, staleness checks, broken-reference detection, orphan detection), and **quality gates the agent cannot edit** (the grader lives outside the agent's write scope and is protected by CODEOWNERS). The slogan is *facts, not procedures; gates, not guidelines; derived, not duplicated.*

## A note on the irony of this directory

The evidence in [01](01-evidence-base.md) is unambiguous that artifact volume exceeding review capacity is the dominant failure mode of every system in this space. This design set is eleven documents. That is deliberate and bounded:

- These are **design documents for a human reviewer**, produced once. They are not agent context and are never loaded into an agent's window.
- The OS they describe ships with an `AGENTS.md` budgeted at **≤150 lines**, enforced in CI.
- The per-project artifacts the OS asks a team to maintain are: one requirements file, one small file per task, and ADRs written only when a decision is architecturally significant. That is the entire mandatory surface.

If the OS ever generates more prose than the code it governs, it has failed, and [09](09-maintenance-and-evolution.md) specifies the mechanism for noticing and reversing that.
