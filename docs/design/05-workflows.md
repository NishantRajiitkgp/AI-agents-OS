# 05 — Workflows

Three loops: what the human does, what the agent does, and what happens between them. Plus the honest treatment of the thing most likely to break: human review capacity.

---

## 1. Modes, not personas

The agent has four modes. A mode is a **tool permission set plus a checklist plus an output contract**. It is not a persona, because personas do not improve objective task accuracy ([01: 3.1]).

| Mode | Can write? | Ends with |
|---|---|---|
| **Explore** | No | An answer plus file references. Runs as the `explorer` subagent when output would be large. |
| **Plan** | Only `aios/tasks/`, `aios/requirements/`, `aios/open-questions.md` | Task files a human approves. Never source code. |
| **Implement** | Only paths matching the task's `touches` | A diff plus a verification record. |
| **Verify** | No | Findings against acceptance criteria. Runs as the `verifier` subagent in fresh context. |

The distinction from role-play matters practically. "You are a QA engineer, review this code" changes tone and nothing else. "You have no write tools, you have this diff and these acceptance criteria, and you have never seen the reasoning that produced them" changes what is possible — and it is the *fresh context*, not the label, that does the work ([01: 3.4]).

Mode transitions are explicit and are the natural boundary for the host tool's plan mode, which we defer to rather than reimplement ([01: 4.5]).

---

## 2. The human loop

### 2.1 Day 0, once per project

1. Clone the template. Delete `docs/design/` if not wanted.
2. Fill `aios/config.yml`: tier, stack, budgets.
3. Write requirements for the first slice — the *why*, in EARS form. This is the only substantial writing the human is asked to do, and it is not delegable: it is the one artifact that cannot be recovered by reading code later.
4. Seed `aios/glossary.md` with domain terms that have a precise meaning.
5. Run `aios probe-adapters`, commit the result.
6. Ask the agent to propose tasks for the first slice. Review, cut, approve.

Note what is not on this list: architecture, folder design for `src/`, technology decisions, a roadmap. Those emerge and get recorded as ADRs (P7).

### 2.2 The steady loop

```
Human:  Next
Agent:  aios next → T-a3f8 → implement → verify → submit → STOP, reports.
Human:  review the diff → merge, or reject with a reason → Next
```

Rejections are cheap and are supposed to happen. A rejection with a reason that recurs is the trigger for a new gate or standard ([09](09-maintenance-and-evolution.md)); a rejection reason recorded three times without a control being added is itself reported as a process failure.

### 2.3 What the human owns, permanently

Requirements and their priority. Risk classification. ADR acceptance. Merge. Everything in [07](07-security-and-agent-containment.md)'s protected set. These are not delegated at any autonomy level, because they are the points at which the system's objectives are defined — and a system that can rewrite its own objectives has no objectives.

---

## 3. The agent loop

### 3.1 Session start: progressive disclosure

An agent starting a session loads, in order, and stops as soon as it has enough:

1. `AGENTS.md` (always, ≤150 lines).
2. Nested `AGENTS.md` for directories it opens (automatic).
3. `aios next` output — the task file, and only that task file.
4. The requirements named in `satisfies` — only those.
5. ADRs and standards **only when a constraint references them**.
6. Deep reference material only on explicit request.

Steps 5 and 6 are the whole reason for progressive disclosure. The naive alternative — load all the ADRs, all the standards, and the full requirements set at session start — is exactly the pattern that degrades performance as context grows ([01: 2.1]) and displaces the instructions that matter ([01: 2.2]). The task file is written to be the single sufficient entry point precisely so that this works.

### 3.2 Executing a task

```
aios start T-a3f8
  → duplicate check: explorer subagent answers "does this already exist?"   [01: 1.2]
  → implement within `touches`
  → run `verify` locally
aios submit T-a3f8
  → verifier subagent, fresh context, diff + acceptance criteria
  → address findings
  → STOP
```

The duplicate check is a cheap counter to the measured rise in code duplication and collapse in refactoring under AI assistance ([01: 1.2]). It costs one read-only subagent call per task, in isolated context, and it is the difference between an agent that grows a codebase and one that maintains it.

### 3.3 Hard stops

The agent halts and reports rather than proceeding when:

- a quality gate in the **Contract** class fails ([06](06-quality-gates-and-testing.md));
- the change would need to escape `touches` (it may propose an amended task file; it may not just do it);
- a constraint in the task conflicts with what the code appears to require — this is the "the spec is wrong" case, and the correct output is a question, not a workaround;
- an ADR would have to be contradicted;
- a credential, key, or production endpoint is needed;
- two requirements conflict;
- the same test has failed three times with three different fixes. Beyond that the agent is guessing, and guessing near a test is one hop from weakening it ([01: 5.2]).

The last one is the interesting one. It converts an internal, invisible failure mode into an explicit stop with a report, at the exact moment the incentive to cheat appears.

### 3.4 Ending a session

The final message is a handoff: task, state, what was verified, what was not, open questions raised. It is written to the task file, not to a scratch memory file — the task is already the unit of state, and adding a second place for "what is going on" is how you get two answers to one question ([01: 2.4], P3).

---

## 4. Autonomy tiers

`plan.txt` proposed a single rule: one task, then stop, always. That is right as a default and wrong as an absolute — it treats a typo fix and an auth rewrite identically, which is how a review gate becomes a rubber stamp.

Three levels, selected by task `risk` × project `tier`:

| | prototype | internal | production | regulated |
|---|---|---|---|---|
| `risk: low` | A2 | A2 | A1 | A1 |
| `risk: medium` | A2 | A1 | A1 | A0 |
| `risk: high` | A1 | A0 | A0 | A0 |

**A0 — plan approval.** Agent proposes an approach; a human approves before implementation; a human reviews the diff. Two checkpoints.
**A1 — task-at-a-time (the default).** Agent implements one task and stops for diff review. One checkpoint.
**A2 — chain until blocked.** Agent may take the next task automatically, up to a configured limit (default 3) or until any Contract gate fails, then stops with the whole chain presented as one review.

`risk: high` never reaches A2 at any tier. A2 exists so that trivial work does not consume the review attention that non-trivial work needs — which is P6 applied to the human's time rather than the agent's.

---

## 5. The review fatigue problem

This is the design's most likely failure point and it deserves to be stated as such rather than assumed away.

A human who types `Next` forty times in an afternoon is not reviewing the fortieth diff. Stop-frequency and review-quality are in direct tension: more stops means more opportunities to catch problems and less attention per opportunity. Every framework in this space assumes the human keeps reading. None measures it. There is no data ([01, closing section]).

The mechanism, offered as an experiment rather than a solution:

**Review debt** = count of merged tasks whose diffs the human spent under a threshold on, or dismissed without comment, in a rolling window. Above a configured limit, `aios next` refuses to hand out work and reports that review is the bottleneck.

Detecting "did they actually read it" is imperfect — time-to-approve and comment presence are weak proxies, and both are gameable by a human who wants to be. That is acceptable, because the target is not a determined circumventer but a person in a flow state who has stopped noticing they stopped reading. A soft signal is enough for that, and a system that makes the bottleneck *visible* is doing more than one that pretends it isn't there.

Supporting measures: a total diff-size budget per review cycle; escalation to A0 after two consecutive rejections in the same area; and — the highest-leverage one — the `touches` mechanism from [04](04-state-and-tasks.md#35-touches-and-scope-escape), which makes the review surface predictable in advance rather than a surprise.

If review debt turns out to be unmeasurable in practice, the fallback is honest: state the limit as guidance and drop the enforcement. A control that cannot be measured should be removed, not left in place as decoration.

---

## 6. Parallelism

The rule follows directly from [01: 3.3]: **parallel reads, serial writes.**

- Multiple `explorer` subagents at once: fine, encouraged. Read-only, isolated context, no coordination cost.
- Multiple writing agents in one worktree: forbidden. This is precisely the case where implicit decisions conflict and the frameworks fail.
- Multiple writing agents in **separate git worktrees on tasks with disjoint `touches`**: permitted at `internal` tier and below, with the disjointness checked mechanically before dispatch. The declared write scope is what makes this checkable at all — without `touches` there is no way to know two tasks will not collide, which is why every "just run five agents" workflow eventually produces a merge disaster.

Expect roughly an order of magnitude more token spend for parallel work ([01: 3.3]) and treat it as an exception, not a default.

---

## 7. Worked example

Task `T-a3f8` from [04](04-state-and-tasks.md#31-schema), at `production` tier, `risk: low` → A1. The commands below are the hypothetical project's own; the loop is identical whatever the stack turns out to be.

```
Human: Next

Agent: aios next → T-a3f8 "Add /search endpoint returning ranked task matches"
       satisfies SEARCH-2, SEARCH-4 · touches 3 files · A1 (one task, then stop)
       Loaded: AGENTS.md, T-a3f8, SEARCH-2, SEARCH-4, ADR-007 (named in constraints).
       explorer: no existing search endpoint; FTS5 helper exists at src/db/fts.ts.

       [implements]

       verify: pnpm test src/api/search.test.ts        ✓ 7 passed
               pnpm bench:search --fixture=10k --p95=150 ✓ p95 = 96ms
       verifier (fresh context): 1 finding — AC-2 returns 400 but omits `code`.
       [fixes] re-verify ✓

       STOP. 3 files, +214/-6, all within declared scope.
       Open question raised: empty-result ranking is undefined in SEARCH-2.

Human: [reviews diff] merge. Next
```

Note what did not happen: the agent did not update a `progress.md`, did not tick a checkbox in an aggregate plan, did not write a session summary document, and did not mark itself done — CI does that when the verification record validates. The state changes are the task file's frontmatter and the code. That is the whole footprint of one unit of work, and keeping it that small is what allows the loop to run hundreds of times without the repository filling with process exhaust.
