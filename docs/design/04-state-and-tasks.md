# 04 — Project state, memory, and task management

The core claim of this design is that **an agent must not be able to assert progress**. Progress is computed. This document specifies the data model that makes that true, and the failure modes it is built against.

---

## 1. The two-level model

```
Requirement  (AUTH-7)   — what the system must do, and why. Stable. Human-owned.
    └── Task (T-a3f8)   — one reviewable change. Volatile. Agent-executed.
```

Two levels, plus an optional `parent` pointer on a task for the rare case where a natural grouping helps a human read the backlog. No epics, no features, no stories, no subtasks.

**Why the middle layers are gone.** Every intermediate level in a work hierarchy exists to coordinate people across an organisational boundary — a team, a quarter, a roadmap review. In a loop of one human and one agent, none of those boundaries exist, but each level still has to be *created*, *kept consistent*, and *decided about* by the agent, and each is somewhere the agent can be wrong in a way a human then has to notice. Kiro's field evaluation ([01: 4.1]) shows the specific pathology: a bug fix expands into four user stories and sixteen acceptance criteria because the schema has slots and the agent fills them.

The cost is real: with a large backlog, two levels give a flat list of many tasks under one requirement. The mitigation is that tasks for *future* slices are not created at all (P7), so the flat list only ever holds the current slice, and `parent` provides grouping when it genuinely helps.

---

## 2. Requirements

One file per capability area, e.g. `aios/requirements/auth.md`, holding several requirements. Area files rather than one-file-per-requirement because requirements are read as a set ("what does auth need to do?"), churn rarely, and one file per requirement produces a directory of hundreds of six-line files that no human ever reads end to end. Area files rather than a single `requirements.md` because a 1,500-line file cannot be loaded into agent context selectively and every addition contends for the same merge region.

### 2.1 Format

```markdown
## AUTH-7 — Session expiry

**Status:** active
**Rationale:** Regulated tier requires idle-session termination (see incidents/2026-03-11-stale-session.md).

When a session has been idle for 30 minutes, the system shall invalidate the session token
and return 401 with `code=SESSION_EXPIRED` on the next request.

While a session is within 5 minutes of expiry, the system shall include
`X-Session-Expires-In` on every response.

**Out of scope:** refresh tokens (see SEARCH of open-questions.md#refresh-tokens).
```

Requirement bodies use **EARS** ([01: 4.6]) — `When <trigger>, the system shall <response>`, `If <condition>, then the system shall…`, `While <state>, the system shall…`, `Where <feature is included>…`, and unconditional `The system shall…`. This is a formatting constraint, not a framework. It buys three things: ambiguity becomes visible, each clause maps to one test, and a linter can flag requirements that match none of the templates or that contain weasel words (`fast`, `user-friendly`, `appropriate`, `etc.`).

The linter warns rather than blocks, because a requirement that resists EARS is usually a signal about the requirement rather than about the author, and blocking here would push people to write template-shaped nonsense.

### 2.2 IDs

`<AREA>-<n>`: `AUTH-7`, `SEARCH-2`. Human-quotable in conversation, in commit messages, and in test names, which is the whole point — an ID nobody can say out loud does not get used.

The trade-off is that two branches adding to the same area can both claim `AUTH-8`. CI enforces global uniqueness and the fix is a rename, which is cheap while a requirement is new and expensive later. Hash IDs would eliminate the conflict entirely and were rejected because unreadable requirement IDs are a daily cost paid to avoid an occasional one ([10](10-decision-register.md#d-011)). Tasks make the opposite trade for the opposite reason.

### 2.3 Status

`active` · `deferred` (agreed, not now — must carry a reason) · `superseded-by: <ID>` · `dropped` (must carry a reason). Requirements are never deleted; the record of what was once wanted is exactly the memory this system exists to keep.

---

## 3. Tasks

One file per task at `aios/tasks/T-<id>.md`. On completion the file moves to `aios/tasks/done/YYYY-MM/`, keeping the active directory small enough that a glob over it stays cheap.

### 3.1 Schema

```markdown
---
id: T-a3f8
title: Add /search endpoint returning ranked task matches
status: todo
satisfies: [SEARCH-2, SEARCH-4]
priority: 2
risk: low
blocked_by: [T-b7c2]
touches:
  - src/api/search.ts
  - src/api/search.test.ts
  - src/index.ts
acceptance:
  - "When GET /search?q=<term> is called, the system shall return 200 with results ordered by descending relevance"
  - "If q is absent or empty, then the system shall return 400 with code=MISSING_QUERY"
  - "p95 latency < 150ms against the 10k-task fixture"
verify:
  - pnpm test src/api/search.test.ts
  - pnpm bench:search --fixture=10k --p95=150
constraints:
  - "Use the existing SQLite FTS5 index (ADR-007). Do not add a search dependency."
  - "Typo tolerance is out of scope; tracked in open-questions.md#fuzzy-search."
---

## Context
SEARCH-2 needs free-text lookup. The FTS index is built during migration, so a green
unit suite alone does not prove this works — see T-b7c2.
```

The concrete commands and paths above belong to one hypothetical project and are illustrative only. `verify` holds whatever the project's own toolchain runs; nothing in the schema knows or cares which ecosystem that is ([D-041](10-decision-register.md#d-041--no-presumed-stack-the-ecosystem-is-derived-from-the-project)).

Field-by-field justification, since every field is a cost:

| Field | Why it exists | Why not more |
|---|---|---|
| `id` | Stable reference from commits, branches, tests | — |
| `title` | Human scanning | — |
| `status` | The state machine (§3.3) | — |
| `satisfies` | **The anti-invention control.** A task satisfying no live requirement fails validation ([01: 6.4]) | — |
| `priority` | Small ordinal (1–3), human-set, drives ordering | Not a score; no RICE, no WSJF (P8) |
| `risk` | `low`/`medium`/`high`; **selects the autonomy tier** in [05](05-workflows.md) | Earns its place only because it changes system behaviour |
| `blocked_by` | The dependency graph `next` walks | — |
| `touches` | Declared write scope; CI fails a diff that escapes it | The single most useful field for review, see §3.5 |
| `acceptance` | EARS-shaped, one per test | — |
| `verify` | Commands that must exit zero before `done` | Free-text "definition of done" was rejected; it cannot be executed |
| `constraints` | No-gos and known rabbit holes | Narrow and task-specific; general rules live in standards |

Deliberately absent: estimate, story points, complexity, effort, assignee, sprint, epic, labels, tags, due date. Each was considered and cut ([01: 6.2], P8). `assignee` in particular is noise in a one-human-one-agent loop and becomes a lie the moment it is stale.

A task file is capped at **60 lines** by a CI check. A task needing more than that is two tasks, or its context belongs in a requirement or an ADR.

### 3.2 IDs

`T-` plus four hex characters derived from a hash of title and creation timestamp. Four characters is 65,536 values, so a birthday collision is likely (~26%) by 200 tasks — the generator therefore checks the existing directory and extends to six characters on collision, and CI enforces uniqueness. Hash-based rather than sequential because sequential IDs conflict on every parallel branch and renumbering breaks every reference already written into commits and test names.

### 3.3 States

Six, and no more:

```
todo ──► doing ──► review ──► done
  │        │          │
  │        └──────────┴──► waiting  (external blocker; requires waiting_on)
  └──────────────────────► dropped  (requires reason)
```

`blocked` is **not** a state, because blockage by another task is derivable from `blocked_by` and derived state that is also stored is state that can disagree with itself (P3). `waiting` exists only for blockers *outside* the repository — a vendor, an access request, a human decision — which nothing can derive.

Transitions are performed by `aios/bin` commands (`aios start`, `aios submit`, `aios done`) rather than by hand-editing frontmatter, so that every transition is validated. The CLI is not a convenience wrapper; it is the schema's enforcement point.

### 3.4 `done` cannot be self-declared

This is the mechanism the whole design hangs on.

`aios done T-a3f8` runs every command in `verify`, and refuses if any exits non-zero. It then writes a verification record — commit SHA, command list, exit codes, timestamp — into the task file.

An agent could of course just edit the frontmatter and skip the CLI. So CI independently validates: for every task marked `done`, the recorded SHA must exist, the recorded commands must match the task's `verify` list, and those commands must pass at that SHA. Faking completion therefore requires forging a CI run, which is outside the agent's reach given the CODEOWNERS protections in [07](07-security-and-agent-containment.md).

This is the difference between this design and every checklist-based tracker surveyed ([01: 4.2]). It is not that agents are asked more firmly to update state. It is that the state they can write is not the state anyone reads.

### 3.5 `touches` and scope escape

The declared file set is checked against the actual diff. A change outside it fails the build with a message telling the agent to amend the task file.

The point is not to prevent the agent from touching other files — often it must. The point is that expanding scope becomes an **explicit, reviewable edit to the task file**, visible in the same PR, instead of an unremarked extra hunk in a 400-line diff. Reviewers reliably miss the latter and reliably notice the former. This is P6 applied: the mechanism spends the agent's effort to save the reviewer's attention.

Globs are permitted (`src/api/**`), and the CI message reports how much of the declared scope went unused, which surfaces tasks that were scoped lazily as `src/**`.

---

## 4. `aios next` — the deterministic selector

```
1. candidates ← tasks where status == todo
2. drop any whose blocked_by contains a task not in {done, dropped}
3. drop any whose satisfies does not resolve to ≥1 requirement with status: active
     (this is a hard error, not a skip — it means the backlog is invalid)
4. sort by, in order:
     a. priority ascending
     b. number of todo tasks this one unblocks, descending
     c. risk rank: low < medium < high
     d. created_at ascending
     e. id lexicographic ascending          ← guarantees a total order
5. return head, or "no ready task" plus the reason each blocked task is blocked
```

Tie-break (e) exists so the function is total: identical repository state always yields an identical answer, on any machine, with no clock or randomness involved. That property is what lets a human trust the answer without re-deriving it.

Rule (b) — prefer the task that unblocks the most others — is the only piece of scheduling intelligence in the algorithm, and it is a pure function of the graph rather than a judgement.

`aios next` **refuses to return a task** when:
- review debt exceeds the configured limit ([05](05-workflows.md#the-review-fatigue-problem));
- an incident is open with `blocks_work: true`;
- backlog validation fails (a dangling `blocked_by`, an unresolvable `satisfies`, a duplicate ID).

Refusing is the correct behaviour: an agent should be stopped by a broken plan, not routed around it.

### 4.1 Derived views

`backlog`, `in progress`, and `completed` are **queries**, not files (`aios list --status=todo`). `plan.txt` proposed them as three markdown files; that design makes every status change a two-file edit — a delete from one and an append to another — which is a merge conflict on every parallel branch and is exactly the aggregate-file failure documented in [01: 4.3], including the incident where a text merge silently destroyed 1,115 records while leaving a valid file behind.

If a human wants a rendered board, `aios board > BOARD.md` generates one, gitignored, regenerated on demand. A generated view can be wrong for a moment; a stored one can be wrong forever.

---

## 5. Traceability

```
Requirement ──satisfies── Task ──touches── Code ──@satisfies── Test
```

Tests carry a tag naming the requirement they verify (`@satisfies AUTH-7` in a docstring, test name, or annotation, depending on ecosystem). A generated coverage map then answers three questions no framework surveyed answers:

- **Which requirements have no test?** A gap in verification.
- **Which tests trace to no requirement?** Either an undocumented requirement or a test for behaviour nobody asked for.
- **Which requirements have no task and are not `deferred`?** Work that has been forgotten rather than decided against.

All three are reported, none block by default, and the first becomes blocking at `regulated` tier. They are reported rather than blocking because in each case the right fix is sometimes to change the requirement, and a gate that presumes the code is wrong will train people to satisfy it dishonestly.

---

## 6. Memory hygiene as a build failure

Every memory system surveyed degrades the same way: bloat, staleness, and internal contradiction, mitigated by asking the agent nicely to keep things tidy. Per P2 that is a preference, not a control. The checks (all in CI):

| Check | Failure mode it prevents |
|---|---|
| `AGENTS.md` ≤ budget (default 150 lines) | Instruction-adherence collapse ([01: 2.2]) |
| Task file ≤ 60 lines | Tasks growing into specs |
| Every path named in an instruction or standards file exists | The commonest form of silent staleness |
| Every `enforced_by` resolves to a live lint rule | Standards outliving their enforcement |
| Every `blocked_by` / `satisfies` / ADR link resolves | Dangling graph |
| No duplicate IDs | — |
| Dated docs past their review date | Narrative rot ([03](03-repository-architecture.md#41-the-classification-rule)) |
| `AGENTS.md` shrank or held steady over the last N commits | Ratchet against monotonic growth |
| Requirement/test orphan report | Untraced work in both directions |

The last one is worth dwelling on. Most systems can only add rules. A budget plus a ratchet is what makes it possible for the instruction surface to *shrink*, and shrinking is the only defence against the slow accumulation that makes every one of these systems worse in month six than in month one.

---

## 7. The CLI surface

Small, because a large one is another thing to remember:

```
aios next                 # the deterministic selector, with reasons when empty
aios start   <id>         # todo → doing, records branch + start time
aios submit  <id>         # doing → review, runs verify locally, invokes the verifier subagent
aios done    <id>         # review → done, requires CI verification record
aios new task|req         # scaffolds a valid file, allocates an ID
aios list    [--filters]  # derived views
aios check                # every hygiene + validation check, same as CI
aios board                # rendered board to stdout
aios probe-adapters       # §3.5 of doc 03
```

`aios check` running locally exactly what CI runs is not a nicety. A gate whose local and remote behaviour differ is a gate people learn to ignore until the PR turns red, which converts every check into late feedback and undoes the fast-feedback capability that DORA identifies as the thing making AI adoption net-positive ([01: 1.1]).

The language the CLI is written in is **not decided here**, and is not decided by default ([D-041](10-decision-register.md#d-041--no-presumed-stack-the-ecosystem-is-derived-from-the-project)). It is chosen once the first project's requirements and ecosystem are known, against four constraints: it must run identically under PowerShell — the target environment — which rules out shell-script-only implementations; it must be installable without a global install, using whatever the host ecosystem's equivalent of `npx` is; it must be present on a machine that already builds the host project, so the OS does not impose a second runtime; and every gate script under `aios/bin/` must be reachable from it. Any ecosystem meeting those four is admissible, and picking one before there is a project to pick it for would be a decision made on nothing.
