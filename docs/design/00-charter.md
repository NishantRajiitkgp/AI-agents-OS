# 00 — Charter

## The problem this exists to solve

AI coding agents are now fast enough that the bottleneck has moved. It is no longer writing code; it is reviewing code, preserving intent across sessions, and preventing a codebase from silently drifting away from its own design. Google's DORA programme measured the shape of this precisely: as of the 2025 report, AI adoption correlates **positively** with delivery throughput and **negatively** with delivery stability. Their causal reading is the thesis of this project:

> "AI accelerates software development, but that acceleration can expose weaknesses downstream. Without robust control systems, like strong automated testing, mature version control practices, and fast feedback loops, an increase in change volume leads to instability."

The seven capabilities DORA identifies as flipping that sign — internal platform quality, AI-accessible internal data, a clear AI stance, user-centricity, **small batches**, **strong version control practices**, and trust — are almost entirely things a repository template can install on day one.

That is the justification for this project. Not "AI needs more documentation." The opposite: **AI needs control systems, and control systems can be pre-installed.**

## What we are building

A repository template. Clone it, add requirements, and you get:

1. A **project state system** from which the next implementation step is computed deterministically, so an agent never invents work.
2. **Quality gates** that run outside the agent's reach and block on things that are binary and harmful.
3. A **memory system** whose staleness, bloat, and internal contradictions are caught by a failing build rather than by hoping someone notices.
4. A **minimal instruction layer** (`AGENTS.md` plus path-scoped rules) that carries only what an agent cannot derive by reading the code.
5. **Thin adapters** so the same core works in Cursor and Claude Code without duplicated content.

## What we are explicitly not building

These are non-goals in the strict sense — things that could reasonably be goals, considered, and declined.

**Not a spec-driven development framework.** GitHub Spec Kit, Kiro, and BMAD all front-load large specification artifacts. The measured results are poor: ~10× slowdown and 2,500 lines of markdown for one production feature (Scott Logic), one bug fix expanded into 4 user stories and 16 acceptance criteria (Böckeler on Kiro), a documented review-quota rule in BMAD that forces reviewers to manufacture at least three findings per review. We take specific mechanisms from these tools and reject their central premise.

**Not a multi-agent org chart.** No PM agent, no architect agent, no QA persona. The evidence against role-play is strong and is laid out in [01](01-evidence-base.md#roles-are-theatre-for-objective-tasks). We use exactly two subagents, both for context isolation rather than for role: one that explores read-only, one that verifies a concrete diff in a fresh context.

**Not a replacement for host-tool features.** Agent OS deleted its own spec-writing commands in v3 and now defers to native plan mode. SuperClaude's own gap analysis lists native skills, hooks, and plan mode as things it must migrate toward. Anything we build that duplicates plan mode, skills, or hooks will be dead weight within two releases. We build only what the tools do not.

**Not a methodology with ceremonies.** No sprint cadence, no retrospective ritual, no definition-of-ready negotiation, no story points. Each of those is a human coordination device for boundaries that do not exist in a one-human-one-agent loop, and each has a documented cost. Where the *artifact* a ceremony produces is valuable (a postmortem, a decision record), we keep the artifact and drop the ceremony.

**Not a stack.** The OS presumes no language, runtime, package manager, test runner, or formatter, and ships no default one ([D-041](10-decision-register.md#d-041--no-presumed-stack-the-ecosystem-is-derived-from-the-project)). Those are properties of a project, derived from its requirements and recorded as ADRs when chosen. What the OS supplies is the shape of the controls — a declared write scope, a verification record, a ratchet — and each project fills in the commands. Where these documents need a concrete command to make a point, it is an illustration from a hypothetical project, not a recommendation.

**Not a scoring system.** No technical debt score, no RICE, no WSJF, no complexity estimate. Google tested 117 candidate metrics as leading indicators of technical debt and explained under 1% of variance. Story points show approximately zero correlation with actual duration. A number nobody can produce honestly is worse than no number, because it invites decisions.

## The novelty question, answered directly

Critics of Spec Kit ask the obvious question, and it applies here: *how is this different from a repo with a good README, an `AGENTS.md`, and some subagents?*

Three things, none of which any system surveyed provides:

**1. The next task cannot be faked.** Every markdown-checklist tracker studied has documented drift — Kiro issue #6826 records a 24-task project where checkboxes were never ticked and `tasks.md` became unreliable as a handoff document. In this design, status lives in per-task frontmatter, readiness is computed from the dependency graph, and `done` is conditional on a verification command exiting zero in CI. An agent that forgets to update state does not corrupt the plan; it simply fails to advance.

**2. Memory hygiene is a red build, not a good intention.** The failure mode of every memory-bank system is drift, bloat, and contradiction, and the standard mitigation is a note in the instructions asking the agent to keep things tidy. We make it mechanical: `AGENTS.md` over its line budget fails CI; a standards file referencing a deleted symbol fails CI; a task whose diff escaped its declared file set fails CI; a test that traces to no requirement is reported as an orphan.

**3. The grader is not editable by the graded.** This is the control the reward-hacking evidence demands and that no surveyed framework implements. Test files, CI workflows, gate configuration, and lint config sit outside the agent's write scope and behind CODEOWNERS. A diff audit looks for the specific published test-weakening patterns. Without this, everything else is advisory.

If someone shows that a plain README plus native plan mode achieves those three properties, this project should be cancelled. It does not, and that is the whole gap.

## What changed relative to `plan.txt`

`plan.txt` asked to be argued with. Here is where the design departs from it, with the reasoning summarised and the full trade-off analysis in [10](10-decision-register.md).

| `plan.txt` proposed | Design decision | Why |
|---|---|---|
| A `status/` directory with `backlog.md`, `in-progress.md`, `completed.md` | **Rejected.** One file per task; status is frontmatter; backlog/in-progress/completed are *derived views*. | Three files partitioned by status means every status change is a two-file edit and a merge conflict. Aggregate files are the documented failure across Spec Kit, Taskmaster, and beads — including one incident where 1,115 records were silently deleted by a default text merge. |
| `context.md` as a project memory file | **Rejected as a single file.** Memory is split into requirements (why), ADRs (decisions), incidents (mistakes), and standards (conventions), each with its own lifecycle and hygiene check. | A single `activeContext.md` is the artifact most prone to context collapse — one documented case shrank 18,282 tokens to 122 in a single LLM rewrite. Splitting by lifecycle lets each piece be immutable, append-only, or mutable as appropriate. |
| "AI generates architecture, roadmap, task hierarchy" up front, then human reviews | **Reduced.** Up-front generation is limited to requirements plus a first slice of tasks. Architecture emerges and is recorded as ADRs. | Exhaustive up-front decomposition is what produces the 2,500-line artifact sets. Shape Up's observation that scopes are discovered while building is corroborated by every field report on Spec Kit. |
| Human types `Next`; agent does one task and stops. Always. | **Kept as the default, made risk-tiered, and given a review-debt limit.** Three autonomy levels; `risk: high` forces the strictest. | Stopping is right, but the flaw is on the human side: someone who types `Next` forty times stops reading, and the gate becomes theatre. Frequency of stops and quality of review are in tension. See [05](05-workflows.md#the-review-fatigue-problem). |
| Epics / Features / Tasks / Subtasks with priorities, estimates, risk, complexity | **Cut to two levels** (Requirement, Task) plus one optional `parent` pointer. Estimates and complexity scores removed entirely. | Every middle layer exists to coordinate humans across organisational boundaries that do not exist here, and each one is a decision the agent can get wrong. Estimation fields were cut on evidence, not taste. |
| A long list of documentation to write before any code | **Reordered.** Requirements and a decision log come first. Architecture, API, database, deployment, and testing docs are generated from or point at the real artifacts, and most are written as they become true. | Documentation is the #2 reported source of technical debt at Google, ahead of testing and code quality. Documentation written before the thing it documents exists is the highest-drift kind. |
| "Determine whether implementation should stop when quality gates fail" | **Answered: yes for contract violations, no for judgment signals**, with a four-class gate model and an automatic demotion rule for gates that misfire. | A binary block/warn model produces either alert fatigue or bypass culture. 54% of surveyed engineers report having disabled or bypassed a security gate in the past year. |
| "Whether multiple specialised agents should exist; whether a PM agent should coordinate" | **Answered: no.** One agent, modes not personas, two context-isolation subagents. | Across 1,600+ annotated multi-agent failure traces, "disobey role specification" accounts for 1.5% of failures; verification failures account for 8%+. Roles are not where the leverage is. |

## Success criteria

The design succeeds if, in a project cloned from the template:

1. A human can answer "what is being built, why, what is done, what is next, and what must never be violated" by reading files in the repository, at any commit, offline.
2. `aios next` returns the same task given the same repository state, every time, and cannot be influenced by an agent forgetting to update something.
3. An agent that weakens a test, escapes its declared file scope, or adds an unlockfiled dependency produces a red build rather than a green one.
4. The always-on instruction surface stays under its line budget for the life of the project, and rule count is capable of going *down*.
5. Total artifact volume per change stays under a stated budget, and the team would rather read the artifacts than skip them.

Criterion 5 is the one most likely to fail, and it is the one worth watching hardest.
