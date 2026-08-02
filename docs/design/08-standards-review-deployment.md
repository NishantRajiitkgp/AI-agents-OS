# 08 — Engineering standards, review, and delivery

---

## 1. Engineering standards

### 1.1 The test every standard must pass

A standard ships only if it answers all three:

1. **Can a machine check it?** If yes, it is a lint rule and the prose is at most two lines pointing at the rule.
2. **What breaks if it is violated?** If the answer is "nothing, it just looks different", it is a preference and does not ship.
3. **Would a competent engineer do this anyway?** If yes, it is noise, and noise in an instruction file displaces signal ([01: 2.2]).

Most conventional style guidance fails all three. That is the intended outcome: **formatting is a formatter's job, not a document's.** Prettier/Black/gofmt with zero configuration options exposed, because time spent choosing between two arbitrary conventions is pure loss.

### 1.2 What actually survives

The standards that pass the test are almost all *semantic*, and they cluster in five areas:

**Naming with meaning.** Not "use camelCase" (the linter's job) but "a function named `get*` must not mutate", "`*Id` is always the primary key, `*Ref` is always a foreign reference", "`Money` is minor units as an integer, never a float." These are the facts that prevent whole classes of bug and that an agent cannot infer reliably from a partial reading of the codebase.

**Error taxonomy.** Which error types exist, which are retryable, what a client can depend on. Enforced partly by types; the parts that cannot be typed are the standard.

**Module boundaries.** What may import what. This is enforced by an import linter (`dependency-cruiser`, `import-linter`, ArchUnit), and `docs/architecture.md` explains *why* the boundaries exist — which is the half a linter cannot express and the half that stops someone deleting the rule when it becomes inconvenient.

**Async and concurrency rules.** Where blocking is permitted, transaction boundaries, idempotency requirements. Rarely lintable, high cost when violated.

**Public API compatibility.** What may change without a major version. Partly enforceable by schema diffing.

### 1.3 Standards for AI-generated code specifically

Three, derived from the measured differences in what AI-assisted codebases look like:

- **No speculative abstraction.** An interface with one implementation, an option nothing sets, a hook nothing calls. Agents produce these prolifically because they pattern-match on "well-designed code". Advisory gate; unused-export detection catches most of it.
- **Prefer extending an existing module over adding a new one.** Direct counter to the measured rise in duplication and collapse in refactoring ([01: 1.2]). Operationalised as the explorer duplicate check in [05](05-workflows.md#32-executing-a-task), not as an instruction.
- **Comments state constraints, never narration.** `// Increment the counter` is noise; `// Must run before migration 0042 — FTS index is rebuilt there` is the only kind worth the tokens.

---

## 2. Code review

### 2.1 Two passes with different jobs

**Machine pass** (CI + verifier subagent) covers everything mechanical: gates, style, coverage, security, scope, acceptance criteria. It runs first, and a human should never see a PR that has not passed it.

**Human pass** covers only what a machine cannot: is this the right thing to build, is the abstraction sound, will this be comprehensible in a year, does it match the requirement's *intent* rather than its letter.

The split matters because the failure mode of AI-era review is a human doing the machine pass badly on a large diff and having no attention left for the second. Explicitly narrowing the human's job is the intervention.

### 2.2 The review packet

Every PR presents, generated:

- The task file (requirements, acceptance criteria, constraints)
- Verification record — which commands ran, with what result
- Diff, grouped by declared `touches`, with any escape flagged
- Gate results by class
- What the verifier subagent found and how it was addressed
- Requirement/test traceability delta

The purpose is to answer the reviewer's questions before they ask them, since the alternative is that they do not ask.

### 2.3 No review quotas

BMAD's documented rule requiring at least three findings per review ([00](00-charter.md)) is a good example of a mechanism that produces the appearance of rigour and destroys its substance: a reviewer with nothing to say invents something, and the noise trains everyone to discount findings. "Approved, no findings" must remain a valid and unremarkable outcome.

### 2.4 Sizing

Soft limit 400 lines of diff, hard limit 800 at `production` tier and above, both measured against the classic finding that review effectiveness collapses past a few hundred lines. Over the limit, the PR must either be split or carry a written reason. Generated files and lockfiles are excluded from the count.

---

## 3. Branching and commits

**Trunk-based, short-lived branches.** DORA identifies strong version-control practice as one of the seven capabilities that make AI adoption net-positive ([01: 1.1]), and long-lived branches plus a high-throughput agent is the specific combination that produces unresolvable merges.

- Branch per task: `task/T-a3f8-search-endpoint`.
- Conventional commits with the task ID in the trailer, so the changelog and the traceability map both generate.
- Squash merge, so `main` has one commit per task and `git log` is a readable list of completed work.
- `main` is always releasable. Feature flags for anything incomplete.

---

## 4. Deployment

The template ships a pipeline whose stages are fixed and whose enforcement follows tier:

```
commit → build+unit → gates → integration → staging deploy → smoke → [approval] → canary → full
```

- Every artifact is built once and promoted, never rebuilt per environment.
- Every deploy is reversible: migrations forward-compatible, feature flags for behaviour changes, an explicit rollback command that is *tested*, not assumed.
- Approval before production is human at `production` and above; automatic below.
- Canary with automatic rollback on error-rate or latency regression at `production` and above.

**Agents may not deploy to production.** Not at any autonomy level, not at any tier. The reasoning is not that an agent would deploy something bad more often than a human — it is that deployment is the one action whose blast radius is unbounded and whose reversal depends on judgment under time pressure. The value of a human in that loop is not the decision; it is that someone is already watching.

### 4.1 Production readiness

Enforced as a checklist gate before the first production deploy of a service, not before every change: health endpoint, structured logs with correlation IDs, the four golden signals instrumented, alerts routed to a real destination, a runbook for each alert, a rollback procedure that has been executed at least once in staging, and a documented data-retention position.

### 4.2 Observability

The default is structured JSON logs, correlation IDs propagated across service boundaries, OpenTelemetry traces on request paths, and errors with enough context to reconstruct the failure without reproducing it.

There is one AI-specific addition worth its cost: **log which task ID shipped which change**, via the commit trailer, so that a production incident can be traced back to the task, the requirement, and the review that let it through. That path — incident to requirement — is what makes the incident log in [07](07-security-and-agent-containment.md#4-incident-response-and-the-learning-loop) able to produce controls rather than regrets.
