# 11 — Implementation roadmap

The order below is chosen so that the riskiest assumptions are tested first and each milestone is independently useful — if the project stops after any one of them, what exists still works.

---

## M0 — Test the assumptions that everything else depends on

**Roughly a day. Do not skip.** Three facts in this design come from undocumented tool behaviour, and building on them unverified would mean discovering the problem after the OS is written.

1. Build and run `aios probe-adapters`. Write a uniquely tagged fact into each candidate location (`AGENTS.md`, nested `AGENTS.md`, `.cursor/rules`, `.claude/agents`, `.claude/skills`, `.claude/commands`) and ask each tool to repeat the tag. Commit the result with both tool versions.
2. Confirm nested `AGENTS.md` path-scoping works in **both** tools. If it does not, `.cursor/rules` stops being near-empty and [D-001](10-decision-register.md#d-001--tool-agnostic-core-with-thin-adapters) needs revisiting before anything else is built.
3. Verify the flattened-symlink detector against a real Windows checkout without `core.symlinks`.

**Exit criterion:** a committed, dated matrix of what each tool actually reads.

---

## M1 — Walking skeleton

**Deliverable:** a repository that can run the loop once, end to end, on a trivial project.

- `AGENTS.md` at ≤150 lines, facts only. `CLAUDE.md` shim.
- `aios/` with config, one requirements area file, one task.
- CLI: `new`, `next`, `start`, `submit`, `done`, `list`, `check`.
- Schema validation for requirements and tasks.
- The `next` algorithm with its total ordering.
- Verification records, and the CI job that independently re-checks them.
- GitHub Actions running `aios check`.

**What M1 proves:** that `done` cannot be self-declared. That is [D-010](10-decision-register.md#d-010--done-requires-a-machine-verified-record), the decision everything else rests on, and it is either true after M1 or the design needs rework.

**What to leave out:** every gate beyond schema validation, both subagents, all hygiene checks, tiers. The temptation to build the gate framework first should be resisted — gates on top of unreliable state are decoration.

---

## M2 — Containment

**Deliverable:** the agent cannot edit its own grader.

- CODEOWNERS covering the protected set; branch protection on.
- Tool-layer deny-lists in `.claude/settings.json` and the Cursor equivalent.
- Pre-commit hook requiring a `human:` trailer for protected paths.
- The test-integrity diff audit, with the enumerated pattern list.
- Scope checking against `touches`.
- Secrets scan.

**What M2 proves:** [D-020](10-decision-register.md#d-020--the-grader-is-outside-the-graded-partys-write-scope). Validate it adversarially — instruct an agent to make a failing test pass by any means and confirm the build goes red. If it goes green, M2 is not done.

M2 comes before the broader gate set because containment is the precondition for gates meaning anything. A gate the agent can edit is worse than no gate: it produces a green signal that is trusted.

---

## M3 — Gates and tiers

- The four classes, declared per check.
- `aios/config.yml` tier → class mapping.
- Ratchets: coverage on changed lines, shipped artifact size, suppression count, `AGENTS.md` length.
- Lockfile enforcement, dependency allowlist, package age and typosquat checks.
- SAST, dependency audit.
- Override recording and the demotion counter.
- The review packet, generated onto the PR.

**What M3 proves:** that Contract failures are rare in practice. A high Contract failure rate after M3 means the classes are miscalibrated, and the fix is reclassification, not exhortation.

---

## M4 — Agent ergonomics

- `explorer` and `verifier` subagent definitions.
- Modes as permission sets; the duplicate check wired into `aios start`.
- Autonomy tiers, including the chain limit for A2.
- Hooks registered in both tools, pointing at shared scripts in `aios/bin/`.
- MCP drift check.
- Slash commands as thin wrappers over the CLI.

**What M4 proves:** whether the fresh-context verifier earns its token cost. Measure findings-per-review and how many survive to a code change. If close to zero, delete it — [D-024](10-decision-register.md#d-024--exactly-two-subagents-both-for-context-isolation) has a revisit trigger for exactly this.

---

## M5 — Hygiene and longevity

- All memory-hygiene checks from [04 §6](04-state-and-tasks.md#6-memory-hygiene-as-a-build-failure).
- Doc classification enforcement; staleness sweep.
- Traceability map generation and orphan reports.
- `aios health`, `aios prune`, `aios board`.
- Review-debt tracking — the most speculative piece, deliberately last.
- `aios upgrade` for downstream propagation.

**What M5 proves:** whether the OS can shrink. Track rules deleted versus added from this point.

---

## M6 — Trial and honest evaluation

One real project, three months, against the kill criteria in [09 §6](09-maintenance-and-evolution.md#6-kill-criteria). Instrument from day one; retrospective judgement about whether it "felt faster" is worthless here, since METR's participants believed they were 20% faster while measuring 19% slower [1: 1.3].

Baseline to capture before starting: current time-to-merge, rejection rate, and defect escape rate without the OS. Without a baseline the trial cannot conclude anything.

---

## Open questions requiring a human decision

These are genuinely undecided and are the natural next conversation:

1. **Primary language and ecosystem** for the reference template. There is no default and no leaning ([D-041](10-decision-register.md#d-041--no-presumed-stack-the-ecosystem-is-derived-from-the-project)) — the choice is derived from the first real project's requirements, since it determines `aios/bin`, every gate script, and the dependency controls in [07 §2](07-security-and-agent-containment.md#2-supply-chain). **This blocks M1**, and it is downstream of question 2, so decide them in that order.
2. **The first real project** for M6. The design's value is unprovable without one, and picking it late means instrumenting late.
3. **Host CI.** GitHub Actions is assumed throughout — CODEOWNERS, branch protection, and required checks are all GitHub mechanisms. GitLab or Azure DevOps changes the containment implementation substantially, though not the design.
4. **Line budget starting value.** 150 is a convergent practitioner estimate, not a measurement [1: 2.2]. Worth setting deliberately and tuning.
5. **Whether `docs/design/` ships in the template** or stays in the OS repository. Shipping it gives every project the reasoning; it also puts eleven documents into a repository that preaches artifact restraint.

---

## Risk register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The OS costs more than it returns [1: 1.3] | Medium | Fatal | Instrument from day one; published kill criteria; every milestone independently useful |
| Human review capacity does not scale | **High** | Fatal | Review debt (itself unvalidated); scope declaration; diff-size limits; A2 for trivial work |
| Host tools absorb most of it [1: 4.5] | High | Moderate | Quarterly overlap review with a bias to delete; a shrinking OS is a healthy one |
| Artifact volume exceeds review capacity [1: 4.1] | Medium | High | Budgets on every artifact; 60-line task cap; only the current slice is materialised |
| Adapter assumptions break on a tool update | High | Low | M0's probe, re-run quarterly and on major releases |
| Agents route around gates in unanticipated ways | Medium | High | Adversarial validation at M2; extend the pattern list on every observed evasion; incident log must name a control |
| The team adopts the structure and ignores the discipline | Medium | High | Nothing structural helps here. The honest mitigation is that the mechanical parts keep working even when the cultural parts lapse — which is the main argument for gates over guidelines in the first place |
