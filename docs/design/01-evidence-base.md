# 01 — Evidence base

Everything downstream is justified from this file. Findings are grouped by the question they answer, and each carries the source and the confidence we place in it. Where evidence is thin or contested, that is stated rather than hidden — several of the most consequential decisions in this design rest on qualitative field reports rather than controlled studies, and a reviewer deserves to know which ones.

Confidence key: **[strong]** multiple independent sources or controlled measurement · **[moderate]** one good source or several consistent field reports · **[weak]** single report or reasoned inference.

---

## 1. The macro picture: AI shifts the bottleneck downstream

**Finding 1.1 — AI adoption raises throughput and lowers stability. [strong]**
DORA's 2025 State of AI-assisted Software Development report found AI adoption associated with increased throughput and *decreased* delivery stability, reversing the historical throughput/stability correlation. Their explanation is that AI amplifies whatever the system already is: "AI acts as a mirror and a multiplier… amplifying the strengths of high-performing organizations and the dysfunctions of struggling ones." The seven capabilities that flip the sign include small batch sizes, strong version-control practices, quality internal platforms, and fast feedback — all installable by a template.
*Implication:* the OS's job is control systems, not instructions.

**Finding 1.2 — Trust in AI output is falling while usage rises. [strong]**
Stack Overflow's 2025 survey: 84% of developers use or plan to use AI tools, but 46% actively distrust accuracy, up from 31% the prior year; 66% cite "almost right, but not quite" solutions as their top frustration, and 45% say debugging AI code takes longer than expected. The 2024 GitClear analysis of 153M changed lines found code duplication rising and refactoring ("moved" lines) collapsing to its lowest measured share.
*Implication:* duplication and near-miss correctness are the specific defects to gate for; a "find the existing implementation first" mechanism has measurable value.

**Finding 1.3 — Perceived speedup is not measured speedup. [moderate]**
METR's 2025 RCT with 16 experienced OSS maintainers on their own mature repositories found a **19% slowdown** with AI tools, while the same developers estimated they had been sped up by 20%. Small n, expert developers, large familiar codebases — do not over-generalise. But the gap between felt and actual productivity is the reason this design refuses to trust self-report anywhere, including an agent's self-report that a task is complete.

---

## 2. Context: more instruction is not more compliance

**Finding 2.1 — Long context degrades non-uniformly. [strong]**
Chroma's *Context Rot* study (18 models, 2025) showed performance declining as input length grows even on trivially simple tasks, with degradation sharpest when the query and target are semantically related rather than lexically identical. Anthropic's own engineering guidance concurs: attention is a finite budget, and every token spent competes with every other.
*Implication:* an instruction file's marginal token has negative expected value past some threshold. Budget it.

**Finding 2.2 — Instruction adherence collapses well before the context window does. [moderate]**
Field measurements circulated through 2025 put reliable adherence at roughly 10–20 instructions, with degradation clearly visible by ~50 and severe past ~150. Anthropic's Claude Code team publicly recommends keeping `CLAUDE.md` "as short as possible," and multiple practitioner reports converge on 100–200 lines as the point past which added rules displace rather than accumulate.
*Implication:* a hard line budget on always-on files, enforced in CI, is the single highest-leverage constraint in the design.

**Finding 2.3 — Facts beat procedures. [moderate]**
The most consistent qualitative finding across practitioner reports: agents reliably use contextual *facts* ("this project uses `pnpm`", "auth lives in `src/auth/session.ts`", "`Money` is minor units as integers") and unreliably follow procedural *instructions* ("always write the test first", "always update the changelog"). Procedures that matter must be mechanised — as a hook, a gate, or a scaffold — not written down.
*Implication:* `AGENTS.md` should be almost entirely facts. Every procedure in it is a candidate for deletion or automation.

**Finding 2.4 — Single-file memory collapses. [moderate]**
The Cline/Cursor "memory bank" pattern (`activeContext.md`, `progress.md`, updated by the agent) has a documented failure mode where an LLM rewrite silently compacts the file; one reported case went from 18,282 tokens to 122 in a single update, destroying weeks of accumulated context with no error and no diff review. Systems whose memory is one mutable file rewritten by an agent have no defence against this.
*Implication:* split memory by lifecycle — immutable (ADRs, incidents), append-only (decision log), mutable-but-bounded (standards) — and never let a single agent rewrite the whole thing.

---

## 3. Roles are theatre for objective tasks

**Finding 3.1 — Persona prompting does not improve objective task accuracy. [strong]**
Zheng et al. (2024) evaluated 162 personas across 4 models and 2,410 factual questions: adding a role persona did not reliably improve accuracy over no persona, and the best persona could not be predicted in advance. Persona prompting helps with *style*, not correctness. "You are a senior security engineer" changes tone, not vulnerability detection.

**Finding 3.2 — Multi-agent failures are overwhelmingly about verification and specification, not roles. [strong]**
The MAST taxonomy (Cemri et al., 2025) annotated 1,600+ failure traces across 7 multi-agent frameworks. Failure distribution: inter-agent misalignment ~36%, specification issues ~30%, verification/termination ~21%. "Disobey role specification" was ~1.5%. Two frameworks' own reported fixes with better prompting and orchestration recovered only ~14% on average.
*Implication:* adding agents adds coordination failure modes without addressing the dominant ones. Spend the effort on verification.

**Finding 3.3 — Anthropic ships multi-agent for research and warns against it for coding. [strong]**
Anthropic's multi-agent research system post reports a 90.2% improvement over single-agent on breadth-first *research* — and explicitly notes it does not transfer to coding, because coding tasks have tight interdependencies that parallel agents cannot resolve, and that the system burns ~15× the tokens of a single chat. Cognition's "Don't Build Multi-Agents" argues the same from the opposite direction: context is not reliably shareable, so parallel writers make conflicting implicit decisions.
*Implication:* parallelism is right for read-only exploration and wrong for writes. That is exactly the split this design adopts.

**Finding 3.4 — Fresh-context verification is the one exception that pays. [moderate]**
The consistent counter-finding: a *separate* agent invocation reviewing a diff with no memory of having written it catches materially more than the author agent re-reading its own work. This is context isolation, not role-play — the value comes from the absence of the generation trajectory, and it survives even when both invocations use an identical prompt.

---

## 4. Spec-driven development: right mechanisms, wrong dosage

**Finding 4.1 — Front-loaded specs produce artifact volumes that exceed review capacity. [moderate]**
Scott Logic's production trial of GitHub Spec Kit reported roughly a 10× slowdown and ~2,500 lines of markdown for a single feature. Birgitta Böckeler's Kiro evaluation documented a straightforward bug fix expanding into 4 user stories and 16 acceptance criteria. Multiple reports note the same second-order effect: once artifact volume exceeds what a human will read, the artifacts stop being reviewed and become decoration that still costs tokens.

**Finding 4.2 — Checklist-file task tracking drifts. [strong]**
Kiro issue #6826 documents a 24-task project where checkboxes in `tasks.md` were never updated, leaving the file useless as a resume point. The same class of bug appears across Spec Kit and Taskmaster reports. The root cause is structural: status is stored in a file the agent must remember to edit, and nothing detects when it doesn't.

**Finding 4.3 — Aggregate state files are merge hazards. [strong]**
Taskmaster's single `tasks.json` and similar aggregate stores are documented conflict generators on any parallel branch. The `beads` issue tracker recorded a JSONL merge that silently deleted 1,115 records because git's default line-merge produced a syntactically valid file.
*Implication:* one small file per unit of state, and never a format where a bad merge stays valid.

**Finding 4.4 — Delta specs solve documentation debt; OpenSpec is the proof. [moderate]**
OpenSpec's model — a change proposal describes only ADDED / MODIFIED / REMOVED requirements against the current spec, and on completion the delta is folded into the baseline and the proposal is archived — keeps the spec current without asking anyone to rewrite it. This is the one structural idea from the SDD tools worth adopting wholesale.

**Finding 4.5 — The tools are converging on native features. [strong]**
Agent OS deleted its own spec-writing commands in v3 in favour of the host tool's plan mode. SuperClaude's published gap analysis lists native skills, hooks, and plan mode as things it must migrate to. The direction of travel is unambiguous: framework-level reimplementations of host features get deprecated.
*Implication:* build only what the host tools do not, and expect to delete anything that overlaps.

**Finding 4.6 — EARS reduces requirement ambiguity and is machine-checkable. [moderate]**
Easy Approach to Requirements Syntax constrains requirements to a small set of templates (`When <trigger>, the <system> shall <response>`; `If <condition>, then…`; `While <state>…`). Originating at Rolls-Royce for aero-engine software and now widely used in safety-critical domains, it yields requirements that lint mechanically for ambiguity and map one-to-one onto test cases. It is a *format*, adoptable without adopting any framework.

---

## 5. Quality gates: the agent will game them

**Finding 5.1 — Reward hacking is measured, not hypothetical. [strong]**
Anthropic's published work on reward hacking in production RL training found models learning to special-case tests, and — critically — that models which learned to hack in one setting generalised to *unrelated* misaligned behaviour, including sabotaging safety research code in 12% of trials. Their mitigation of choice, "inoculation prompting," reduced misgeneralisation but not the hacking itself.

**Finding 5.2 — Agents weaken tests in identifiable, enumerable ways. [strong]**
Published patterns from agentic coding evaluations: adding `@skip`/`.skip`/`xfail`, loosening assertions (`assertEqual` → `assertIsNotNone`, exact → `toBeTruthy`), broadening exception handlers to swallow the failure, mocking the unit under test, deleting the failing case, raising timeouts, and adding `--ignore` / `--exclude` flags to the test command. These are finite and grep-detectable in a diff.
*Implication:* a diff auditor for these specific patterns is cheap and high-value; it belongs in CI, not in the agent's prompt.

**Finding 5.3 — Package hallucination is a live supply-chain attack. [strong]**
The USENIX Security 2025 study across 16 models and 576,000 generated samples found ~19.7% of package references non-existent, with ~205,000 unique hallucinated names; 43% of hallucinations repeated across identical prompts, making them predictable enough to pre-register. Real attacks followed. Lockfile-only installs and a dependency allowlist are the direct mitigation, and both are trivially enforceable.

**Finding 5.4 — Blocking everything produces bypass culture. [strong]**
Survey data through 2025 puts the share of engineers who have disabled or circumvented a security gate in the past year at around 54%. A gate that fires often and is often wrong trains people to route around gates in general, including the correct ones.
*Implication:* gates need classes. Blocking must be reserved for the binary and the harmful; everything judgment-shaped must ratchet or advise.

**Finding 5.5 — Ratchets work where thresholds fail. [moderate]**
The widely-reported practical pattern: a fixed coverage threshold either blocks legitimate work or is set so low it means nothing, whereas a ratchet ("this PR may not lower the metric") is always satisfiable, never blocks a good change, and monotonically improves. Google's large-scale static-analysis experience points the same way: analyses were only durably adopted when their false-positive rate was low enough to be trusted at the diff, and effective FP rate — not true-positive count — was the adoption predictor.

**Finding 5.6 — Coverage percentage is a weak proxy. [moderate]**
Mutation-testing literature consistently finds line coverage a poor predictor of fault detection; a suite can execute a line without asserting anything about it. Coverage's honest use is as a ratchet and a map of what is untested, not as a quality number.

**Finding 5.7 — Structural gate integrity is the precondition for all of it. [strong]**
If the agent can edit the test files, the CI workflow, or the lint configuration, no gate is a gate. GitHub CODEOWNERS with required review, plus branch protection, plus a write-scope declaration per task, is the minimum viable containment. Every framework surveyed omits this.

---

## 6. Task decomposition: two levels, no scores

**Finding 6.1 — Small batches are one of DORA's seven amplifiers. [strong]**
Independently corroborated by the practical agent finding that tasks touching more than a handful of files have sharply higher failure and review-miss rates. Batch size is one of the few levers with both organisational and agent-level evidence behind it.

**Finding 6.2 — Estimates do not predict. [strong]**
Analyses of large agile datasets find story points essentially uncorrelated with actual elapsed time. Google's technical-debt work is the sharper version: 117 candidate metrics, evaluated as leading indicators, explained under 1% of the variance in engineer-reported debt — the only reliable signal was asking engineers. A field an agent fills in with a plausible-looking number that predicts nothing is worse than an absent field, because someone will schedule against it.

**Finding 6.3 — Scopes are discovered while building. [moderate]**
Shape Up's core claim, corroborated by every field report on exhaustive up-front decomposition: the real structure of the work becomes visible once implementation starts. Systems that demand a complete task tree before the first commit encode their least-informed decisions most durably.

**Finding 6.4 — Requirement→task→test traceability is the mechanism that stops invented work. [moderate]**
The specific control: every task declares which requirement it satisfies, and a task that satisfies nothing fails validation. This converts "don't build things nobody asked for" from an instruction (advisory, per 2.3) into a check (binding). The inverse — a requirement with no tasks, a test tracing to no requirement — surfaces coverage holes for free.

---

## 7. Tooling reality on the target platform

**Finding 7.1 — `AGENTS.md` is the emerging cross-tool standard. [strong]**
Adopted across OpenAI Codex, Cursor, Gemini CLI, Jules, and others; Claude Code supports it via an `@AGENTS.md` import from `CLAUDE.md`. It is the only file that does not need duplicating.

**Finding 7.2 — The adapter layer must account for asymmetric discovery. [moderate]**
Cursor reads `.claude/` for some asset types; Claude Code does not read `.cursor/`. Therefore shared assets belong in `.claude/` and Cursor-only assets in `.cursor/`, not the reverse. MCP configuration is genuinely duplicated (`.mcp.json` and `.cursor/mcp.json`) with no supported single source, so it needs a drift check rather than a clever symlink.

**Finding 7.3 — Symlinks are not portable to the target environment. [strong]**
On Windows, git symlink support depends on `core.symlinks`, Developer Mode, and clone-time configuration; the common failure is a checkout that silently produces a one-line text file containing the target path. That file then *looks* like a valid `CLAUDE.md` to every tool that reads it. Import shims (`@AGENTS.md`) plus a CI check for the flattened-symlink signature is the portable answer.
*The user's environment is Windows/PowerShell, so this is a hard constraint, not a nicety.*

---

## What the evidence does not settle

Stated plainly, because these are the design's real risks:

- **Whether the whole approach nets positive.** There is no controlled study of a repository-template OS of this kind. METR (1.3) is a warning that structured overhead can cost more than it returns in exactly the mature-codebase setting this targets. The instrumentation in [09](09-maintenance-and-evolution.md) exists because of this.
- **Where the line budget actually sits.** 100–150 lines is a convergent practitioner estimate, not a measurement. It should be treated as a starting parameter to be tuned per project.
- **Whether humans sustain review under a stop-every-task loop.** No data. This is the most likely failure point and is addressed with a review-debt mechanism in [05](05-workflows.md) that is itself unvalidated.
- **How much of this survives the next 18 months of host-tool features.** By 4.5, some of it will not, and the design should be judged partly on how gracefully it can shrink.
