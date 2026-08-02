# 10 — Decision register

Every design decision, with the alternatives that were considered and the trade-off accepted. Each entry carries a **revisit trigger**: the observation that should cause the decision to be reopened. A decision without one is a belief, not an engineering choice.

References like [1: 5.2] point at [01 — Evidence base](01-evidence-base.md); P-numbers point at [02 — Principles](02-principles.md).

---

## A. Structure and tooling

### D-001 — Tool-agnostic core with thin adapters
**Decision.** `AGENTS.md` is the single source of agent-facing project knowledge. `.cursor/` and `.claude/` may contain only imports, paths, and tool-specific settings.
**Why.** `AGENTS.md` is the cross-tool standard [1: 7.1]; duplicated knowledge is how documentation becomes wrong (P3).
**Alternatives.** *Cursor-native only* — smaller, but locks the template to one vendor in a market where the leader has changed twice. *Maintain both fully* — guaranteed drift. *Generate both from a source* — a build step for a file humans must be able to edit directly.
**Trade-off.** Tool-specific features are underused, since anything Cursor-only lives in a directory we keep deliberately near-empty.
**Revisit if** a tool ships a capability that is materially better than the portable path and cannot be reached via `AGENTS.md`.

### D-002 — `CLAUDE.md` is an import shim, never a symlink
**Decision.** `CLAUDE.md` contains `@AGENTS.md` plus Claude-only notes. CI greps for the flattened-symlink signature.
**Why.** Windows checkouts silently turn symlinks into one-line text files that every tool accepts as valid [1: 7.3]. The target environment is Windows/PowerShell.
**Alternatives.** *Symlink* — cleanest on POSIX, silent corruption on Windows. *Duplicate the content* — drift. *Generate at setup* — a step people skip.
**Trade-off.** One extra file with two lines in it.
**Revisit if** git on Windows makes symlinks reliable by default.

### D-003 — `aios/` is visible, not `.aios/`
**Decision.** State lives in a non-hidden directory.
**Why.** `ripgrep` skips dot-directories by default, and agents search with ripgrep. Hidden state is state the agent concludes does not exist.
**Alternatives.** *`.aios/`* — tidier root, breaks search. *Everything under `docs/`* — mixes machine-parsed state with human narrative, which have different lifecycles and different readers.
**Trade-off.** One more visible top-level directory.
**Revisit if** agent search tooling starts including hidden paths by default.

### D-004 — Root markdown files capped at five
**Decision.** CI fails if the root holds more than five `.md` files.
**Why.** Root files are scanned by everything; unchecked, they accumulate (`CONTRIBUTING`, `STYLE`, `NOTES`, `TODO`) and compete for the same attention.
**Alternatives.** *No limit* — observed drift. *Cap at three* — too tight for real projects with a licence and a security policy.
**Trade-off.** Occasional annoyance; a file must move to `docs/`.
**Revisit** never; if it becomes annoying that is the rule working.

### D-005 — Probe the adapter discovery matrix instead of documenting it
**Decision.** `aios probe-adapters` writes tagged facts into candidate locations and reports which tool surfaces them. Results are committed with tool versions.
**Why.** Which tool reads which directory is undocumented and changes between releases [1: 7.2]. A prose matrix would be wrong within months and authoritative-looking while wrong.
**Alternatives.** *Document it* — stale. *Assume the superset* — duplicates content into both trees.
**Trade-off.** A tool to build and re-run.
**Revisit if** either vendor publishes a stable, versioned discovery contract.

### D-041 — No presumed stack; the ecosystem is derived from the project
**Decision.** The OS names no default language, runtime, package manager, test runner, or formatter. Every stack-shaped choice is made per project, from its requirements, and recorded as an ADR at the moment it is made. Design documents state stack-dependent things as *constraints the choice must satisfy*, never as a named tool, and any concrete command in an example is labelled illustrative.
**Why.** A default is a decision made before there is anything to decide it on, and defaults are sticky — nobody revisits one that is already working badly. This is P7 applied to the stack itself: the ecosystem is exactly the kind of thing that should be decided late, and the cost of deciding it early is that every gate script, dependency control, and `aios/bin` entry point gets written against an assumption nobody chose.
**Alternatives.** *Node by default with a Python twin* — the earlier position; convenient for building the OS first and a mismatch for any project that isn't JavaScript, and the twin doubles the gate surface permanently. *Support all major ecosystems from day one* — an adapter matrix larger than the OS, most of it unexercised and therefore untrustworthy. *Let the agent infer the stack per repository* — the inference is silent, and a wrong one shows up as a gate that quietly does nothing.
**Trade-off.** M1 cannot start until the first project is chosen, which makes the roadmap's question 2 a hard prerequisite rather than a parallel track. Accepted: building against a guess costs more than waiting.
**Revisit if** the OS is ever extracted for general distribution across many unrelated projects, at which point a *reference* implementation in one named ecosystem becomes necessary — as a worked example, still not as a default.

---

## B. State and tasks

### D-006 — No separate change-proposal directory; git is the delta store
**Decision.** Adopt OpenSpec's discipline (requirement change + implementing tasks in one PR) and reject its directory structure.
**Why.** A `changes/` tree with proposals, deltas, and an archive reimplements version control in markdown. Git already holds the delta, the baseline, the archive, and the review (P3).
**Alternatives.** *Full OpenSpec* — a second copy of the truth. *No discipline at all* — requirements drift from code, the exact debt OpenSpec exists to prevent.
**Trade-off.** No long-lived, visible-on-`main` proposal for unstarted work. Mitigated by `open-questions.md`.
**Revisit if** a project accumulates more than a handful of long-lived proposals.

### D-007 — Two-level hierarchy (Requirement → Task)
**Decision.** No epics, features, stories, or subtasks. One optional `parent` pointer.
**Why.** Intermediate levels coordinate humans across organisational boundaries that do not exist in this loop, and each is a slot the agent will fill whether or not it should [1: 4.1].
**Alternatives.** *Full Epic/Feature/Story/Task* — the `plan.txt` proposal; produces the observed artifact explosion. *One level* — loses the why/what separation, which is the one distinction that carries weight.
**Trade-off.** Large backlogs render as long flat lists. Mitigated by only materialising the current slice (P7) and by `parent`.
**Revisit if** a project sustains 50+ concurrent `todo` tasks and grouping becomes the dominant navigation problem.

### D-008 — One file per task; no aggregate store
**Decision.** `aios/tasks/T-xxxx.md`. No `tasks.json`, no `backlog.md`.
**Why.** Aggregate stores are documented merge hazards, including a silent 1,115-record deletion from a syntactically-valid bad merge [1: 4.3].
**Alternatives.** *Single JSON/JSONL* — machine-friendly, conflict-prone, and fails in the worst way (silently valid). *SQLite* — no diff, no review, no merge.
**Trade-off.** Aggregate queries need a tool; directory grows. Mitigated by archiving completed tasks.
**Revisit if** task count makes globbing slow enough to matter — at which point add an index that is regenerable from the files, never authoritative.

### D-009 — Status in frontmatter; backlog views are derived
**Decision.** Reject `plan.txt`'s `backlog.md` / `in-progress.md` / `completed.md`.
**Why.** Status-partitioned files make every transition a two-file edit and a conflict (P3, P5).
**Alternatives.** *Three files* — as proposed; fails on parallel work. *Board file the agent maintains* — the drift documented in [1: 4.2].
**Trade-off.** No at-a-glance board in the repository. `aios board` generates one on demand, gitignored.
**Revisit if** humans consistently want a checked-in board — then generate it in CI and mark it generated.

### D-010 — `done` requires a machine-verified record
**Decision.** `done` requires `verify` commands passing at a recorded SHA, independently re-checked in CI.
**Why.** Self-declared completion is the single documented failure of every checklist tracker [1: 4.2]. This is the decision the whole design rests on (P5).
**Alternatives.** *Trust the agent* — measured to fail. *Human confirms every completion* — the human already reviews the diff; this adds a second click with no new information.
**Trade-off.** Every task must have an executable verification. Tasks that genuinely cannot (a design spike) use an explicit `verify: [manual]` with a human sign-off trailer — visible, and rare by design.
**Revisit** never; if this goes, nothing else stands.

### D-011 — Declared write scope (`touches`)
**Decision.** Tasks declare the files they may change; a diff outside the declaration fails at `internal` tier and above.
**Why.** Scope creep is invisible in a large diff and obvious as a task-file edit. Spends agent effort to save reviewer attention (P6). Also makes parallel worktrees checkable.
**Alternatives.** *No declaration* — silent scope growth. *Hard prevention at the tool layer* — brittle; the agent legitimately needs to read widely and sometimes to touch an unforeseen file.
**Trade-off.** Friction when the estimate is wrong, which is often. Deliberate: the friction is the signal.
**Revisit if** amendment rate exceeds ~50%, which would mean the declaration is guesswork and the gate is noise.

### D-012 — Readable requirement IDs, hashed task IDs
**Decision.** `AUTH-7` for requirements; `T-a3f8` for tasks.
**Why.** Requirements are quoted in conversation, commits, and test names, so readability wins; they change rarely so occasional collisions are cheap. Tasks are numerous, parallel, and machine-referenced, so conflict-freedom wins.
**Alternatives.** *Hash both* — unquotable requirements. *Sequential both* — conflicts on every branch, and renumbering breaks references already written into history.
**Trade-off.** Two ID conventions to learn.
**Revisit if** requirement ID collisions become frequent — a sign areas are too coarse.

### D-013 — No estimates, points, or complexity scores
**Decision.** Cut entirely. `priority` (1–3) and `risk` (three values) survive.
**Why.** Story points are essentially uncorrelated with duration; Google's 117 debt metrics explained under 1% of variance [1: 6.2]. `risk` survives only because it *changes system behaviour* — it selects the autonomy tier (P8).
**Alternatives.** *Keep estimates for planning* — planning against a number that predicts nothing is worse than planning against none, because it feels like information.
**Trade-off.** No burndown, no velocity, no forecast. For a one-human-one-agent loop this costs nothing real.
**Revisit if** someone demonstrates an agent-produced estimate that correlates with outcomes.

### D-014 — EARS for requirements and acceptance criteria
**Decision.** Constrained templates; a linter warns on non-conforming text and weasel words.
**Why.** Ambiguity becomes visible, each clause maps to one test, and it is machine-checkable [1: 4.6].
**Alternatives.** *Free prose* — ambiguity survives to implementation. *Gherkin* — heavier, pulls toward BDD tooling nobody asked for. *Formal specification* — wildly disproportionate outside safety-critical work.
**Trade-off.** Stilted prose; a learning curve.
**Revisit if** authors route around it by writing template-shaped nonsense — which would mean it should warn less, not more.

---

## C. Gates and verification

### D-015 — Four gate classes, not block/warn
**Decision.** Contract (halts), Ratchet (blocks regression), Advisory (reports), Report (measures).
**Why.** Binary models produce either alert fatigue or bypass culture; ~54% of engineers report having bypassed a gate [1: 5.4].
**Alternatives.** *Block everything* — bypass culture. *Warn on everything* — decoration. *Two classes* — no home for "important but subjective".
**Trade-off.** Every check needs a class assignment, and the assignment is a judgement.
**Revisit if** one class absorbs almost everything, indicating the taxonomy is not doing work.

### D-016 — Ratchets rather than fixed thresholds
**Decision.** Metric gates say "no worse than before".
**Why.** Always satisfiable, never blocks a good change, monotonically improves; fixed thresholds either block legitimate work or are set low enough to be meaningless [1: 5.5].
**Alternatives.** *Fixed target* — the standard failure. *No metric gate* — unbounded decay.
**Trade-off.** A bad baseline is inherited. Fix by setting the baseline deliberately at adoption, not by importing whatever the first run reports.
**Revisit if** ratcheting stalls near a genuinely acceptable value and the noise floor causes flapping.

### D-017 — Overridden gates demote automatically
**Decision.** Three overrides in 30 days demotes a Contract gate to Ratchet and files a report. Security gates are exempt.
**Why.** A repeatedly overridden gate is already not blocking; it is teaching everyone that overrides are routine, which erodes the gates that matter [1: 5.4].
**Alternatives.** *Keep it blocking* — bypass culture spreads. *Delete on override* — too aggressive; the gate may be right and the code wrong.
**Trade-off.** An important gate could be demoted because it is inconvenient. Mitigated by the exemption, the report, and demotion being a reviewable commit.
**Revisit if** demotions cluster on gates that later correlate with incidents.

### D-018 — Tier changes gate classes, never structure
**Decision.** All tiers run all checks; `tier` promotes or demotes them.
**Why.** Prototypes become production systems without anyone performing a migration. Trend data exists from day one, so promotion is not a leap.
**Alternatives.** *Fewer checks at low tiers* — faster start, cliff later. *Same enforcement everywhere* — prototypes become unusable and people abandon the OS at exactly the moment they are evaluating it.
**Trade-off.** Prototypes carry CI cost for checks that only report.
**Revisit if** prototype CI time becomes a reason people skip the template.

### D-019 — Test-integrity diff audit as a Contract gate
**Decision.** Scan diffs for the enumerated test-weakening patterns; any hit blocks.
**Why.** Reward hacking is measured and generalises [1: 5.1]; the behaviours are finite and grep-detectable [1: 5.2].
**Alternatives.** *Instruct the agent not to* — advisory, per P1. *Human review only* — reviewers miss a one-character `.skip` in a large diff, reliably.
**Trade-off.** False positives on legitimate test deletion, resolved by a human commit with a reason — which is the visibility the control exists for.
**Revisit** by extending the pattern list whenever a new evasion is observed.

### D-020 — The grader is outside the graded party's write scope
**Decision.** Tests, CI, gate config, lint config, and lockfiles are CODEOWNERS-protected, with tool-level deny-lists and a pre-commit hook as convenience layers.
**Why.** Without this every gate is advisory (P2a). No surveyed framework implements it, which is why their gate layers are nominal.
**Alternatives.** *Trust the agent* — contradicted by measurement. *Prevent the agent writing tests at all* — unworkable; the agent must write tests.
**Trade-off.** Human review is required on every test change, which is real recurring cost. Accepted: it is the price of the verification layer meaning anything.
**Revisit** never while the reward-hacking evidence stands.

### D-021 — Coverage is a ratchet and a map, never a target
**Decision.** No coverage percentage goal below `regulated` tier. Mutation sampling on critical modules instead.
**Why.** Line coverage is a poor fault-detection predictor [1: 5.6]; making it a target produces assertion-free suites.
**Alternatives.** *80% target* — the classic, produces exactly that. *Full mutation testing* — too slow to gate on.
**Trade-off.** No single quality number to report upward. Correct, but politically inconvenient in some organisations.
**Revisit if** mutation tooling gets fast enough to run per-PR.

### D-022 — Duplicate check before implementation
**Decision.** The explorer subagent answers "does this already exist?" at the start of each task.
**Why.** Measured rise in duplication and collapse in refactoring under AI assistance [1: 1.2]. Mechanised because P1 says the instruction version will not be followed.
**Alternatives.** *Instruct the agent to check* — advisory. *Similarity detection in CI* — after the fact, when the cost is already sunk.
**Trade-off.** One extra subagent call per task, in isolated context.
**Revisit if** the check's hit rate is near zero over a large sample.

---

## D. Agents and workflow

### D-023 — One agent with modes; no role personas
**Decision.** Explore / Plan / Implement / Verify as permission sets and checklists. No PM, architect, or QA persona.
**Why.** Personas do not improve objective accuracy [1: 3.1]; role disobedience is ~1.5% of multi-agent failures while verification is 8%+ [1: 3.2].
**Alternatives.** *Full agent team* — the `plan.txt` open question; adds coordination failure modes without touching the dominant ones. *No modes* — loses the permission scoping, which is the part that actually works.
**Trade-off.** Gives up whatever benefit specialised system prompts might confer. Evidence says that benefit is stylistic.
**Revisit if** a controlled study shows role specialisation improving coding-task correctness.

### D-024 — Exactly two subagents, both for context isolation
**Decision.** `explorer` (read-only) and `verifier` (fresh-context diff review).
**Why.** Parallel reads are safe and cheap; parallel writes conflict on implicit decisions [1: 3.3]. Fresh-context review outperforms self-review because of the missing trajectory, not the label [1: 3.4].
**Alternatives.** *More subagents* — each adds an interface. *None* — main context fills with search output; self-review misses what self wrote.
**Trade-off.** Extra token cost per task.
**Revisit if** host tools make fresh-context review a native primitive — then delete ours (§4 of [09](09-maintenance-and-evolution.md)).

### D-025 — Risk-tiered autonomy rather than always-stop
**Decision.** A0 / A1 / A2 selected by task `risk` × project `tier`; A1 is the default; `risk: high` never reaches A2.
**Why.** `plan.txt`'s always-stop is right by default and wrong absolutely: treating a typo fix like an auth rewrite is how review becomes a rubber stamp (P6).
**Alternatives.** *Always stop* — as proposed; burns review attention uniformly. *Full autonomy with post-hoc review* — large diffs, and review effectiveness collapses with size.
**Trade-off.** A2 chains can produce a bigger review surface. Bounded by chain limit and by any Contract failure ending the chain.
**Revisit if** A2 chains show a higher post-merge defect rate than A1.

### D-026 — Review debt as a throttle
**Decision.** Track apparently-unreviewed merges in a rolling window; over the limit, `aios next` refuses to hand out work.
**Why.** The unmeasured assumption in every framework here is that the human keeps reading. Nobody validates it, and the loop's entire safety argument depends on it.
**Alternatives.** *Assume good faith* — the universal choice, and the universal blind spot. *Hard rate limit on merges* — blunt; punishes genuine fast review.
**Trade-off.** The proxies (time-to-approve, comment presence) are weak and gameable. Acceptable: the target is inattention, not evasion.
**Revisit** after one real project. **If it cannot be measured usefully, delete it** rather than leaving it as decoration.

### D-027 — Progressive disclosure with an enforced budget
**Decision.** `AGENTS.md` ≤150 lines, CI-enforced, with a ratchet. Everything else loads on demand.
**Why.** Long context degrades [1: 2.1]; adherence collapses well before the window does [1: 2.2].
**Alternatives.** *Load everything* — the naive default, measurably worse. *Aggressive RAG over docs* — retrieval failure becomes a new silent failure mode, and this is where semantic-similarity degradation bites hardest.
**Trade-off.** The agent sometimes lacks a fact it would have had. Mitigated by making the task file self-sufficient.
**Revisit if** models demonstrate flat adherence across long contexts — then raise the budget, having measured it rather than guessed.

### D-028 — Facts in instruction files, procedures mechanised
**Decision.** `AGENTS.md` is a fact sheet. Anything phrased as "always/never/remember to" is either mechanised or deleted.
**Why.** Agents apply facts reliably and follow procedures unreliably [1: 2.3] (P1).
**Alternatives.** *Comprehensive process documentation* — the intuitive approach, and the one that produces 600-line instruction files nobody follows.
**Trade-off.** Some genuinely unmechanisable procedures survive as prose and will be followed inconsistently. They are few, and they are marked as such.
**Revisit** per-rule, whenever a procedure becomes automatable.

---

## E. Memory and documentation

### D-029 — Memory split by lifecycle; no single context file
**Decision.** Requirements, ADRs, incidents, standards, glossary, open questions — separate stores, separate mutability rules. No `activeContext.md` or `progress.md`.
**Why.** A single agent-rewritten memory file collapses; one documented case went 18,282 tokens to 122 in one update, silently [1: 2.4].
**Alternatives.** *Memory bank pattern* — popular and fragile. *Everything in `AGENTS.md`* — violates the budget immediately.
**Trade-off.** More files, and a human must know which store a fact belongs in. Mitigated by the lifecycle table in [03](03-repository-architecture.md#2-project-state-what-lives-where-and-why).
**Revisit** never; single mutable memory is the clearest documented failure in this space.

### D-030 — ADRs are immutable
**Decision.** Accepted ADRs are never edited; they are superseded by a new ADR that links back.
**Why.** Editing destroys the record of why the old decision was made, which is the only thing an ADR is for.
**Alternatives.** *Living documents* — loses history. *Delete when obsolete* — loses the most valuable part, the reasoning behind an abandoned path.
**Trade-off.** Readers must follow supersession chains. Cheap; the index shows current status.

### D-031 — Incidents must name the control they produced
**Decision.** Every incident entry has a mandatory field: the gate, rule, or test that now prevents recurrence — or an explicit statement that no practical control exists, and why.
**Why.** This is the compounding mechanism. A fix is worth one instance; a control is worth all future instances. It is also the health metric in [09](09-maintenance-and-evolution.md#2-health-metrics).
**Alternatives.** *Free-form postmortems* — become a list of regrets. *No incident log* — the loop cannot learn.
**Trade-off.** Pressure to invent a control where none is warranted. Mitigated by making "no control is practical, because…" a first-class answer.

### D-032 — Standards must declare `enforced_by` or `unenforceable`
**Decision.** Each rule names its enforcing lint rule (prose capped at two lines) or states why it cannot be enforced. A file where every rule is enforced gets deleted.
**Why.** Prose duplicating a lint rule is a copy that can disagree (P3); prose with no enforcement is a preference (P2).
**Alternatives.** *Prose style guide* — the norm, and inert. *Linter config only* — loses the "why", which is what stops someone deleting an inconvenient rule.
**Trade-off.** Writing a standard costs more up front. Intended.

### D-033 — Every document is generated, checked, dated, or immutable
**Decision.** Four classes; anything fitting none is not written.
**Why.** Documentation is the top reported source of technical debt at Google. The problem is not volume, it is documents with no mechanism for being true.
**Alternatives.** *Write comprehensive docs* — the default, and the source of the debt. *Write none* — loses the "why" permanently.
**Trade-off.** Some useful writing has nowhere to go and does not get written. Accepted; "dated and owned" is a deliberately wide net.

### D-034 — Requirements first; architecture recorded as it emerges
**Decision.** Against `plan.txt`'s up-front documentation set. Only requirements, glossary, and open questions precede code.
**Why.** Scopes are discovered while building [1: 6.3]; exhaustive up-front decomposition produces the observed artifact explosion [1: 4.1] (P7).
**Alternatives.** *Full design up front* — encodes the least-informed decisions most durably. *Nothing up front* — loses the "why", which code never recovers.
**Trade-off.** Early architecture is implicit and only becomes legible once ADRs accumulate.
**Revisit** for domains where up-front design is a regulatory requirement.

---

## F. Delivery and lifecycle

### D-035 — Agents never deploy to production
**Decision.** No autonomy level and no tier permits it.
**Why.** Not that an agent decides worse, but that deployment has unbounded blast radius and reversal depends on judgement under time pressure. The human's value is that someone is already watching.
**Alternatives.** *Agent deploys with automated rollback* — defensible for mature pipelines, and one incident makes it indefensible.
**Trade-off.** A human is required at the least intellectually interesting step.
**Revisit if** rollback becomes provably automatic and instantaneous for the given system.

### D-036 — Trunk-based, squash merge, task ID in the commit trailer
**Decision.** One task per branch, one commit per task on `main`.
**Why.** Strong version-control practice is one of DORA's seven amplifiers [1: 1.1]; long-lived branches plus high agent throughput is the combination that produces unresolvable merges. The trailer is what makes the traceability chain reach production.
**Alternatives.** *Merge commits* — preserves granular history; makes `main` unreadable at agent commit rates. *Rebase* — rewrites history, which conflicts with the review-trail requirement in [07](07-security-and-agent-containment.md#12-command-execution).
**Trade-off.** Intra-task history is lost. It is available on the branch until deletion, and is rarely wanted.

### D-037 — No review quotas
**Decision.** "Approved, no findings" is valid and unremarkable.
**Why.** BMAD's minimum-three-findings rule manufactures noise, and noise trains people to discount findings.
**Alternatives.** *Minimum findings* — the anti-pattern. *Mandatory checklist* — better, and included as the review packet in [08](08-standards-review-deployment.md#22-the-review-packet).

### D-038 — Deletion is scheduled, not incidental
**Decision.** `aios prune` proposes removals monthly; each is a PR.
**Why.** Keeping costs a little attention forever and nobody notices; deleting risks one visible mistake. Unmanaged, that asymmetry guarantees growth.
**Alternatives.** *Delete opportunistically* — never happens. *Automatic deletion* — too aggressive without review.
**Trade-off.** A recurring review task.

### D-039 — Kill criteria are published
**Decision.** Six explicit conditions under which the OS should be abandoned or rewritten ([09](09-maintenance-and-evolution.md#6-kill-criteria)).
**Why.** A system that cannot be abandoned gets maintained past its usefulness. Committing to the conditions in advance is the only way to evaluate honestly later.
**Alternatives.** *No criteria* — the norm, and the reason these systems outlive their value.
**Trade-off.** Invites early abandonment on a bad month. Mitigated by requiring a three-month fair trial.

### D-040 — `aios check` runs exactly what CI runs
**Decision.** Local and remote checks are the same code path, not two implementations of the same intent.
**Why.** Divergence turns every check into late feedback, and fast feedback is one of the capabilities that makes AI adoption net-positive [1: 1.1].
**Alternatives.** *Local subset for speed* — the common compromise; the excluded checks become the ones that always fail in CI.
**Trade-off.** Local runs are slower than a curated subset. Managed by the tiered timings in [06](06-quality-gates-and-testing.md#6-feedback-speed) — a fast pre-commit hook, then the full check.
