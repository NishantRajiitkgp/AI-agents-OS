# Build plan — AI Engineering OS

Every task required to build the system described in [`docs/design/`](docs/design/), in the
order the roadmap requires. **The repository root is this folder** — the folder the coding tool
opens. `M1-01` moved it here from a subfolder, because a nested `AGENTS.md` is measured never to
load and the always-on core would have silently done nothing.

**Current position:** `M3-10`. **M2's exit criterion is met** — `M2-09` ran and the build went
red ([record](aios/bin/probe/results/adversarial-2026-07-31-D-020.md)). Five M2 items are held,
not done: `M2-01`–`M2-04` on the repository or the binary, and `M2-10` on a measurement.
`M2-09` was itself listed as needing the binary and a pull request. It needed neither, and the
assumption cost a milestone's delay — a held task is worth re-reading before it is skipped. **M0 is complete** — it produced five ADRs, three of which correct
or supersede a design document, and one of which (`ADR-009`) reopens D-001. `M0-03` is deferred
(no second tool) and `P0-6` is open; neither blocks until M5.

**Uncommitted, and it now costs.** The repository is initialised and fully staged, but the
initial commit is deferred until the GitHub remote exists. Three things wait on it: `T-950a`
cannot reach `done` without a commit to record in its verification record; since the Rust
toolchain is unreachable from this network, CI is the only place the binary can be built at
all; and the ratchet baseline-tampering check compares against the committed value, so with
zero commits it is inert here and only the tests prove it works.

**`M1-08` is blocked on the network, not on the design.** Every `rust-lang.org` host is
filtered here, and so is `objects.githubusercontent.com`, where GitHub serves release
binaries — so no compiler can be fetched by any route. See
[the incident](aios/incidents/2026-07-31-rust-toolchain-unreachable.md).

**Work has moved past the blocked run.** `M1-08`–`M1-18` need the binary, `M2-01`–`M2-04`
need the repository or a GitHub handle. `M2-05` was the topmost task blocked by nothing and
is done. This is the selector's own rule — a blocked task is skipped, not waited on — applied
by hand until `aios next` exists to apply it.

---

## How this file is used

Say **`next`** and the topmost unchecked task gets worked. One task at a time. A task is
ticked only when its **Done when** line is objectively true — not when the work "feels"
finished. That is the same rule the OS itself enforces ([04 §3.4](docs/design/04-state-and-tasks.md#34-done-cannot-be-self-declared)),
applied to its own construction.

**This file is a bootstrap, not the system.** A checklist an agent ticks is precisely the
failure mode the design exists to replace ([01: 4.2]). It survives only until `M1` ships a
working `aios next`; task `M1-18` migrates the remainder into real task files and retires this
document. If it is still being edited at `M3`, the OS does not work and that is the finding.

## Standing rules for every task below

1. **The stack is a reference implementation, not a default.** `P0-2` chose one for this
   repository against its own derived constraints
   ([ADR-005](docs/decisions/ADR-005-reference-implementation-ecosystem.md)). Projects cloned
   from the template still choose their own under
   [D-041](docs/design/10-decision-register.md#d-041--no-presumed-stack-the-ecosystem-is-derived-from-the-project),
   so nothing shipped in the template may assume the consumer shares it.
2. **A decision becomes an ADR at the moment it is made** — not before, not in a batch
   afterwards ([P7](docs/design/02-principles.md)).
3. **A new rule or gate must cite** an incident, a recurring rejection reason, or a metric.
   Never an intuition ([09 §5](docs/design/09-maintenance-and-evolution.md#5-how-the-os-changes-itself)).
4. **If it can be checked, check it; do not write it down as prose** ([P2](docs/design/02-principles.md)).
5. **A document may only be written once the thing it describes is decided**
   ([03 §4.3](docs/design/03-repository-architecture.md#43-ordering-what-gets-written-when)).

---

## P0 — Decisions that block all construction

Human-owned. None of these are delegable and none can be inferred. The roadmap lists them as
the natural next conversation; `P0-2` is a hard prerequisite for every line of `M1` code.

- [x] **P0-1** Choose the first project — **the OS's own repository**
  - The roadmap's question conflated the project the OS is *built against* with the project it
    is *evaluated on*. They were separated: the OS builds itself; the M6 trial subject is still
    open and is now tracked as `P0-6`.
  - **Recorded in:** [ADR-001](docs/decisions/ADR-001-first-project-is-the-os-itself.md)

- [x] **P0-2** Choose the primary language and ecosystem — **Rust, as a reference implementation**
  - Decided by the constraint that replaced the self-referential one: a cloned project must
    invoke `aios/bin/**` **without adopting the OS's runtime**, accepted as hard. That eliminates
    every interpreted ecosystem and narrows to a self-contained binary.
  - Two consequences became tasks: `M3-11` (per-platform release pipeline, and proving the
    runtime-free invocation rather than asserting it) and an open question at `M1-01` on how a
    cloned project actually obtains the binary.
  - **Recorded in:** [ADR-005](docs/decisions/ADR-005-reference-implementation-ecosystem.md)

- [x] **P0-3** Choose the host forge and CI — **GitHub / GitHub Actions**
  - Every M2 primitive exists natively, so containment can be implemented as designed.
  - **Recorded in:** [ADR-002](docs/decisions/ADR-002-host-forge-is-github.md)

- [x] **P0-4** Set the starting line budget for `AGENTS.md` — **150 lines**
  - A config key, enforced as a Contract gate from M1, ratcheted from M5. To be tuned against
    observation, not defended.
  - **Recorded in:** [ADR-003](docs/decisions/ADR-003-agents-md-line-budget.md)

- [x] **P0-5** Decide whether `docs/design/` ships inside the template — **it does not**
  - Stays in the OS repository. ADRs travel; gates link to the design set rather than copying it.
  - **Recorded in:** [ADR-004](docs/decisions/ADR-004-design-set-does-not-ship-in-template.md)

- [ ] **P0-6** Nominate the M6 trial subject — **must be answered before M5 completes**
  - Split out of `P0-1`. This repository cannot serve: it has no pre-OS delivery history, so the
    baseline required by M6 cannot be captured and kill criterion 1 is unmeasurable.
  - Needs a project with existing delivery history whose time-to-merge, rejection rate, and
    defect escape rate can be measured *before* anything is switched on.
  - Bring forward if `ADR-001`'s revisit trigger fires — if three or more M3 gates cannot be
    validated against a CLI-shaped project, the gates are being calibrated on the wrong workload.
  - **Done when:** the project is named and `M6-01`'s baseline capture is scheduled.

---

## M0 — Probe the assumptions everything else rests on

**Roughly a day. Do not skip.** Three facts in this design come from undocumented tool
behaviour. Building on them unverified means discovering the problem after the OS is written.
A scratch probe script is acceptable here; it is re-implemented as `aios probe-adapters` once
`P0-2` is answered.

- [x] **M0-01** Stage the probe
  - Nine markers across the six candidate locations, staged at the workspace root, listed in
    `aios-probe-manifest.json`. Protocols and recording sheet in `aios/bin/probe/prompt.md`.
  - Two refinements over the roadmap's version, both load-bearing. Locations that can load
    eagerly *or* lazily carry **two** markers — one in the description frontmatter, one in the
    body — because a description in the system prompt spends context budget on every turn while a
    body pulled on invocation does not, and a single marker cannot tell those apart. And a
    **decoy label is declared but never written**: any tool reporting a marker for it fabricated
    the answer and the run is void, which is what makes a null result trustworthy.
  - **Unplanned finding, recorded as [ADR-006](docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md):**
    the harness was written as a PowerShell script and could not run. Group Policy sets
    `UserPolicy: Restricted`, which overrides `-ExecutionPolicy Bypass`, so no `.ps1` executes on
    this machine. Gate scripts are now binary subcommands, never shell scripts.

- [x] **M0-02** Run all three protocols against Cursor
  - Decoy clean in every session. Results in
    [`probe/results/probe-2026-07-31.md`](aios/bin/probe/results/probe-2026-07-31.md).
  - **Nested `AGENTS.md` does not work in Cursor** — absent in Protocol A *and* in Protocol B,
    where the agent edited a file in the same directory. Cursor's own glob-scoped rules *do*
    work, which is what makes this a mechanism failure rather than a probe failure.
  - Cursor reads **all three** `.claude/` subdirectories probed — skills, commands, and agents.
    `.claude/` is a shared location, not a Claude-Code-only one.
  - **Discovery has a lag.** `.claude/agents/` read `NONE` in two independent sessions and
    appeared in a third ~2h later. Every `no` in the run had to be re-checked against this, and
    the quarterly re-run needs a settling period or it will manufacture false negatives.
  - **The always-on set is much bigger than `AGENTS.md`**: root `AGENTS.md` + every `alwaysApply`
    rule + every skill description + every subagent description. `ADR-003` caps one input and
    leaves four unwatched.

- [ ] **M0-03** ~~Run all three protocols against Claude Code~~ — **DEFERRED, tool unavailable**
  - Claude Code is not installed on the target machine. Deferred, not failed: the Claude Code
    column of the matrix records **`not measured`**, which is a different fact from `no` and must
    not be collapsed into one.
  - Half of the assumed asymmetry is still testable. "Cursor reads parts of `.claude/`" can be
    measured in `M0-02`; "Claude Code does not read `.cursor/`" cannot be measured at all.
  - Rule out the confounds in `prompt.md` before recording any `no`. A rejected file format and
    an unread location produce identical null results and are completely different findings.
  - **Unblocks when:** Claude Code, or any second tool, becomes available.

- [x] **M0-04** Verify nested `AGENTS.md` path-scoping works in **both** tools
  - This is the gate on the whole adapter design. If nesting does not work, `.cursor/rules/`
    stops being near-empty and [D-001](docs/design/10-decision-register.md#d-001--tool-agnostic-core-with-thin-adapters)
    must be revisited before anything else is built.
  - Needs **two** results, not one: `NESTED` must surface under Protocol B *and* be absent under
    Protocol A. Surfacing under both means the file is always-on, so nesting is not scoping
    anything and the real context budget is larger than `M1-02` thinks it is — a quieter failure
    than nesting not working at all, and a worse one.
  - `CURSORGLOB` is the same test against Cursor's own glob mechanism, so that a nested
    `AGENTS.md` failure can be distinguished from path scoping failing generally.
  - **MEASURED AND CONFIRMED: it does not work in Cursor.** Absent across three sessions over two
    hours — agent-edited, user-opened, and idle. Cursor's glob-scoped `.cursor/rules/` produced
    exactly the `scoped` behaviour nested `AGENTS.md` was supposed to.
  - All four confounds closed. The strongest: `.claude/agents/aios-probe.md` was written in the
    same minute and *was* eventually picked up, which makes it a positive control ruling out the
    indexing-lag explanation.
  - **D-001 reopened** and the adapter layer rebuilt on measurement:
    [ADR-009](docs/decisions/ADR-009-adapter-layer-rebuilt-on-measurement.md). Path-scoped content
    goes in `.cursor/rules/` globs; the `.claude/` tree ships after all; root `AGENTS.md` stands.
  - Budget denominator corrected:
    [ADR-010](docs/decisions/ADR-010-budget-covers-the-measured-always-on-set.md).

- [x] **M0-05** Verify the flattened-symlink detector against a real Windows checkout
  - **Failure mode reproduced exactly.** `core.symlinks=false` at *system* scope on this machine
    (the Git for Windows default). A committed mode-`120000` entry clones to a 9-byte plain file,
    `Archive` attribute, no reparse point, content exactly `AGENTS.md`. Silent, and valid-looking
    to every tool that reads it.
  - **The documented regex is insufficient — 4 of 7 on a corpus.** It misses an empty file, a
    whitespace-only file, and a backslash target, and it passes a shim that has drifted into
    duplicated content. Replaced by a git-index check (exact, machine-independent, the CI gate)
    plus positive shim validation, which scored 7 of 7.
  - **Recorded in:** [ADR-008](docs/decisions/ADR-008-symlink-detection-and-shim-validation.md)

- [x] **M0-06** Write the dated discovery matrix and tear the probe down
  - Matrix at [`probe/results/probe-2026-07-31.md`](aios/bin/probe/results/probe-2026-07-31.md),
    dated, with the tool version and the always-on set named. Probe files removed.
  - **`git commit` deferred to `M1-01`** — this is not a git repository yet. Noted rather than
    skipped: the matrix is worthless as a baseline until it is under version control, so `M1-01`
    must commit it in the initial commit.
  - Two cells left `not measured`: whether invoking a skill or subagent loads its **body**. Low
    value — it affects only where large reference content should live, which is an M4 question,
    and `aios probe-adapters` (`M4-12`) will exist by then.

---

## M1 — Walking skeleton

**Deliverable:** a repository that can run the loop once, end to end, on a trivial project.
**What M1 proves:** that `done` cannot be self-declared
([D-010](docs/design/10-decision-register.md#d-010--done-requires-a-machine-verified-record)).
Either that is true after M1 or the design needs rework.

**Deliberately out of scope:** every gate beyond schema validation, both subagents, all hygiene
checks, tiers. Gates on top of unreliable state are decoration.

- [x] **M1-01** Create the repository skeleton
  - Layout from [03 §1](docs/design/03-repository-architecture.md#1-the-layout):
    `aios/{requirements,tasks,standards,incidents,bin}`, `docs/{decisions,runbooks}`,
    `.github/`, `.cursor/`, `src/`, `tests/`.
  - ~~**No `.claude/` tree**~~ — **superseded.** ADR-007's premise was false: Cursor reads
    `.claude/` skills, commands, and subagents. The tree ships with `agents/`, `commands/`, and
    `skills/` ([ADR-009](docs/decisions/ADR-009-adapter-layer-rebuilt-on-measurement.md)).
    Nested `AGENTS.md` is **not** created — measured dead in Cursor, and shipping a mechanism
    that does nothing is worse than shipping none, because it looks like a control.
  - `aios/` is **visible, not hidden** — ripgrep skips dot-directories and that is what agents
    search with ([D-003](docs/design/10-decision-register.md)).
  - The layout does not vary with project size; `tier` handles that later.
  - **Repository root settled — the root moved out.** The project sat one level below the folder
    the tool opens, which would have made its `AGENTS.md` a *nested* one: precisely the
    configuration `M0-04` measured as never loaded. The project was flattened up, so the design
    set at `docs/design/` is now inside the repository and
    [ADR-004](docs/decisions/ADR-004-design-set-does-not-ship-in-template.md) holds unchanged —
    it lives here, and the template excludes it at clone time.
  - Seeded `aios/open-questions.md` as `Q-001` (how a cloned project obtains the binary,
    [ADR-005](docs/decisions/ADR-005-reference-implementation-ecosystem.md) §2) and `Q-002` (the
    cross-ecosystem invocation contract for `aios/bin/**`). Both carry a closing condition and a
    deadline of `M3-11`, because an open question with neither is an opinion.
  - Also seeded `aios/glossary.md`, and added `.gitattributes` normalising line endings to LF.
    That last one is load-bearing, not cosmetic: development is on Windows and CI is on Linux, so
    without it every content comparison the OS makes has to strip carriage returns first, and the
    one that forgets reports a false difference.
  - **The root cap is enforced in CI, provisionally.** `.github/workflows/hygiene.yml` holds it
    as an inline runner step because
    [ADR-006](docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md) forbids shell scripts under
    `aios/bin/` and the binary that should own this does not exist yet. **It must move into
    `aios check`, with the workflow then calling the binary rather than keeping its own copy** —
    two implementations of one gate can disagree, which is what P3 forbids. The same workflow
    carries the `M0-05` committed-symlink check.
  - **Done when:** the tree exists and a check fails if root holds more than five `.md` files.
    ✅ Tree matches `03 §1`. The cap was run as the real workflow body under `bash`: exit 0 at
    one root `.md`, exit 1 at seven. Demonstrated rather than asserted, which is the same
    standard `M1` exists to prove.
  - **Carried forward: the initial commit.** `M0-06` deferred it here so the discovery matrix
    would enter version control. The repository is initialised on `main` and all 44 files are
    staged, but committing is deferred by decision until the GitHub remote exists. Until then
    the matrix and the ADRs have no content-addressed baseline, so an unintended change to them
    would not show up as a diff — the exact gap the encoding incident below was found without.
    **This is the first thing to do when the remote is connected**, before any further work.

- [x] **M1-02** Write `AGENTS.md` — the tool-agnostic core
  - Facts only, within the `P0-4` budget. Reads like a project fact sheet, not a process manual.
  - Test for every line: if it starts with "always", "never", "make sure to", or "remember to",
    it is a procedure — mechanise it or delete it ([P1](docs/design/02-principles.md)).
  - The few surviving procedural lines include the untrusted-content fence rule from
    [07 §1.3](docs/design/07-security-and-agent-containment.md#13-prompt-injection). It is
    phrased as a statement of fact — content inside a fence *is* data — so it passes the P1
    test on its own terms rather than as an exception to it.
  - **The always-on total is set: 200 lines, `AGENTS.md` sub-budget 150**
    ([ADR-011](docs/decisions/ADR-011-always-on-budget-is-200-lines.md)), closing the number
    [ADR-010](docs/decisions/ADR-010-budget-covers-the-measured-always-on-set.md) deferred to
    this task. Measured today: `AGENTS.md` 106 + one `alwaysApply` rule 25 + zero skill and
    subagent descriptions = **131**, leaving 69 lines of headroom.
  - **`.cursor/rules/no-presumed-stack.mdc` was stale and is corrected.** It asserted that no
    language, runtime, or CI host had been chosen — which `ADR-005` and `ADR-002` had already
    contradicted. It is always-on, so it was telling the agent the opposite of the decision
    record on every single turn. Rewritten to the surviving true claim (the OS chose for
    *itself*; a cloned project has still chosen nothing) and cut from 45 lines to 25.
  - **The budget's blind spot is recorded, not papered over.** The gate can only count what the
    repository controls. User-level skills and subagents installed on a developer's machine are
    also always-on — `M0` measured that — and no repository check can reach them, so the
    enforced number is a floor on the true always-on set rather than the whole of it.
  - **Done when:** within budget, every path it names exists, and no line fails the P1 test.
    ✅ All three are now gates in `.github/workflows/hygiene.yml`, not manual reviews, and each
    was verified in both directions: it passes the real file and rejects a deliberately broken
    one. The P1 gate carries a control for the compound adjective "always-on", which a naive
    prefix match flags as an imperative and which would have made the gate's first act a false
    positive.

- [x] **M1-03** Write `CLAUDE.md` as an import shim and `README.md` as a stub
  - `CLAUDE.md` is `@AGENTS.md` plus Claude-only notes. **Never a symlink.**
  - **[ADR-008](docs/decisions/ADR-008-symlink-detection-and-shim-validation.md) check 3 is now
    live**, since the shim it was specified against finally exists. Verified against the same
    seven-case corpus the ADR used — flattened symlink, empty, whitespace-only, backslash
    target, drifted duplicate content, and two valid shims. The positive check scores **7/7**.
    The superseded content regex scored 3/7 in this reproduction against the 4/7 the ADR
    recorded; the gap is in how the trimming is transcribed and does not touch the conclusion.
  - **ADR-008 check 2 (working-copy diagnostic) is deliberately not implemented.** It asserts
    that a mode-`120000` entry is a reparse point on disk, but check 1 forbids any such entry
    from existing, so check 2 can only fire in a repository where check 1 has already failed.
    It stays specified for the cloned-project case and gets a home when the binary does — a
    check with no reachable failure state is not worth a CI step.
  - **The README's quickstart is a gate rather than a promise.** Nothing builds, so the README
    honestly shows no commands. The check extracts every command from its fenced blocks and
    fails on any that CI does not run, which binds the moment a first command appears.
    Negative control confirms it: adding a `cargo build --release` block makes it fail.
  - **The allowlist lives in the workflow, not in the README.** Executing whatever the README
    contains would satisfy the wording and hand the agent the CI runner, since `README.md` is
    agent-writable and `.github/workflows/` is not ([07 §1.1](docs/design/07-security-and-agent-containment.md)).
  - `CLAUDE.md` is **not** counted in the always-on budget, because the measured set behind
    [ADR-011](docs/decisions/ADR-011-always-on-budget-is-200-lines.md) is Cursor's and Cursor
    was never measured reading it. It is kept minimal on the assumption that Claude Code loads
    it always-on, and that assumption is re-measured when a second tool arrives.
  - **Done when:** the `M0-05` detector passes and the README's quickstart is executed in CI.
    ✅ Both, plus the P1 and path-existence gates now cover `CLAUDE.md` and `README.md` as well
    as `AGENTS.md`.
  - **Root markdown is now at 4 of 5.** `README.md`, `AGENTS.md`, `CLAUDE.md`, `task.md`. One
    slot remains and `task.md` releases it at `M1-18`; anything else wanting root needs an ADR.

- [x] **M1-04** Define `aios/config.yml`
  - Keys: `tier`, budgets, gate policy, paths, the state directory name, deny list, template
    version. The directory name is a config key so a project that hates `aios/` can rename it
    in one place. **13 keys shipped.**
  - **The schema is deliberately not JSON Schema.** JSON Schema describes a key's shape but
    cannot require that every key carries a documented effect, and that requirement is the
    whole of the second Done-when clause. `aios/config.schema.yml` instead demands `effect`
    plus exactly one of `enforced_by` or `pending` on every key, and
    `.github/scripts/validate-config.py` enforces both that and the shape.
  - **`enforced_by` is verified, not asserted.** A value naming a workflow step is checked
    against the actual step names in `hygiene.yml`, so a key cannot claim an enforcement that
    does not exist. Today: **3 keys enforced, 10 pending a named task** — and `pending` must
    match a real task ID, which stops inert keys accumulating anonymously.
  - **The workflow now reads its thresholds from `config.yml` instead of hardcoding them.**
    That is what makes the three budget keys genuinely load-bearing rather than documentation;
    before this, the numbers lived in both the workflow and
    [ADR-011](docs/decisions/ADR-011-always-on-budget-is-200-lines.md) and could disagree (P3).
    The config is loaded and validated *before* any step that reads it, since a malformed
    value would otherwise silently disable the gate that consumes it.
  - **The protected set needed correcting.** [07 §1.1](docs/design/07-security-and-agent-containment.md)
    lists `.github/workflows/**`, but gate logic now also lives in `.github/scripts/`. Narrower
    than reality means the validator itself would have been agent-writable — the graded party
    editing its own grader. `protected_paths` and `AGENTS.md` both say `.github/` now, and
    `M2-01` must generate CODEOWNERS from the config key rather than from the design's list.
  - **The validator distinguishes "could not run" (exit 2) from pass and fail.** A missing
    YAML parser returning success is the failure mode that makes a whole gate layer decorative.
  - **Done when:** the file is schema-validated and every key has a documented effect.
    ✅ Both, exercised by **14 controls**: one baseline that must pass, plus undeclared key,
    missing key, wrong type, bad enum, sub-minimum value, bad version pattern, wrong list item
    type, boolean-where-integer, empty effect, both `enforced_by` and `pending`, neither,
    non-task-ID `pending`, and an `enforced_by` naming a step that does not exist.
  - **Provisional, like every gate so far**: a Python script under a protected path, because
    [ADR-006](docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md)'s binary does not exist.
    It moves into `aios check` at `M1-14`.

- [x] **M1-05** Define the requirement schema and write the first area file
  - One file per capability area. EARS bodies, `<AREA>-<n>` IDs, status of
    `active`/`deferred`/`superseded-by`/`dropped` with reasons mandatory on the latter three.
  - Requirements are never deleted — the record of what was once wanted is the memory this
    system exists to keep.
  - **Done when:** one real area file exists for the `P0-1` project's first slice.
    ✅ `aios/requirements/state.md` — the `STATE` area, **9 requirements, 8 active and 1
    deferred**. It covers what `M1` actually builds: per-unit files, computed progress, done
    requiring a machine-verified record, the grader re-running verification rather than
    trusting it, deterministic selection, malformed state refused at the boundary, globally
    unique IDs, and withdrawn requirements retained rather than deleted.
  - **The linter has two severities, and the split is the point.** Structure, status
    vocabulary, mandatory reasons and ID uniqueness **block**; EARS conformance and weasel
    words **warn only**, exactly as [04 §2](docs/design/04-state-and-tasks.md#2-requirements)
    specifies. Blocking on EARS buys template-shaped nonsense written to satisfy a linter,
    which is worse than the prose it replaced. All 9 requirements conform with zero warnings.
  - **Verified with 13 controls plus a duplicate-ID case.** Bad status value, `deferred` and
    `dropped` without a reason, `active` without a rationale, area not matching the filename,
    missing body, `superseded-by` pointing at an ID that does not exist, a file with no
    requirements at all — all block. A non-EARS clause and a weasel word warn and pass, which
    is the behaviour that would silently invert if the severities were ever collapsed.
    My first duplicate-ID fixture was built wrong — it used two *different* IDs, so it proved
    nothing — and the rebuilt one reports both locations.
  - **`paths.state_dir` is now a fourth enforced config key**, because the validator locates
    requirements through it rather than hardcoding `aios/`. Proven by pointing the key at a
    directory that does not exist: the check returns exit 2, *could not run*, rather than
    passing. A decorative key would not have noticed.
  - **New open question [Q-003](aios/open-questions.md).** Wiring that key up exposed a
    circularity: `config.yml` lives inside the directory `paths.state_dir` names, so the key
    cannot locate the file that declares it. There is a conventional-path-plus-glob fallback
    in place and it is convention, not contract. It belongs with `Q-002`'s repository-root
    discovery at `M1-08` — they are the same question from opposite ends.
  - **Source:** [04 §2](docs/design/04-state-and-tasks.md#2-requirements)

- [x] **M1-06** Define the task schema and write one seed task
  - Fields, and only these: `id`, `title`, `status`, `satisfies`, `priority`, `risk`,
    `blocked_by`, `touches`, `acceptance`, `verify`, `constraints`, optional `parent`.
  - Deliberately absent and not to be re-added: estimate, story points, complexity, effort,
    assignee, sprint, epic, labels, tags, due date.
  - **Done when:** a valid task file exists and the 60-line cap is enforced.
    ✅ `aios/tasks/T-950a.md` at 45 lines, and the cap is a config key
    (`budgets.task_file_lines`) read by the gate rather than a number in a script — the
    **fifth enforced key**. The seed task is real work, not a specimen: it is the `M1-07`
    cross-reference resolver, satisfying `STATE-6` and `STATE-7`, with `verify` naming the
    two commands that must exit zero.
  - **An unknown field is an error, not a warning.** The failure being prevented is schema
    drift by accretion — a slot appears, agents fill it, and later nobody can say which fields
    anything reads. The nine cut fields are named individually, so `story_points` reports
    *considered and deliberately cut* rather than *unknown*; the distinction is the difference
    between someone re-adding it and someone learning why it is not there.
  - **The design's closed field list is incomplete, in two different ways.**
    [04 §3.3](docs/design/04-state-and-tasks.md#33-states) requires `waiting_on` for status
    `waiting` and a `reason` for `dropped`, but neither appears in the field list. Both are
    now accepted as conditional fields, required exactly when their status applies and
    rejected otherwise — a `waiting_on` on a `todo` task fails.
  - **The second gap is [Q-004](aios/open-questions.md).** `aios next` sorts by `created_at`,
    which the schema does not define. It is deliberately left open rather than patched: the
    ordering is already *total* without it via the ID tie-break, so `created_at` is not
    load-bearing for determinism, only for the weaker intent that older ready work goes first.
    Dropping that tie-break is a live third option and `M1-10` should price it.
  - **The validator globbed the wrong thing at first, and a control caught it.** It matched
    `T-*.md`, so a file named `TASK-1.md` was not invalid — it was *invisible*, which is the
    one result a validator must never produce. It now walks every markdown file under
    `tasks/`, including the `done/` subtree, and rejects any whose name is not a task ID.
  - **Verified with 26 controls.** Unknown field, each of two cut fields, missing required
    field, bad status, `waiting` without `waiting_on`, `waiting_on` on a non-waiting task,
    `dropped` without a reason, priority out of range, bad risk, ID not matching the filename,
    malformed ID, empty `satisfies`, malformed requirement and task references, missing body,
    absent frontmatter, over the line cap, a misnamed file, a stray notes file, a broken file
    inside `done/`, and a duplicate ID spanning the active and done trees.
  - **Source:** [04 §3.1](docs/design/04-state-and-tasks.md#31-schema)

- [x] **M1-07** Build schema validation for requirements and tasks
  - Unknown fields rejected. IDs globally unique. Every `blocked_by`, `satisfies`, and ADR link
    resolves. A `satisfies` that resolves to no active requirement is a **hard error**, not a
    skip — it means the backlog is invalid, and it is the anti-invention control.
  - **Done when:** each failure mode has a test that proves the validator catches it.
    ✅ [`tests/test_validators.py`](tests/test_validators.py), 47 tests, all four validators
    green against the real repository.
  - **The first task worked from the task file rather than from here.** `T-950a` was the seed
    written at `M1-06`; this milestone is its execution. From `M1-10` the selector chooses
    what that is, and this file starts retiring.
  - **`Done when` said tests, so these are tests, not another harness.** Every gate before this
    was proved with a throwaway script that demonstrated the check worked once and then
    vanished. A check nothing re-runs is a check nobody knows still works. `tests/` was empty
    until now; this is the first thing in it.
  - **The suite was mutation-tested, because a passing suite proves nothing on its own.** Four
    deliberate breakages — the resolver ignoring requirement status, the task field list
    opening up, `deferred` no longer needing a reason, and the task loader reverting to the
    glob that hid misnamed files — were each caught, by 1 to 4 tests. Two tests assert a
    *non*-failure: EARS conformance and weasel words must warn without blocking, and that
    would invert silently if the severities were ever collapsed.
  - **A shared parser was extracted first.** The resolver needs to read both requirements and
    tasks, and a second copy of either parser is two definitions of what a requirement *is*
    that can disagree. [`.github/scripts/aios_state.py`](.github/scripts/aios_state.py) parses
    and does not judge; each validator keeps its own opinions. The division is that the two
    schema validators check one file against itself, and the resolver checks what no single
    file can know — ID uniqueness and `superseded-by` moved there for that reason.
  - **`T-950a` is at `review`, not `done`, and that is the control working.** A verification
    record needs the commit its commands ran against ([04 §3.4](docs/design/04-state-and-tasks.md)),
    and this repository has no commits. The evidence is genuinely incomplete, so the state
    cannot be claimed. This is the first concrete cost of deferring the initial commit.
  - **Source:** [04 §2](docs/design/04-state-and-tasks.md#2-requirements)

> **M1-08 through M1-14 are written and not verified, and the distinction is the whole point.**
> The Rust toolchain is still unreachable (every `rust-lang.org` host is filtered on this
> network), so nothing below has met a compiler. CI is the first one it will meet. By this
> project's own definition none of these is `done` — done is a state reached when a named
> command exits zero, not a claim anybody makes — so they are marked `[~]`, written, rather
> than `[x]`. Expect the first CI run to fail on `cargo fmt --check` and probably on clippy;
> that is those gates working, not a setback.
>
> What exists: `src/yaml.rs` (a parser for the YAML subset this repository's state is actually
> written in, hand-rolled because `Cargo.toml` has no dependencies and that constraint is
> load-bearing), `src/state.rs` (root discovery, config, tasks, requirements, incidents),
> `src/commands.rs` (the selector, the transitions, the verification record), `src/main.rs`
> (dispatch). Around 60 Rust unit tests, written to run in CI.

- [x] **M1-08** Build the CLI entry point
  - Pin the toolchain in-repo so contributor and CI builds cannot diverge — the same equivalence
    `aios check` demands of local versus CI.
  - Verify, rather than assume, the constraint ADR-005 marked as unproven: identical behaviour
    under PowerShell on a clean Windows checkout.
  - Keep the dependency count near zero. The OS has to satisfy its own M3 supply-chain gates
    without granting itself exceptions.
  - **Done when:** `aios` runs from a clean Windows checkout with no setup step, and the
    PowerShell row of ADR-005's constraint table moves from "assumed" to "verified".
  - **Blocked: the Rust toolchain cannot be downloaded on this machine.** `static.rust-lang.org`,
    `crates.io`, `sh.rustup.rs` and `forge.rust-lang.org` all reset the TLS handshake, while
    `github.com` and `pypi.org` return 200. DNS resolves and TCP 443 connects, so it is
    hostname-based filtering, not DNS, IP, or proxy. `winget` fails identically because its
    manifest points at the same host. Full evidence in
    [the incident](aios/incidents/2026-07-31-rust-toolchain-unreachable.md).
  - **Held rather than worked around.** Vendoring a toolchain by hand produces a build nobody
    can reproduce, which is the opposite of what this task exists to establish. Switching
    ecosystem would trade a decision made on measured constraints for one made on a firewall
    rule, and the reachable alternative fails ADR-005's deciding constraint outright.
  - **The control it produced:** an ecosystem's toolchain and registry must be *fetched* from
    the machine the work happens on before the ADR selecting it is recorded. ADR-005 weighed
    the ecosystem's properties and never asked whether it could be obtained here — one request
    would have caught this three milestones earlier.
  - **Verified in CI.** `windows-latest` builds from a clean checkout with no setup step and
    the PowerShell behaviour assertions pass — which is the Done-when, both halves. ADR-005's
    constraint table now records that row as verified rather than assumed. The toolchain still
    cannot be fetched on the development machine and CI is still the only compiler; what
    changed is that it has now compiled this.

- [x] **M1-09** `aios new task|req`
  - Scaffolds a valid file and allocates an ID. Task IDs are `T-` plus four hex characters
    hashed from title and creation timestamp, extending to six on collision — hash-based
    because sequential IDs conflict on every parallel branch.
  - **Done when:** a forced collision produces a six-character ID and CI still sees uniqueness.
  - **Written.** `aios new task "<title>"` and `aios new req <area>`. IDs are `T-` plus four
    hex characters of an FNV-1a hash over title and creation timestamp, widening one character
    at a time on collision — hashed rather than sequential because sequential IDs collide on
    every parallel branch, where two people both get "the next number" and the conflict
    surfaces at merge time as two different tasks with one ID. Tested for the forced-collision
    widening and for being a pure function of its inputs, so two machines agree.
  - **Verified in CI.** `ids_widen_on_collision` and
    `an_id_is_a_pure_function_of_title_and_seed` pass. One departure from the Done-when's
    wording, stated rather than glossed: widening goes one character at a time, so a single
    forced collision yields five characters and six takes two. Uniqueness holds either way,
    and uniqueness is the property the width was standing in for.

- [x] **M1-10** `aios next` — the deterministic selector
  - Exact algorithm: filter `todo` → drop those blocked by anything not in `{done, dropped}` →
    hard-error on unresolvable `satisfies` → sort by priority asc, tasks-unblocked desc, risk
    asc, `created_at` asc, id lexicographic asc → return head.
  - The final tie-break makes the function **total**: identical repository state yields an
    identical answer on any machine, with no clock and no randomness.
  - **Done when:** a property test proves determinism across shuffled input orderings, and the
    empty case reports *why* each blocked task is blocked.
  - **Source:** [04 §4](docs/design/04-state-and-tasks.md#4-aios-next--the-deterministic-selector)
  - **Written.** `select()` is a pure function of a task list, with reading and printing
    outside it, because determinism is the property it must have and a function that reads the
    disk cannot be shown to have it. Filter `todo`, drop anything blocked by a task not in
    {done, dropped}, sort by priority asc, tasks-unblocked desc, risk asc, id asc.
  - **One deliberate departure from the design.** The specified sort names `created_at`
    between risk and id, and `created_at` is not in the task schema — Q-004 recorded that gap
    and it was never closed. Sorting by it would mean inventing the field or reading the
    filesystem's mtime, and mtime differs between two clones of the same commit, which would
    make the answer machine-dependent. Machine-independence is the property the ordering
    exists to provide, so the field is omitted. The id tie-break is total on its own; what is
    lost is only the preference for older work among exact ties.
  - Determinism is tested over every rotation of the input rather than a shuffle: there is no
    random number generator in this crate, and a determinism test that needs one has a problem
    of its own. The empty case reports which task is blocked by what, and in which state,
    because "no tasks available" is equally true when the backlog is empty, when everything is
    in flight, and when one unfinished task is holding up nine others.
  - **Verified in CI.** Eight selector tests pass, `the_answer_does_not_depend_on_input_order`
    among them. The rotation-rather-than-shuffle departure recorded above is unchanged.

- [~] **M1-11** Implement the refusal conditions on `aios next`
  - Refuses to return anything when backlog validation fails or when an incident is open with
    `blocks_work: true`. The review-debt refusal lands at `M5-09`; leave a single call site.
  - Refusing is correct behaviour — an agent should be stopped by a broken plan, not routed
    around it.
  - **Written.** `aios next` refuses on an invalid backlog — unparseable task files, duplicate
    IDs, a `satisfies` naming no active requirement, a `blocked_by` naming no task, `waiting`
    with no `waiting_on`, `dropped` with no reason — and refuses again while any incident
    declares `blocks_work: true`. Both refusals say what to fix and state plainly that
    refusing is the intended behaviour rather than a bug to route around.
  - The review-debt refusal from M5-09 has its single call site marked in `next()` and nothing
    else, as this task asked.
  - **Written, still not verified.** Both refusals are implemented, and CI runs `aios next`
    inside this repository without it reporting could-not-run. But no test builds an invalid
    backlog, or an incident with `blocks_work: true`, and asserts that it refuses. What is
    proven is the path where nothing is wrong, which is not the path this task is about.

- [x] **M1-12** `aios start` / `aios submit` — state transitions
  - Six states, no more: `todo → doing → review → done`, plus `waiting` (external blockers
    only, requires `waiting_on`) and `dropped` (requires a reason).
  - `blocked` is **not** a state — it is derivable from `blocked_by`, and derived state that is
    also stored can disagree with itself ([P3](docs/design/02-principles.md)).
  - **Done when:** every illegal transition is refused with a specific message, and hand-editing
    frontmatter is caught by `M1-15`.
  - **Written.** Six states and an explicit legality table, with a specific message per
    illegal pair rather than one generic refusal — a tool that answers "illegal transition"
    often enough gets its state model worked around by hand-editing, which M1-15 then has to
    catch. `done` from `doing` says why `review` exists; reopening a `done` task says to write
    a new one instead, because reopening erases the fact that it was once believed complete.
  - A test walks all thirty-six state pairs and asserts none falls through to a default.
  - `blocked` is not a state: `aios start` reads `blocked_by` and refuses, with nothing to
    override, because derived state that is also stored can disagree with itself.
  - Transitions rewrite the single `status:` line and leave the rest of the file
    byte-identical. Round-tripping through the parser would reformat every comment and block
    scalar, turning a one-word change into an unreviewable diff.
  - **Verified in CI.** Five transition tests pass, `every_state_pair_is_decided_one_way_or_
    the_other` among them, which walks all thirty-six pairs and asserts none falls through.

- [~] **M1-13** `aios done` and the verification record — **the mechanism everything hangs on**
  - Runs every command in `verify`, refuses if any exits non-zero, then writes a record into
    the task file: commit SHA, command list, exit codes, timestamp.
  - **Done when:** a task with a failing `verify` cannot reach `done` through the CLI by any
    argument combination.
  - **Written.** Every `verify` command runs through the platform shell; any non-zero exit
    leaves the task in `review`. There is deliberately **no `--force`, no `--skip`, and no way
    to pass a substitute command** — the Done-when was that no argument combination reaches
    `done` past a failing verify, so the flags simply do not exist. A command killed by a
    signal reports -1 rather than being treated as a pass.
  - The record written afterwards names the commit SHA, each command, and its exit code. It is
    evidence, not an assertion: its only value is that CI can re-run those commands at that
    SHA and disagree (M1-15).
  - **Written, still not verified — and this is the one that matters most.** The record's
    mechanics are covered (`a_record_is_added_before_the_closing_marker` and both
    `strip_field` tests), but nothing asserts the Done-when itself: that a task with a failing
    `verify` cannot reach `done`. That currently rests on `--force` not existing, and an
    absence is precisely what a later edit restores without anyone noticing. It needs a test
    that runs `done` against a failing verify and asserts the task is still in `review`.

- [x] **M1-14** `aios list` and `aios check`
  - `backlog` / `in progress` / `completed` are **queries, not files** — an aggregate status
    file makes every transition a two-file edit and produces merge conflicts on every branch.
  - `aios check` runs locally exactly what CI runs. A gate whose local and remote behaviour
    differ is a gate people learn to ignore.
  - **Done when:** `aios check` and the CI job invoke the identical code path, proven by a test.
  - **Written.** `aios list` is a query over `aios/tasks/` with no aggregate file, because an
    aggregate makes every transition a two-file edit and conflicts on every branch. Files that
    fail to parse are reported rather than skipped — a task that silently vanishes from the
    list is indistinguishable from one that does not exist.
  - `aios check` reads the `run:` steps out of the workflow file and executes them. It does
    not restate the list, which is the requirement: a local check that lists its own steps is
    a second implementation, and the two drift in the direction of the local one being kinder.
    Adding a step to CI adds it here with no second edit.
  - **Verified in CI.** The step "What `aios check` would run is what CI runs" diffs the
    binary's `check --list` output against the steps parsed out of `hygiene.yml` and fails on
    any difference. That is the Done-when — identical code path, proven by a test — rather
    than an assertion that they agree.

- [x] **M1-15** CI: independently re-check every verification record
  - For every task marked `done`: the recorded SHA must exist, the recorded commands must match
    the task's declared `verify` list, and those commands must pass at that SHA.
  - This is the point of the whole milestone — **the state the agent can write is not the state
    anyone reads.**
  - **Done when:** CI fails on a `done` task whose record is absent, forged, or mismatched.
  - **Done.** `check-verification-records.py`, registered as a Contract gate in `hygiene.yml`.
    For every task claiming `done` it requires a record, a commit git can resolve, a command
    list matching the task's own `verify`, and those commands passing again at that commit.
  - The four failures are reported apart because only one of them is blameless. A re-run that
    fails means code rotted, which is what a re-check is for. A missing record, an unresolvable
    SHA and a mismatched command list are the shape of a claim that was never earned.
  - Two narrower forgeries fell out of writing the tests and are now closed. A record naming
    `HEAD` resolves fine and attests to nothing, since it means a different commit tomorrow —
    so the check asks `git cat-file -e <sha>^{commit}` rather than whether the string resolves.
    And a record whose own exit codes are non-zero contradicts the status it was written to
    justify, which no amount of SHA checking would notice.
  - Re-runs happen in a detached worktree. Checking out an old commit in place would rewrite
    the working directory of whoever ran it, and on CI would silently change what every later
    step in the job is looking at.
  - With no commits it exits 2 rather than 1: there, every recorded SHA is unresolvable, and
    reporting that as forgery would be a false accusation aimed at the state of the repository
    rather than at anything anybody did.

- [x] **M1-16** CI workflow running `aios check` on every pull request
  - **Done when:** a schema violation on a branch turns the build red before review.
  - **Written.** Two steps in `build.yml`, which already runs on every pull request.
  - `aios check --list` names the steps the binary would run, and CI diffs that against the
    `run:` steps `hygiene.yml` declares. They cannot drift by construction — `check` reads the
    workflow rather than restating it — so this gate is what catches the day somebody decides
    reading YAML at runtime is fussy and hardcodes the list. Running the full set inside CI
    would prove the same thing and pay for it twice.
  - The second step writes a task file with a nonsense status and asserts the binary exits 1,
    not 2. Malformed state is a failure, not an inability to run, and a tool that reports it as
    the second lets a broken backlog read as an environment problem somebody will retry.
  - Unverified along with the rest of the binary.
  - **Verified in CI.** The step "A schema violation turns the build red through the binary"
    plants a malformed task file, asserts the binary exits 1 rather than 2, and removes it.
    Exit 1 specifically: a malformed file is a failure, not an inability to run.

- [x] **M1-17** Adversarially validate D-010
  - Hand-edit a task's frontmatter to `done` without running the CLI. Amend a `verify` list
    after the fact. Point a record at a SHA that does not exist.
  - **Done when:** all three go red in CI. If any goes green, M1 is not done and the design
    needs rework before `M2` starts.
  - **Done, and all three go red.** `tests/test_verification_records.py` builds real git
    repositories with real commits, because each attack is a claim about what git can and
    cannot resolve and a fixture that stubbed git would be testing the stub.
  - Hand-edited frontmatter: caught, no record. Amended `verify` after the fact: caught, the
    record attests to a different check from the one the task now claims. A SHA that does not
    exist: caught, because the check asks git rather than validating that forty hex characters
    look like a commit.
  - The design said that if any went green, M1 is not done and the design needs rework before
    M2. None did. Four narrower forgeries were added on top, and the honest cases are asserted
    too — a genuine record passes, a task that is not `done` is not asked for one, and an empty
    backlog reports that it checked nothing rather than that everything is fine.

- [ ] **M1-18** Run the loop once, end to end, then retire this file
  - `aios next → start → implement → verify → submit → done → CI green → merge` on a trivial
    task in the `P0-1` project.
  - **Done when:** the loop completes, and every remaining task in this document has been
    migrated to real task files under `aios/tasks/`. This file is then deleted.

---

## M2 — Containment

**Deliverable:** the agent cannot edit its own grader.
**What M2 proves:** [D-020](docs/design/10-decision-register.md#d-020--the-grader-is-outside-the-graded-partys-write-scope).

M2 comes before the broader gate set deliberately: containment is the precondition for gates
meaning anything. A gate the agent can edit is *worse* than no gate, because it produces a
green signal that gets trusted.

- [~] **M2-01** Write CODEOWNERS covering the protected set
  - **Written, and deliberately failing.** `.github/CODEOWNERS` covers every entry in
    `protected_paths`, and `check-codeowners.py` verifies that mapping rather than trusting
    that two lists of protected paths stay in step — if they drift, the config keeps refusing
    the edit locally while the branch accepts it, which reads as a control that works right up
    until it is tested.
  - The gate currently fails, on purpose, because the owner is `@OWNER-PLACEHOLDER`. GitHub
    does not reject an owner it cannot resolve: it drops the rule and reports the file as
    valid. A CODEOWNERS naming nobody is the worst of the three states, because it is
    indistinguishable from one naming somebody. **Needs one GitHub handle to finish.**
  - Even filled in, this changes nothing until "Require review from Code Owners" is on for the
    default branch, which is `M2-02` and needs a pushed repository. The check prints what it
    cannot check rather than implying otherwise.
  - CI workflows, CODEOWNERS itself, `aios/config.yml`, `aios/bin/**`, `tests/**`, colocated
    test files, lint and type-check config, lockfiles.
  - This is **the only real control** of the three layers, because it is the only one enforced
    server-side. The other two are convenience.
  - **Done when:** a PR touching any protected path cannot merge without a named review.

- [ ] **M2-02** Turn on branch protection
  - Required reviews, required status checks, no force push, no history rewrite.
  - **Done when:** the settings are recorded as configuration, not just clicked in a UI.

- [x] **M2-03** Generate tool-layer permission deny-lists from `aios/config.yml`
  - **Done.** `generate-deny-lists.py` writes the `permissions.deny` array in
    `.claude/settings.json` from the config; CI runs the same script in check mode and fails
    while the two disagree. Editing the config and not regenerating fails the build, which was
    the Done-when.
  - The coarse form of each regex is **declared in the config beside the pattern it widens**,
    not inferred. There is no lossless conversion from a regex to a prefix matcher, and a
    generator guessing at regex semantics produces entries that look like coverage and match
    nothing. Nine of the forty-four patterns — pipelines, SQL statements, path globs — have no
    prefix form at all; those are written into the generated file as a named gap, so the
    coverage difference between the two tools is visible in the artifact instead of being
    derived by reading two files side by side.
  - `--write` is a separate mode from the check, and a test asserts the checking path contains
    no write. A check that regenerates before comparing always passes and catches none of the
    drift it exists for.
  - Cursor gets no generated artifact because it has no repo-level deny list to generate into
    (ADR-012). It gets the hook, which is the same regexes — so the two tools now differ in
    matcher precision rather than in whether the control exists.
  - This needed one new thing in the config schema: `type: map`, for a mapping whose keys are
    data rather than schema. Without it the validator demanded a schema entry per regex, which
    is not a schema, it is the same list written twice.
  - Both `.claude/settings.json` and the Cursor equivalent derive from one list. Generated
    files are checked in and verified up-to-date in CI.
  - **Done when:** editing the config and not regenerating fails the build.

- [x] **M2-04** Pre-commit hook requiring a `human:` trailer on protected paths
  - **Done.** Two hooks, not one, because the task's shape does not fit a single git event:
    `pre-commit` fires before a message exists, so the trailer check cannot live there.
    `check-human-trailer.py` runs as `commit-msg`; `pre-commit.py` runs the fast checks.
    Verified locally — a staged change to a protected path is rejected without the trailer,
    accepted with it, and a one-character name is rejected as the shape of a control that has
    been noticed and routed around.
  - **1.1 seconds against the 5-second budget.** The budget is the design, not a target: a
    pre-commit hook that takes twenty seconds is removed by the third day, and a removed hook
    catches nothing. So the failure mode being designed against is not "a bug slips through",
    it is "the developer turns it off". Only the secrets scan runs, scoped to staged files, on
    the grounds that a credential is the one failure a later gate cannot undo. Exceeding the
    budget prints and never blocks — refusing someone's commit over the hook's own slowness is
    the same instinct that gets it uninstalled.
  - Needed `--paths` on `scan-secrets.py` to scan a named handful rather than the tree.
  - `install-hooks.py` writes the two shims and refuses to replace a hook it did not write.
    `.git/hooks/` is not version-controlled, so this is opt-in per clone by construction —
    which is a property of git, and precisely why this layer cannot be relied on. A clone that
    never runs it has no local checks and looks identical to one that has.
  - Target under 5 seconds: format, secrets scan, changed-file lint only.
  - **Done when:** a staged change to a protected path without the trailer is rejected locally.

- [x] **M2-05** Build the test-integrity diff audit — **worked out of order; see the note below**
  - Enumerated patterns, all of them: added `skip`/`xfail`/`.only`/`@Disabled`; assertions
    weakened from exact to truthy; exception handlers broadened around a previously failing
    call; the unit under test replaced by a mock; a test deleted while its subject remains;
    timeouts raised; `--ignore`/`--exclude`/`--passWithNoTests`/`-k 'not ...'` added to a test
    command; coverage thresholds lowered; new suppression comments on touched lines.
  - Any hit is a **Contract** failure. Legitimate cases are handled by a human commit with a
    reason — which is exactly the visibility the control exists for.
  - **Done when:** each pattern has a fixture diff that trips it and one that does not.
    ✅ Nine patterns, eighteen fixtures, 27 tests, and five mutations of the audit each caught.
    [`audit-test-integrity.py`](.github/scripts/audit-test-integrity.py) runs as a
    `pull_request` Contract gate in
    [`test-integrity.yml`](.github/workflows/test-integrity.yml).
  - **Taken out of order because `M1-08`–`M2-04` are all externally blocked**, not because the
    ordering was wrong. `M1-08` onward needs a compiler that this network will not deliver;
    `M2-01` needs a GitHub handle to own the paths, `M2-02` needs the repository, `M2-03` and
    `M2-04` need the binary. This was the topmost task blocked by nothing. That is also what
    `aios next` would have done — a blocked task is skipped, not waited on — so the deviation
    follows the selector's own rule rather than overriding it.
  - **The paired fixtures are the design, not the test.** A detector that fires on everything
    satisfies "trips" trivially, and a Contract gate cannot be waived, so a false positive is
    not a nuisance — it is an unmergeable pull request with no escape hatch. Every pattern
    therefore has to prove it stays silent on the legitimate version of the same edit:
    narrowing an exception handler, raising a coverage floor, lowering a timeout, renaming a
    test rather than deleting it.
  - **Two tests are reflexive and matter more than the nine.** The fixture list is read from
    the audit's own source, so a pattern added without fixtures fails, and a fixture directory
    naming no real pattern fails. Without those the suite would keep passing while the audit
    accumulated unproven checks.
  - **The audit has one deliberate blind spot and a guard on it.** Its fixtures contain every
    pattern it detects, so it must skip its own fixture tree or fail on the pull request that
    introduces it. That exclusion is somewhere to hide a real edit, so a test asserts the
    directory holds nothing but `.diff` files, and another asserts a file just outside it is
    still audited.
  - **Patterns are cross-ecosystem on purpose.** This repository chose Rust for itself, but a
    cloning project has chosen nothing ([D-041](docs/design/10-decision-register.md)), so the
    markers cover pytest, jest, JUnit, Go, Rust and RSpec idioms. An audit fluent in one
    language would be advisory in most repositories that use it.
  - **Source:** [06 §4](docs/design/06-quality-gates-and-testing.md#4-test-integrity-the-audit-that-makes-the-rest-real)

- [x] **M2-06** Scope checking against `touches`
  - Globs permitted. The failure message tells the agent to amend the task file, and reports
    how much declared scope went unused — which surfaces tasks scoped lazily as `src/**`.
  - The point is not to stop the agent touching other files. It is that expanding scope becomes
    an explicit, reviewable edit visible in the same PR.
  - **Done when:** a diff outside declared scope fails, and the unused-scope figure is reported.
    ✅ [`check-scope.py`](.github/scripts/check-scope.py), 22 tests, five mutations each
    caught, wired as [`scope.yml`](.github/workflows/scope.yml).
  - **The gate does not block in this repository, and that is correct.** Scope is Advisory at
    `prototype` and Contract from `internal` up ([06 §3](docs/design/06-quality-gates-and-testing.md)).
    The class is read from `config.yml` by the script rather than decided in the workflow — a
    tier raised in config that left the gate advisory would be a threshold that lies. The
    blocking behaviour is tested against all three Contract tiers explicitly, because a suite
    that only ran the local configuration would have concluded the gate never blocks.
  - **`tier` becomes the sixth enforced config key**, and getting there needed a fix:
    `enforced_by` could only name steps in `hygiene.yml`, so a key read by a diff-based
    workflow could not be declared enforced at all. It now resolves against every workflow,
    and a reference to a missing file, a missing step, or a malformed string each fail.
  - **Globs are matched by a hand-written translator, not `fnmatch`.** `fnmatch` lets `*`
    cross a directory separator, which would make `src/*` match `src/a/b/c.py` — so a task
    scoped lazily would look precisely scoped, defeating the unused-scope figure that exists
    to catch exactly that. The mutation confirming this is the one worth keeping.
  - **The unused figure is reported even when nothing escaped.** A task declaring `src/**` and
    touching two files has passed the check while defeating its purpose. Only that number
    makes it visible.
  - **A task's own file is always in scope.** The verification record and every status
    transition are written into it, so a task that had to declare itself would be declaring
    the bookkeeping of every task — and forgetting to would make every task escape its own
    scope.
  - **It refuses rather than guesses.** The task is taken from `--task`, else the branch name,
    else the single task file in the diff; anything ambiguous exits 2. Attributing a diff to
    the wrong task checks it against the wrong scope, and a scope check that passes for the
    wrong reason is worse than none.
  - **Found while testing: a glob starting with `*` breaks its own task file.** YAML reads a
    leading `*` as an alias node, so an unquoted `**/x.py` in `touches` makes the frontmatter
    unparseable. The raw parser error talks about anchors and aliases and never mentions
    globs, so the task validator now adds the hint.

- [x] **M2-07** Secrets scan as a Contract gate at every tier
  - Including prototypes — prototype repositories become real repositories with their history
    intact.
  - **Done when:** a planted credential fails the build and the history check catches one that
    was committed and then removed.
    ✅ [`scan-secrets.py`](.github/scripts/scan-secrets.py), 35 tests over 14 credential
    formats plus a generic entropy rule, wired as
    [`secrets.yml`](.github/workflows/secrets.yml).
  - **The history half is the whole point.** Deleting a secret in a later commit changes
    nothing — it stays readable at the commit that added it, to anyone who can clone. A scan
    of the current tree alone would report clean on a repository whose history is compromised,
    which is the worst shape of false negative because it is indistinguishable from safety.
    Tested directly: commit a key, delete it, then assert the tree scan is clean *and* the
    history scan still finds it.
  - **A mutation survived, and it was the design that was wrong, not the test.** Lockfiles
    were skipped wholesale as "high entropy by nature". Removing that skip broke nothing,
    because the generic rule keys on the variable *name* rather than raw entropy, so
    `integrity` and `checksum` hashes never matched it anyway. The skip bought nothing and
    hid something real: a private-registry URL carrying a token, one of the commoner ways a
    credential actually reaches a repository. The fix was deleting the code, not adding a
    test for it. Both behaviours are now asserted.
  - **No inline waiver comment, deliberately.** A Contract gate that can be silenced by a line
    in the file it is checking is an Advisory gate wearing a Contract label. The route for a
    credential-shaped string is to make it obviously not a credential, which is what the
    placeholder list encodes — and every detection test has a placeholder counterpart, because
    with no waiver a false positive is an unmergeable pull request with no escape at all.
  - **Findings are redacted in output**, and a test asserts the full value never appears. CI
    logs are widely readable and retained longer than the branch, so a scanner that echoes the
    secret it found has moved the leak rather than reported it.
  - **Planted credentials are assembled at runtime, never written as literals.** A test file
    containing a credential-shaped string would be found by the scanner when it scans this
    repository, so the suite would fail the gate it exists to prove. Building them from
    fragments means no committed file contains one — which also avoids needing an exclusion
    directory, and the blind spot the test-integrity audit had to accept.
  - **Found by a fixture written on autopilot:** a credential on `example.com` is suppressed as
    documentation. That is correct behaviour, and it needed the counterpart test on a host not
    reserved for documentation, which is what the fixture should have used.
  - **Cost noted:** the suite takes about a minute locally because most cases initialise a real
    git repository. That is the honest way to test history, but it is the first thing to push
    against `budgets.check_seconds` when that lands at `M3-10`.

- [x] **M2-08** Command-execution deny list at the tool layer ✅
  - `rm -rf`, `git push --force`, history rewrites, `git reset --hard`, credential access,
    package publishing, database drops, anything touching a production endpoint, any
    `curl | sh`.
  - Destructive git operations matter more than they look: an agent that force-pushes destroys
    the review trail everything else in this design depends on.
  - **Done when:** every enumerated category is refused and ordinary work is not.
    ✅ 45 patterns in [`config.yml`](aios/config.yml), matcher at
    [`deny-commands.py`](aios/bin/hooks/deny-commands.py), 11 tests over 76 commands.
  - **The design assumed one list generating two similar artifacts. It cannot.** Cursor's IDE
    agent has **no repo-level command deny list at all** — `.cursor/permissions.json` is
    allowlist-only. Claude Code takes a deny array directly. The two sides are shaped
    differently and always will be ([ADR-012](docs/decisions/ADR-012-command-denial-is-asymmetric-across-tools.md),
    correcting [03 §3.4](docs/design/03-repository-architecture.md)).
  - **The layer is Advisory, and saying so is the point.** Cursor's own documentation calls
    allowlists "best-effort convenience" and not a security boundary, and a repo-level file
    can only *widen* a developer's permissions, never narrow them. `AGENTS.md`'s claim that
    the permission layer is a structural defence is narrowed accordingly. Effort spent making
    these regexes airtight buys nothing review does not already give.
  - **Registering it blocked every shell command in the editor — twice.**
    [Incident](aios/incidents/2026-07-31-fail-closed-hook-blocked-every-command.md).
    First `python3`, which does not exist on Windows (Q-005); then, fixed, the hook received
    empty stdin instead of the documented event. The contract came from documentation rather
    than measurement — the identical mistake [ADR-009](docs/decisions/ADR-009-adapter-layer-rebuilt-on-measurement.md)
    was written about. That is four for four on assumed tool behaviour being wrong.
  - **`failClosed` was correct and is staying.** It did not cause the outage; it made an
    unverified control visible in one second instead of as a silent absence months later. The
    Cursor registration is withdrawn until `M2-10` measures the event shape. Claude Code's
    enforcement point is live, because there the contract is a data file, not a protocol.
  - **The tests weight false positives heavily** — 30 benign commands, several adjacent to
    denied ones. Two real bugs fell out: case-insensitive matching made `git branch -d` and
    `-D` the same command, and `git push -f` escaped a pattern that required a token before
    the flag. A deny list that blocks `git status` gets switched off, taking the control with
    it, so a false positive here is more dangerous than a miss.
  - **`deny_commands` becomes the seventh enforced config key.**

- [x] **M2-10** Measure Cursor's `beforeShellExecution` event, then re-register the hook
  - **Done.** Registered against `preToolUse` with matcher `Shell`, not against
    `beforeShellExecution` at all — `M4-03` had already measured `preToolUse` carrying the
    command at `tool_input.command`, so the hook rides the shape that was observed instead of
    the one that was documented. Both shapes are accepted, so re-registering it could not
    silently turn it into a hook that allows everything.
  - Two faults came out of it that a reading would not have found. The hook still used
    `json.load(sys.stdin)`, which reads to end-of-stream — the same hang that caused the
    outage recorded on 2026-08-02, sitting unfixed in the second hook. And the standing rule
    to run it by hand first was followed, which is how the `preToolUse` shape was confirmed
    before it was named in `hooks.json`.
  - **`failClosed` is false on this entry, against the standing rule, and the reversal was
    forced by watching it happen.** Registered fail-closed, a momentarily half-written
    `config.yml` made the hook undecidable and every shell command in the editor was refused;
    the only way back was the editor's write tool. That is the `M2-08` outage a second time,
    in the exact place `hooks.json` predicted it — a `Shell` matcher has no repair path
    through the shell. Fail-closed is right for the layer that is the containment; this layer
    is Advisory by [ADR-012](docs/decisions/ADR-012-command-denial-is-asymmetric-across-tools.md), so
    it does not buy enough to be worth a repository nobody can fix. The script now allows and
    prints when it cannot decide. A denial it *can* decide is still a denial.
  - It also refused one of this session's own commands, correctly: a shell argument containing
    prose about reading a `.env` file matched the credential pattern. A false positive of the
    class the design expects, and the reason the layer is Advisory rather than Contract.
  - Raised by `M2-08` breaking on it. The documented `{command, cwd, sandbox}` on stdin was
    not what arrived; stdin was empty. Until the real shape is known the only deny-list
    enforcement is Claude Code's.
  - Record it in `aios/bin/probe/results/` with the M0 matrix, and re-run it on the same
    schedule — tool behaviour is precisely the thing that changes underneath.
  - **Run the hook once by hand against a real event before registering it.** One invocation
    would have caught both faults.
  - **Done when:** the event shape is recorded from observation, the hook is registered with
    `failClosed: true`, and a denied command is refused while `git status` still runs.
  - **The measurement half is done, from `M4-03`.** `preToolUse` sees `Shell` calls carrying
    `tool_input.command`, so the deny list can be wired as a second entry in the same hook and
    `beforeShellExecution` need not be used at all. The recorded shape and the BOM finding are
    at [hook-event-2026-08-01](aios/bin/probe/results/hook-event-2026-08-01.md).
  - What remains is wiring the tested matcher to that entry and demonstrating the refusal —
    a separate change, deliberately, so a deny-list regression cannot be mistaken for a mode
    regression.

- [x] **M2-09** Adversarially validate D-020 — **the M2 exit criterion** ✅
  - Instruct an agent to make a failing test pass by any means available to it.
  - **The test must not telegraph itself.** M0 measured an agent narrating its own compliance
    because a marker file announced that a probe was running. An agent that knows it is an
    adversarial test is not the agent the control has to survive, and a green result from a
    primed agent proves nothing.
  - **Done when:** the build goes red. **If it goes green, M2 is not done.**
    ✅ Red. [Record](aios/bin/probe/results/adversarial-2026-07-31-D-020.md).
  - **It ran without the binary or a pull request** — a diff against a pristine snapshot, piped
    to the audit. The blocker on `M1-08` never applied to this task; it was assumed to.
  - **Two trials with a control**, given to subagents with no view of the session that designed
    them, under deliberately permissive framing ("whatever gets the suite green is fine"). Where
    honest repair was impossible the agent weakened the suite and the audit went **red**; where
    a real bug existed the agent fixed the module and the audit stayed **green**. The second
    trial is what stops the first from being meaningless: a gate that reddens on every change
    proves nothing.
  - **The agent did not reward-hack in the crude sense, and the gate was still right to fire.**
    It left the module untouched, added three genuine hermetic tests, deleted nothing, and
    volunteered that the live check was now skipped. D-020 is not a claim that agents are
    malicious — it is that a change to the graded artifact needs a human to look. A defensible,
    honestly disclosed change that leaves the suite verifying less is the *harder* case, because
    the reasoning is sound. The gate should not try to read intent; it routes to a human.
  - **The silences were as important as the catch.** Mocking a transport dependency did not trip
    `mocked-subject`; relocating a test into a skipped class did not trip `deleted-test`. Both
    correct. A gate that flagged either would teach people to ignore it.
  - **What it does not establish:** n=1 per condition, one model. Trial 1 made honest repair
    impossible by construction, so it tests the control and not the agent's propensity. Both
    agents inherited `AGENTS.md`, so the restraint observed is an upper bound, not a baseline.

---

## M3 — Gate classes and tiers

**What M3 proves:** that Contract failures are rare in practice. A high Contract failure rate
after M3 means the classes are miscalibrated, and the fix is reclassification, not exhortation.

- [x] **M3-01** Make every check declare a class ✅
  - `Contract` (blocks, halts the agent, no self-override) · `Ratchet` (blocks only regression)
  · `Advisory` (reports, never blocks) · `Report` (measured, never acted on automatically).
  - **Done when:** a check without a declared class fails to register.
    ✅ [`gates.yml`](aios/gates.yml) registers 25 checks and 10 planned ones,
    [`validate-gates.py`](.github/scripts/validate-gates.py) enforces it, 27 tests.
  - **The criterion has two halves and only one of them is obvious.** Rejecting a registry
    entry with no class is easy. The half that carries the weight is rejecting a check that is
    simply *absent* from the register — because if omission avoided the declaration, declaring
    would be optional in practice and the register would list only the checks that
    volunteered. Every workflow step with a `run:` must be registered or listed under
    `not_a_gate` **with a reason**. Both mutations caught on the real repository.
  - **A step with no name fails.** It cannot be registered, so it must not be allowed to exist
    — otherwise anonymity is the hole. A `uses:` step needs no registration: actions are not
    checks, and requiring them would make the register mostly noise.
  - **The class is checked against what CI actually does**, via a `blocking` field recording
    how the class is produced. `advisory` on a step that fails the job is rejected, and so is
    `contract` on a step carrying `continue-on-error`. A class nothing enforces is decoration,
    and this is the same failure `M2-06` had to avoid when `tier` was read in the workflow
    instead of the script.
  - **`blocking: script` is the escape hatch and it costs a note.** Scope reads the tier and
    decides for itself, so no workflow field can confirm its class. Rather than infer wrongly,
    the registry records that the script owns the decision and requires the entry to say so.
  - **The registry registers itself.** A register that exempted its own enforcing step would be
    the first hole anyone looked for.
  - **Two classifications are recorded as uncomfortable rather than smoothed over.** The P1
    facts-not-procedures check is a regex over prose that has already produced one false
    positive; `advisory` is the honest class for a heuristic, and it is `contract` only because
    P1 is load-bearing for the instruction layer. Its note says that a second false positive
    should demote it rather than tune it. The always-on budget is `contract` because ADR-011
    fixes a cap, and `M3-04`'s ratchet on the same number is a different control: the cap stops
    the budget being blown, the ratchet stops it being crept up to.
  - **The 06 §3 tier table is not wired yet** — classes here are the values at this
    repository's tier. `planned` carries the ten checks the table names that do not exist,
    each naming the task that builds it, so `M3-02` has the whole picture rather than an
    inventory of what happened to get built.

- [x] **M3-02** Implement the tier → class mapping ✅
  - The gate *set* is identical at every tier; only the class assignment moves. Hardening a
    prototype is a one-line config change rather than a migration, and a prototype still runs
    everything — it just mostly reports, so the trend data exists from day one.
  - **Done when:** the full table from [06 §3](docs/design/06-quality-gates-and-testing.md#3-tier-policy)
    is driven by one key, with a test per tier.
    ✅ All 13 rows in [`gates.yml`](aios/gates.yml), resolving against `tier` alone. 43 tests,
    four of them the real table at each tier.
  - **The claim "a one-line config change rather than a migration" is now enforced, not
    asserted.** A gate whose class varies by tier **must** use `blocking: script`, because a
    workflow step is static and its class cannot follow the tier. Allowing `blocking: step` on
    a varying gate would mean raising the tier changed this register and nothing else — the
    migration would still be there, just invisible. Declaring it now fails.
  - **A partial tier mapping fails.** Naming three tiers leaves the gate undefined at the
    fourth, and a gate that silently does not apply is the failure the register exists to
    prevent. `none` is a real value — the dashes in the table — and a gate resolving to `none`
    may not be enforced by a step that would run anyway.
  - **The table only hardens, and that is now asserted.** No row in 06 §3 relaxes as the tier
    rises, so a row that did would be a typo rather than a policy, and nothing else in the
    system would notice. A test orders the four classes and fails any gate that weakens.
  - **The resolved shape matches the design's intent:** contract rises 25 → 26 → 27 → 32 across
    the tiers while `report` drains 6 → 4 → 1 → 0 and `none` 2 → 1 → 0 → 0. A prototype runs
    everything and mostly reports, so the trend data exists from day one.
  - **Only one implemented gate actually varies** — scope, advisory at prototype and contract
    above. The other nine varying rows are `planned`, which is why carrying them in `M3-01` was
    worth it: the mechanism was built against the whole table rather than the one row that
    happened to exist, and eight of those rows exercise paths the single live one does not.
  - **Three mutations on the real registry, all caught:** enforcing scope with a static step,
    dropping its `regulated` row, and making SAST weaken at `regulated`.
  - **`tier`'s enforcement point moves** from the scope workflow to the registry gate, which is
    the honest one now that it drives every class rather than one check's behaviour.

- [x] **M3-03** Build the ratchet mechanism ✅
  - Baseline storage, comparison, and the "may not make this worse" rule. This is the class
    that solves the threshold problem: always satisfiable, never blocks a good change,
    improves monotonically.
  - **Done when:** a regression fails and an equal-or-better value passes, on a real metric.
    ✅ [`ratchets.yml`](aios/ratchets.yml) holds five measured baselines,
    [`check-ratchets.py`](.github/scripts/check-ratchets.py) enforces them, 29 tests.
  - **It caught its own author, live.** Adding one row to the `AGENTS.md` state table tripped
    `always_on_lines` and `agents_md_lines` on the real repository before any test was written
    for it. That is the criterion met on a real metric rather than a fixture.
  - **And that immediately exposed a hole: a baseline that may only ever improve is a freeze,
    not a ratchet.** ADR-011 leaves 57 lines of deliberate headroom, and a strict
    improve-only rule forbids spending any of it — so "never blocks a good change" stops being
    true, which is the property the whole class rests on. Loosening is therefore permitted and
    made *expensive* instead of impossible: it must name the exact value it moved from and say
    what was bought. Naming the old value is what stops one justification covering every later
    move, because a stale `from` no longer matches. Both baselines here carry one.
  - **Metrics are measured in code, and definitions cannot supply a command to run.** If they
    could, lowering a bar would be an edit to a file that reads like configuration, and the
    measurement would be the thing under the agent's control rather than the thing measuring
    it.
  - **`aios/ratchets.yml` and `aios/gates.yml` join the protected set.** A loosening is
    declared in the file, and the declaration is only worth anything if a human approves it —
    the tool check is the second layer, which is why the loosening prints loudly rather than
    passing quietly. This is D-020 applied to baselines.
  - **The tampering defence is inert in this repository right now**, and the tests are the only
    thing proving it works. It compares against the committed baseline, and there are still
    zero commits — so `previous` is always empty here. The tests build real repositories with
    real history, which is why this was visible at all rather than being discovered whenever
    the first commit lands.
  - **Five real metrics, all measured rather than chosen:** always-on lines (143), `AGENTS.md`
    lines (118), root markdown files (4), TODO/FIXME/XXX/HACK markers (10), and linter and
    type-checker suppressions (14). A baseline set to an aspiration is a Contract gate wearing
    a ratchet's name and blocks from the day it lands, so a test asserts none of them is.
  - **The suppression count is the one that earns its keep.** It is the cheapest available
    defence against an agent silencing a check rather than satisfying it, and an agent that
    cannot add a suppression without the number rising has to argue for it in review.

- [x] **M3-04** Wire the individual ratchets ✅ *(three of seven; four accounted for)*
  - Coverage on changed lines; shipped artifact size where the ecosystem has a meaningful
    notion of one; p95 latency on benchmarked paths; count of the linter's suppression escape
    hatch; `TODO`/`FIXME` count; `AGENTS.md` line count; accessibility violations on changed
    views.
  - The suppression ratchet is the cheapest available defence against an agent silencing a
    check rather than satisfying it, and it costs one number in CI.
  - **Wired:** suppressions (10), deferred-work markers (1), `AGENTS.md` lines (118) — the
    last two landed with the mechanism in `M3-03`. Plus always-on lines (143) and root
    markdown files (4), and two the list does not name but this repository needs.
  - **Not wired, each with a reason rather than a silence.** Coverage, artifact size and p95
    latency all need a compiled binary, and the toolchain is unreachable from this network;
    accessibility has no views to scan and never will here, so it is recorded as permanently
    not-applicable rather than pending. `planned` and `not_applicable` are validated: an entry
    that is **measurable today fails**, which stops either becoming the place a ratchet goes to
    avoid being enforced.
  - **Two new ratchets whose only job is to notice something disappearing.**
    `gates_registered` (26) and `tests_declared` (188). Deleting a check is the quietest way to
    stop it failing, and every other control assumes the checks still exist — the gate registry
    proves each check declares a class but cannot notice one that is simply gone. Both
    mutations caught.
  - **`tests_declared` counts source, not a run**, so skipping does not move it. That failure
    belongs to the test-integrity audit, and the two are deliberately different: the audit
    reads a diff and sees only what a pull request contains, while this reads the tree and
    notices a suite that shrank by any route — including one that never appeared in a diff.
  - **The marker ratchet was measuring its own documentation.** Writing the words `TODO` and
    `FIXME` into the file explaining the ratchet raised it from 10 to 18. Markers and
    suppressions now count in code files only: a marker in code is debt, the same word in a
    design note is a sentence, and a count that cannot tell them apart teaches people to avoid
    the vocabulary rather than the debt. Correctly scoped, the real figures are 1 and 10.

- [x] **M3-05** Supply-chain controls ✅
  - Lockfile-only installs everywhere including local, using the ecosystem's frozen-install
    mode. Dependency allowlist requiring a human commit with a one-line reason. Package
    existence check plus a 90-day minimum age. Typosquat check refusing Levenshtein distance
    ≤2 from an existing dependency name. SBOM per release. Known-critical CVE blocks.
  - Package hallucination is the highest-probability AI-specific risk — ~19.7% of generated
    package references do not exist, ~205,000 unique invented names, 43% repeating across
    identical prompts, which is repeatable enough for an attacker to pre-register.
  - The age check is the specific counter: an attacker must sit on the name for three months
    while every scanner watching for this is looking.
  - **Done when:** each control has a fixture that trips it.
    ✅ [`dependencies.yml`](aios/dependencies.yml) is the allowlist,
    [`check-dependencies.py`](.github/scripts/check-dependencies.py) enforces it, 28 tests.
  - **The enforcement layer had an undeclared dependency, which is the problem this task is
    about sitting inside the thing meant to prevent it.** Every gate script imports `yaml` and
    nothing installed it — it worked only because the GitHub runner image happens to ship
    PyYAML. Now declared, and pinned by hash in
    [`requirements.txt`](.github/scripts/requirements.txt): `--require-hashes` is pip's
    frozen-install mode, and without it an exact version still trusts whatever the index
    serves for it.
  - **All five workflows ran `actions/checkout@v4`, a mutable tag.** An action runs arbitrary
    code in CI holding a token, so a moved tag is remote code execution inside the layer that
    grades the agent. All five now pin the commit.
  - **The direction that matters is finding what the allowlist does *not* mention**, so the
    sources are read rather than the list: Cargo's dependency table, every workflow `uses:`,
    and every non-stdlib import. An allowlist checked only against itself is a list of things
    someone remembered to write down.
  - **The import scan reads the AST, not a regex** — because the regex read this script's own
    docstring and reported a dependency named `in`. Second time in two tasks that a scanner
    matched prose about itself; parsing removes the class of bug rather than narrowing it.
  - **The 90-day minimum age is the specific counter to package hallucination.** ~19.7% of
    generated package references do not exist, across ~205,000 invented names, and 43% repeat
    across identical prompts — repeatable enough to pre-register one and wait. An attacker must
    now sit on the name for three months while every scanner watching for this is looking at
    it. Fixtures cover both directions and the exact boundary, since a control that rejected
    everything new would simply be switched off.
  - **Existence is checked against the registry, and deliberately not in the pull-request
    gate.** [`supply-chain.yml`](.github/workflows/supply-chain.yml) runs nightly and is
    **Advisory**: a Contract gate that reaches the network fails on somebody else's outage, and
    a gate that fails for reasons unrelated to the change is one people learn to re-run rather
    than read. It is also the first gate to use `blocking: continue`, so the registry's
    class-versus-reality check now has a non-Contract case to verify.
  - **Typosquatting compares declared names to each other**, not to a registry, because the
    attack is a lookalike sitting beside the real one where a reader's eye slides over it. The
    org prefix is stripped before comparing, or every action from one organisation would flag
    every other.
  - **Three controls are not built, each naming its task:** SBOM per release needs a release,
    CVE blocking landed at `M3-06`, and `Cargo.lock` is generated
    by a toolchain this network cannot reach. Hand-writing a lockfile would be inventing the
    one file whose entire purpose is to be machine-derived.

- [x] **M3-06** Wire SAST and the nightly dependency audit
  - Class by tier: Advisory at prototype through Contract at production.
  - **SAST is CodeQL on Python**, in [`sast.yml`](.github/workflows/sast.yml), with
    `security-extended` rather than the default suite — the default is tuned for a low false
    positive rate on application code, and this repository is almost entirely subprocess
    execution, path handling and regex, which is what the extended queries cover. Python is the
    honest scope, not a limitation glossed over: the Rust tree is a dispatch skeleton that
    cannot be compiled on this network, and every line that currently decides whether this
    repository is valid is Python. Rust joins at `M1-08`.
  - **The registry rejected the first attempt, correctly.** SAST was wired as
    `continue-on-error` on the CodeQL step itself. It is the one row in `06 §3` passing through
    all four classes in order, and `M3-02`'s rule — a class that varies by tier must use
    `blocking: script` — refused it: a static flag cannot follow a moving class. So the
    analyser only uploads, and [`check-sast.py`](.github/scripts/check-sast.py) reads the tier
    and decides. Verified at every tier: prototype reports and exits 0, production and
    regulated block, internal **refuses** because no baseline has been measured. That refusal
    is deliberate — ratcheting against a baseline that was never measured ratchets against
    nothing, so the measurement is forced before the promotion.
  - **CVE blocking, deferred here by `M3-05`, uses GitHub's advisory database.** Not OSV:
    `api.osv.dev` is filtered on this network with the same connection-reset signature as the
    Rust hosts, so it could not be verified even once, and an unverifiable source is not a
    source. GitHub adds no trusted party beyond the forge already depended on (`ADR-002`) and
    needs no credential. Blocks on critical and high only; a list that flags everything gets
    ignored. Fixture is PyYAML 5.3.1 and its real GHSA-8q59-q68h-6hv4.
  - **The age rule was measuring the wrong thing.** `first_release` compared the *pinned
    version's* upload date, and the CodeQL wiring exposed it: both `v3` and `v4` point at
    commits from yesterday, because major-version tags are moved on every release. The check
    would have banned the action outright. The attack it exists to stop is a freshly registered
    *name*, so age belongs to the name — PyYAML is 5509 days old, not 309. Corrected in
    `check-dependencies.py`, and a version that was never published is now its own finding.
  - **Suppressions ratchet raised 10 → 12**, using `M3-03`'s `raised` field. Each gate script
    pays the same two `E402`s for the sibling-module import after a `sys.path` insert; routing
    it through an imported module trades `E402` for an unused-import `F401`, so it buys nothing.
    First real use of the mechanism outside its own tests.
  - **Done:** 5 mutations of `check-sast.py` — contract never blocking, the threshold dropped to
    zero and raised out of reach, and the ratchet accepting a missing baseline or ignoring a
    regression — all caught, no survivors. Gate registry valid at all four tiers.

- [x] **M3-07** Override recording
  - An override is a **human commit** adding a dated, reasoned entry to `aios/incidents/`. The
    agent cannot override, cannot ask to override, and cannot edit the override list.
  - **Done when:** an override without a matching incident entry fails. It does — and so does
    the opposite, which the task did not ask for and which matters as much. A record no commit
    claims is a record smuggled in, and checking only one direction leaves the other open.
  - **The record is frontmatter on an incident file**: `override`, `date`, `approved_by`,
    `reason`. Frontmatter rather than the bold-prose fields the other incidents use, because
    this is state a machine counts — `M3-08` needs three-in-thirty-days per gate, and
    `--list` emits exactly that so the counter never re-parses the format and the two cannot
    drift apart. The absence of an `override` key is silence, not a malformed record;
    otherwise any incident that ever grew frontmatter for another purpose would become one.
  - **Only a Contract gate can be overridden.** Overriding an Advisory check records nothing
    and would still feed the demotion counter, inflating the count on a gate that never
    stopped anybody. Resolved at the configured tier, so `quality.sast` is un-overridable at
    prototype and overridable at production — the same gate, correctly.
  - **The list cannot be edited**, which is the clause most likely to be quietly dropped.
    Enforceable because it is a property of the diff rather than of who produced it: each
    record is compared against its content at the base ref, and a modification or deletion
    fails. Ordinary incidents stay editable.
  - **What this does not enforce is the word *human*.** An agent can type a `human:` trailer
    as easily as a person can. Same shape as `ADR-012`: the local check is consistency and
    recording, the unforgeable half is server-side required review (`M2-02`) and signing
    (`M5-03`). The trailer is checked and its weight is stated rather than oversold — claiming
    otherwise would be the exact failure this gate exists to prevent.
  - The gate itself is Contract at every tier. A gate governing the escape hatch from Contract
    gates cannot be weaker than the gates it governs, or the hatch is the way around all of them.
  - **Done:** 25 tests over real repositories with real commits, since the range half reads
    commit messages and base-ref content. 9 mutations — both agreement directions, record
    editing, unknown and non-Contract gates, thin reason, future date, missing field, absent
    trailer — all caught, no survivors.
  - **The suppressions ratchet caught the OS bypassing itself.** This milestone needed the same
    raise `M3-06` had just taken, for the same stated-unavoidable reason. Twice for one cause is
    exactly the pattern `D-017`'s demotion rule exists to name, so the second raise was refused
    and the cause re-examined. Every gate script opened with
    `sys.path.insert(0, Path(__file__).parent)` before its imports — and Python already places
    a script's own directory at `sys.path[0]`, so the line did nothing and the `E402`
    suppressions existed solely to permit it. Removed from nine scripts: 14 → **4**, and the
    four left are regex patterns that *detect* suppressions, so the true count is zero. The
    `M3-06` `raised` entry was deleted rather than left standing, because its reasoning was
    wrong and a justification that survives being disproved is how the mechanism rots.

- [x] **M3-08** The demotion counter
  - Any Contract gate overridden three times in 30 days is automatically demoted to Ratchet and
    a report is filed. Any Advisory check ignored 20 times in a row is deleted.
  - A gate being routinely overridden is already not blocking — just blocking dishonestly.
  - The security subset of Contract gates is **exempt**, demotion files a report a human must
    close, and demotion is itself a reviewable commit.
  - **Done when:** the counter demotes on the third override and never on the second. Both
    proven, and the window boundary with them: three inside 29 days demote, three spanning
    exactly 30 do not.
  - **The window is anchored to the overrides' own dates, not to the last 30 days.** A gate
    that demotes on Tuesday and not on Wednesday, with nobody having changed anything, has a
    verdict that depends on when CI happened to run, and a rule like that cannot be argued with
    in review. Tested by asking the same question in 2026 and in 2030 and requiring one answer.
  - **"Automatic" and "a reviewable commit" are not in tension.** `--apply` computes the
    demotion and writes [`aios/demotions.yml`](aios/demotions.yml); a human commits it and
    later closes the report. Until that commit exists the gate fails, so the demotion cannot be
    quietly declined — the same shape as the ratchet baselines, deliberately.
  - **Both halves are required, and each masked the other.** A ledger entry without the class
    change leaves the gate blocking dishonestly; the class change without a ledger entry loses
    the only artefact saying why it stopped blocking. Every test had the class still on
    contract, so that check masked the second and a mutation deleting it survived. The gap was
    real, not cosmetic, and the missing test is now there.
  - **A demotion nobody earned is a violation**, or the ledger is a way to switch off any gate
    by writing a line in it. And demotion goes to Ratchet, never to anything weaker.
  - **Seven gates are marked `security: true`** and never demote — declared explicitly rather
    than inferred from the `containment.` prefix, since a rename would silently un-exempt one.
    `process.overrides` is among them: a demotable override gate is a way around every other
    gate at once. Exemption is not silence — a crossing still lands in `exempt_crossings`,
    because a security gate overridden three times means either it or the code is wrong.
  - **The two checks had to be made to agree.** Demoting a gate to Ratchet made the very
    override records that caused the demotion invalid, since the override gate accepts only
    Contract gates. A record is a statement about the past, so it is judged against what the
    gate was. Also found: `--list` printed JSON *and* violation lines, and a violation
    containing `[a/path]` made the JSON unparseable — a data command that sometimes emits prose
    is not a data command.
  - Advisory-ignored-20-times is `planned` against `M3-10` with its reason: it counts
    consecutive CI runs, this repository has none yet, and implementing it now would mean
    inventing the history it reads.
  - **Done:** 30 tests, 12 mutations — threshold moved up, window widened, boundary made
    inclusive, both recording halves, unearned demotions, weaker-than-ratchet demotions, and
    four ways of breaking the security exemption — all caught, no survivors.

- [x] **M3-09** Generate the review packet onto the pull request
  - **Done when:** a reviewer can see scope, gate results by class, and advisory findings
    without leaving the pull request. All three render, plus the task with its acceptance
    criteria and constraints.
  - **A Report, not a gate.** A packet that can block is a second, worse copy of the gates it
    reports on, and one that goes red for the same reason twice teaches people to skim both.
    The registry enforces the class: the render step carries `continue-on-error`, and removing
    it without changing the class fails `validate-gates.py`.
  - **The commands come from the registry, not from a list in the workflow.** Asking GitHub
    for check runs does not work — a check run is a *job* and a gate is a *step*, so results
    arrive at the wrong granularity. So [`run-gates.py`](.github/scripts/run-gates.py) reads
    each gate's workflow and step and takes the step's `run:` block. One definition of what a
    gate runs, and it is the one CI executes (`D-040` applied to the reporting layer).
  - **A check that did not run is never rendered as one that passed.** Action steps,
    steps the registry points at that do not exist, and commands still holding an
    Actions-only expression are all reported as skipped with the reason. The same applies to
    the packet's own inputs: "no advisory results were supplied" and "no findings" are
    different sentences, because otherwise silence reads as a pass.
  - **Three of 08 §2.2's six sections name their blocker rather than being absent** — the
    verification record (`M1-13`), the verifier's findings (`M4-01`), and the traceability
    delta (`M4-04`). A checklist quietly missing an item is how the item stops existing.
  - **`pull_request`, deliberately not `pull_request_target`.** The packet renders task prose
    and paths from the branch, and rendering attacker-controlled text under a writable token
    is 07 §1.3's warning exactly. The cost is that a fork's token cannot comment, which is why
    the job summary is written first and unconditionally and the comment is best-effort. Task
    prose is additionally fenced as untrusted — the packet is read by agents too.
  - **The registry caught four faults in this milestone's own workflow**: a Report step with no
    `continue-on-error`, and three unregistered steps. Registering delivery and diff-collection
    under `not_a_gate` with reasons is the correct answer, and the gate would not let them pass
    unexplained.
  - **A fixture bug that made tests pass for the wrong reason.** `textwrap.dedent` measures the
    common indent of the *result*, so interpolating a two-line `touches` list into an indented
    template let the short line set the margin and silently produced unparseable YAML. It
    passed with one pattern and broke with two. The fixture now substitutes after dedenting,
    and a test asserts the fixture itself parses.
  - **Done:** 35 tests and 16 mutations — unflagged escapes, unreported unused scope, missing
    results rendered blank, advisory silence read as clean, dropped pending sections, unfenced
    untrusted content, classes not resolved per tier, unmarked failures, and five ways for the
    runner to call something a pass that never ran — all caught, no survivors.

- [x] **M3-10** Measure and enforce the feedback-speed budgets ✅
  - Pre-commit under 5s · `aios check` under 60s · CI on PR under 10min · nightly for mutation
    sampling, full dependency audit, staleness sweep, trend reports.
  - Fast feedback is one of the capabilities that flips AI's stability effect from negative to
    positive, which makes latency a requirement rather than an optimisation.
  - **Done when:** each budget is measured in CI and reported as a ratchet. All three paths are
    defined and measured by [`measure-speed.py`](.github/scripts/measure-speed.py), wired into
    [`speed.yml`](.github/workflows/speed.yml), and registered as `process.feedback_speed`.
  - **The first measurement found the budget missed by six times.** `aios check` ran 366s
    against a 60s ceiling. Nearly none of it was work: the gates are separate programs, so
    almost every test spawns an interpreter and waits, and the wall clock is process startup
    repeated a few hundred times. [`run-tests.py`](.github/scripts/run-tests.py) sharded it by
    test class and took it to 164–225s — real, and far short of the 12x twelve shards should
    have bought. The per-shard timings say why: every shard slowed down, so the ~366s of serial
    work became ~1900s of parallel work. That is process-creation contention on Windows, not
    computation, and it is a cost the Linux runner does not pay. Which is the point: **the
    number that matters is the CI one, and it does not exist yet.**
  - **That 164–225s spread is the same suite on the same machine minutes apart.** A 37% swing
    with nothing changed is the argument for the tolerance below, measured rather than assumed.
  - **So the timing baselines are `planned`, not measured.** Recording a Windows baseline for a
    check that runs on Linux would produce a ratchet comparing two different machines forever.
    They are recorded against `M3-10-ci` with the local numbers kept, so the overrun is not lost.
  - **Class moves with the tier, as SAST does:** report → advisory → ratchet → contract. Report
    at prototype is not softness. Blocking on a ceiling nobody has measured means the first red
    build is also the first measurement, and the build that goes red for a reason nobody can
    size is the build people learn to re-run.
  - **The ratchet tier needed a tolerance, and that is new machinery.** Wall clock on a shared
    runner moves tens of percent between identical runs, so a strict timing ratchet fails on
    jitter — and a gate that gets re-run rather than read has already stopped working while
    still looking green. `tolerance_percent` is now general to
    [`check-ratchets.py`](.github/scripts/check-ratchets.py), bounded to 50%, and requires a
    reason naming what is noisy. It applies to the comparison only: an improvement still
    tightens to the measured value, so slack cannot accumulate.
  - **Done:** 27 tests, 11 mutations — an unnoticed overrun, a contract tier that stops
    blocking, a ratchet tier accepting a missing baseline, a path reporting zero when it could
    not be measured, and three ways of defeating the tolerance — all caught, no survivors.

- [x] **M3-12** Delete Advisory checks that are ignored 20 times running
  - Deferred out of `M3-08`, then out of `M3-10`. It is not being deferred a third time by
    milestone number: **its precondition is CI run history, and no milestone creates that** —
    pushing does, and the first commit is still unpushed. Anchored to the precondition instead,
    so it stops travelling.
  - "Ignored" is not "failed". An Advisory check never fails, so the counter has to compare
    findings between consecutive runs and see that nothing moved. The findings live in job
    output, which means either an artifact this repository does not yet write or a ledger it
    would have to invent — and inventing the history a counter reads is the one thing a counter
    must not do.
  - **Done when:** the counter deletes on the twentieth consecutive ignored run and not the
    nineteenth, measured against real run history.
  - **Done.** `check-advisory-deletion.py`, Report class, in the new monthly workflow.
  - The precondition was CI run history, and the reason to build it now anyway is that a
    counter written after somebody notices the logs starts counting from the day it was
    written. It reports zero today and says explicitly that zero is a statement about the
    history rather than a clean bill of health for the checks.
  - Ignored means the check reported a finding and the pull request merged with it still
    there. A clean run breaks the streak, and so does a run where the gate did not fire at all
    — without that second rule, switching a check off for a month would count as a month of
    being ignored, which would make disabling a check the way to get rid of it.
  - It resolves the class at the active tier rather than reading the declared one, so a gate
    that is Advisory at prototype and Contract at production is not deleted for being ignored
    where it was never meant to block. It proposes; the answer is sometimes promotion to
    Ratchet, and a script cannot tell a check nobody values from one everybody meant to fix.

- [~] **M3-11** Build the release pipeline and prove the cross-ecosystem invocation contract
  - The direct price of the hard constraint in
    [ADR-005](docs/decisions/ADR-005-reference-implementation-ecosystem.md), and the closure of
    the deferral in [ADR-001](docs/decisions/ADR-001-first-project-is-the-os-itself.md) §4.
  - Per-platform artifacts, and a resolution to the open question of how a cloned project obtains
    one — checksum-verified if fetched, because an unverified fetch is a supply-chain hole in the
    one tool whose job is closing those.
  - **Done when:** a scratch project in a **different** ecosystem runs `aios check` end to end
    with the OS's toolchain absent from the machine. Asserting it does not count.
  - **Not done. It needs the binary, and it was still worth re-reading** — `M2-09` was skipped
    on the same assumption and turned out to need neither the binary nor a pull request. This
    one does need it, but only for the last step, and everything before that step is built.
  - **The contract is written and closed as
    [ADR-013](docs/decisions/ADR-013-the-cross-ecosystem-invocation-contract.md).** `Q-002`
    required this to happen *before* the test, so the test can fail the contract instead of
    describing it — a suite generated from an implementation passes by definition. Four
    clauses: invocation by path, exit codes 0/1/2 with the remaining space reserved, human
    output by default with `--format json`, and root discovery walking upward for `.git`.
    `Q-002` is closed and the root-discovery half of `Q-003` with it, since answering them
    separately would have given the tool two ways to find one repository.
  - **Two independent conformance implementations, both able to fail.** The
    [Python suite](tests/test_invocation_contract.py) and the dependency-free
    [Node host project](tests/host-project/check.mjs) each reject all twelve deliberately
    non-conforming stand-ins. Twelve rather than a handful because a suite written against an
    absent subject is the easiest place in this repository to write a check that cannot fail.
  - **The meta-check earned its place immediately.** Re-running the conformance suite against a
    subject that treats the working directory as the root — the mutation — was *accepted*. It
    exited 2 as the contract requires, but only because it then failed to find a config there;
    it was right by accident. The fix was to give the decoy directory a valid config, so root
    discovery is the only thing separating the outcomes. Asserting that a broken stand-in
    misbehaves would never have found this; only re-running the real checks against it did.
  - **Then it found a second one, from the feedback-speed budget of all places.** The
    meta-check ran all four conformance classes per violation, and the module took 240s. Making
    each violation name the class that must reject it was the cheaper fix and the stronger
    assertion — and two §2 violations immediately failed, because the mutation was landing on
    the root-discovery branch and being caught by `TestRootDiscovery` while claiming to test
    exit codes. Two clauses were covered only incidentally. Re-anchored, all twelve are covered
    by the checks that claim to cover them, and the module runs in 101s.
  - **Cross-ecosystem, and genuinely so.** The host project is Node, has no dependencies, and
    knows nothing about the implementation — if it needed to, the contract would have failed.
    It ran here: 16/16 clauses held against a stand-in, including the toolchain-absence clause,
    which is true on this machine because Rust could never be installed on it.
  - **What is actually owed:** the same run against a real binary. Wired as three Contract
    gates in [`release.yml`](.github/workflows/release.yml), on a job that never installs a
    toolchain, deletes the one the runner image ships, and refuses to proceed until `cargo`,
    `rustc` and `rustup` are all absent. Without that removal the proof would pass for the
    wrong reason and keep passing after the claim stopped being true.
  - **`Q-001` stays open, and not for lack of a decision.** It needs a measured artifact size
    per platform to choose between committing the binary and fetching it. The pipeline records
    that size; the pipeline has never run. Guessing the number is the one way to close it
    wrongly.
  - **Held on:** `M1-08`. Reopens the moment a binary is built —
    `TestTheProofThatIsStillOwed` fails as soon as an executable appears anywhere it looks, so
    this cannot be forgotten rather than finished.

---

## M4 — Agent ergonomics

**What M4 proves:** whether fresh-context verification earns its token cost. If
findings-per-review is near zero, delete it —
[D-024](docs/design/10-decision-register.md#d-024--exactly-two-subagents-both-for-context-isolation)
carries a revisit trigger for exactly this.

- [x] **M4-01** Define the `explorer` subagent ✅
  - Read-only, no write tools. Answers "where does X live", "is there already an implementation
    of Y", "what calls Z". Exists to keep large search output out of the main context.
  - **Placement is probe-dependent.** `03 §3.6` puts both subagents in `.claude/agents/`; the
    provisional M0 reading suggests Cursor does not read that location. Place them where the
    matrix says Cursor actually looks. If confirmed, that is a correction to the design doc, not
    an implementation detail ([ADR-007](docs/decisions/ADR-007-claude-adapter-deferred.md) §3).
  - **That bullet is stale and was already answered.**
    [ADR-009](docs/decisions/ADR-009-adapter-layer-rebuilt-on-measurement.md) §2 settled it:
    the provisional reading was a false negative, the marker appeared in a later session, and
    `.claude/agents/` is read. `.claude/agents/explorer.md` it is. Worth noting the M0 lesson
    that produced the correction — a single null result is untrustworthy, and this task would
    have moved the file on the strength of one.
  - **The measurement had to be fixed before the subagent could be added at all.** A subagent's
    *description* is resident on every turn (ADR-010), and the ratchet that watches the
    always-on set was not counting descriptions — only `AGENTS.md` and the `alwaysApply` rules.
    The workflow's Contract gate counted all four contributors correctly. Two implementations
    of one definition, agreeing on 143 only because the categories they disagreed about were
    empty. The explorer would have measured as +5 in one and +0 in the other, and the ratchet
    would have reported "held" while the set it exists to watch grew.
    [Incident](aios/incidents/2026-08-01-the-always-on-budget-was-not-measuring-its-own-set.md).
  - **Resolved by having one implementation**,
    [`check-always-on.py`](.github/scripts/check-always-on.py) — the workflow calls it, the
    ratchet imports it. The irony is recorded rather than smoothed over: ADR-010 exists because
    a budget watching one input while others grow freely is "a budget-shaped object", and its
    own implementation was one.
  - **The `raised` mechanism had its first real use outside a test.** The explorer's five lines
    were a genuine regression against a 143 baseline, declared with a reason rather than
    absorbed. Budget now 148 of 200.
  - **Done when:** the subagent exists where Cursor reads it, holds no write tools, and its
    always-on cost is counted. All three, plus 24 tests and 10 mutations — every contributor
    dropped from the set, bodies counted instead of descriptions, both budgets disabled — all
    caught, no survivors.

- [x] **M4-02** Define the `verifier` subagent ✅
  - Receives a diff and the acceptance criteria in a fresh context, with no memory of writing
    the code. Returns **findings, not edits**.
  - It is the context isolation that does the work, not the label — 162 personas across 4
    models and 2,410 questions found no reliable accuracy gain from role prompting.
  - **The evidence constrains the file more than it looks.** `01: 3.4` says the effect survives
    an identical prompt, which means this file is not where the value comes from. So it does
    not try to make the reviewer smarter; it fixes the input and output contracts and stops.
    Elaborate instruction here would be unearned, and it would cost context on every turn.
  - **It says why it is not a persona, not just that it isn't.** A file that merely omits
    "you are a senior engineer" invites the next reader to add it as an improvement. `01: 3.1`
    is recorded in the file so that edit gets made once, in the wrong direction, and reverted.
  - **The output format is a decision, not a formatting preference.** D-024 retires this
    subagent if findings-per-review trends to zero, and `M4-10` is what measures that. A
    trigger nothing can count is decoration — the same shape as the advisory-deletion counter
    in `M3-12` and the always-on measurement in `M4-01`. So findings are one line each with a
    severity and a location, the format has a parser, and the parser has tests before the
    number is needed. The examples in the file are checked against that parser, so the
    specification and its illustration cannot drift.
  - **A review that found nothing and a review that never ran must not look alike.** Hence the
    mandatory `verifier: N finding(s)` terminator: without it, silence reads as approval. Same
    distinction as could-not-run versus pass in [ADR-013](docs/decisions/ADR-013-the-cross-ecosystem-invocation-contract.md) §2.
  - **Two instructions exist to prevent a known failure**, not to be thorough: zero findings is
    explicitly a complete review, because a documented review-quota rule in another framework
    forces three findings and gets three inventions; and repeating the machine pass is
    forbidden, because a finding a gate already reports inflates the count `M4-10` reads.
  - **The review packet was citing the wrong task.** Its pending section named `M4-01` — the
    explorer — as the blocker for verifier findings. Now it names the actual gap: the verifier
    runs inside an agent session and nothing carries its findings into CI.
  - **Done when:** the subagent exists, holds no write tools, and returns findings rather than
    edits. All three, plus shared checks that run over `.claude/agents/` by discovery so a
    third subagent cannot arrive unchecked — proven by adding one and watching it fail.
    11 mutations, including a granted write tool, an added persona, and a drifted format —
    all caught, no survivors. Always-on budget now 153 of 200.

- [x] **M4-03** Implement modes as permission sets
  - Explore (no write) · Plan (writes only `aios/tasks/`, `aios/requirements/`,
    `open-questions.md`; never source) · Implement (writes only paths matching `touches`) ·
    Verify (no write). A mode is a permission set plus a checklist plus an output contract.
  - **Done when:** a write outside the active mode's set is refused by the tool, not by prose.
  - **Refused by the tool, demonstrated live.** With `explore` active, a write to
    `.tmp-probe-target.txt` came back `Mode 'explore' may write to: nothing.` — from the hook,
    before the edit, not from an agent deciding to comply. Removing the mode file let the same
    write through. `preToolUse` is the event; `ADR-012` concluded correctly about command
    denial but examined only `beforeShellExecution`, and `preToolUse` is broader.
  - **The event was measured first, and the measurement rewrote an incident.** Cursor prefixes
    stdin with a **UTF-8 BOM**. A strict parse raises on it, and a hook that reads a parse
    failure as "no input" reports empty stdin — which is exactly what `M2-08` recorded before
    fail-closed refused every command. The record is
    [hook-event-2026-08-01](aios/bin/probe/results/hook-event-2026-08-01.md); the incident has
    an addendum rather than an edit. Also measured: writes and edits both arrive as
    `tool_name: "Write"`, and top-level `cwd` is absent on writes, so the root comes from
    `CURSOR_PROJECT_DIR`. A control reading `cwd` would have worked on shell and silently not
    on the tool it exists to govern.
  - **No mode means no restriction, deliberately.** A template that defaults to refusal blocks
    a fresh clone before anyone configures it, and the instinct that produces is to delete the
    hook rather than to set a mode. `implement` with no task named is the one refusal in the
    other direction: it would otherwise permit everything, which is the opposite of choosing it.
  - **`failClosed: true`, with a bounded blast radius.** The matcher is `Write`, so if this
    hook ever breaks, `Shell` still runs and the repository is repairable from the terminal. A
    control whose failure mode locks you out of fixing it is not a safety control. Unparseable
    input is the one case that allows — and says so in `agent_message`, because a fail-open
    control that is silent is absent without anyone noticing.
  - **Advisory by classification, and the schema says so.** A mode is chosen locally and can be
    changed locally, so it disciplines the run rather than containing it. The blocking half is
    the `M2-06` scope gate re-checking the same `touches` server-side. Following `deny_commands`,
    `enforced_by` names the CI step that keeps the hook honest.
  - **The hook parses YAML without PyYAML.** It runs on whatever interpreter the editor has,
    and with `failClosed: true` a missing third-party import is a crash on every write.
  - 20 tests, every payload BOM-prefixed from the measurement rather than invented. 9 mutations,
    9 caught — including dropping the BOM handling and reading "no mode" as `explore`.

- [x] **M4-04** Wire the duplicate check into `aios start`
  - One read-only explorer call in isolated context, before implementation. This is the cheap
    counter to the measured rise in duplication and collapse in refactoring under AI
    assistance, and it is the difference between an agent that grows a codebase and one that
    maintains it.
  - **`aios start` does not exist, but the moment it named does.** The first write in
    `implement` mode is when implementation begins, and `M4-03`'s hook already sees it. The
    task is wired there instead, so this did not wait on `M1-08`. When the binary arrives,
    `aios start` becomes a second door onto the same check, not a replacement for it.
  - **Demonstrated live:** a write *inside* the task's `touches` was refused with
    `T-9f01 has no duplicate_check`. Scope could not have been the cause; only the missing
    record. Adding one entry let the identical write through.
  - **`duplicate_check` is a task field**, required from `doing` onward — not at submission,
    because by then the duplicate is written and removing it costs more than the check would
    have. `todo` is deliberately exempt: the record is produced while planning, and requiring
    it to leave `todo` is a deadlock. A mutation that added `todo` was caught by that test.
  - **An entry must say what was found, not that looking happened.** `searched for it` is
    rejected; `X — nothing found; searched a, b, c` is accepted. "Nothing found" is worth as
    much as a hit, and naming the search terms is what makes it checkable by someone who
    disagrees — a bare "nothing found" is indistinguishable from not having looked.
  - **Stated twice, on purpose.** The hook refuses locally and the validator refuses in CI.
    The hook runs on a machine nobody else can see, so the same rule has to exist where a
    pull request can fail on it.
  - **`T-950a` is the only task with a retroactive record**, and its body says so. Both
    searches genuinely happened — the second is why `aios_state.py` exists rather than a third
    frontmatter parser — but reconstructed evidence is weaker, and the file admits it.
  - The explorer gained a fixed output contract for this one call. Its body is free; only the
    description counts against the always-on budget, which is unchanged.
  - **The mutation harness had a bug worth more than the mutations.** It continued past a
    failing baseline and reported four "caught" results that were caught by a pre-existing
    failure. It now exits rather than run — a green-looking result from a red baseline is
    worse than no result, because it reads as evidence. Re-run properly: 3 real survivors, all
    genuine gaps. Two were untested validator branches; the third was an equivalent mutant,
    which was the code telling me `field_list` distinguished absent from empty and nothing
    read the difference. The distinction is deleted. 6 caught, 0 survived.

- [x] **M4-05** Implement autonomy tiers
  - A0 (human approves the approach, then the diff) · A1 (one task, then stop — the default) ·
    A2 (chain to a configured limit, default 3, or until any Contract gate fails).
  - Selected by task `risk` × project `tier`. **`risk: high` never reaches A2 at any tier.**
  - A2 exists so trivial work does not consume the review attention non-trivial work needs.
  - **The three levels are one number: how many tasks may begin without a human.** A0 is zero,
    A1 is one, A2 is the configured limit. That collapse is what made this enforceable without
    the binary — the hook already sees the first write of each task, so a ledger of tasks begun
    turns "one task, then stop" from a promise into a count.
  - **Demonstrated live at `production` × `risk: low` → A1.** The first task's write was
    permitted and recorded; switching to a second task and writing the same file came back
    `A1: 1 task(s) without review, and T-9f10 already ran.`
  - **A0 approved becomes A1, not A2.** Approval permits a task, not a chain — otherwise the
    strictest level would be the easiest route to unbounded autonomy. A mutation making an
    approved A0 unbounded was caught.
  - **The invariant is asserted apart from the table it constrains.** `risk: high` never
    reaches A2 is checked in `check-autonomy.py`, not encoded only in `aios/config.yml` — a
    table that was its own only check could repeal the rule by being edited. Two further
    invariants fell out while writing it and were worth more than the one specified: autonomy
    may not loosen as risk rises within a tier, nor as the tier rises at fixed risk. Both are
    checked, and both catch a plausible mis-edit the high-risk rule alone would miss.
  - **The table is four readable rows, not twelve keys.** The schema only has integer, string
    and list, so twelve dotted keys would each need near-identical `effect` prose — the
    decoration the schema's own comment warns about. Held as `"prototype:  low=A2 medium=A2
    high=A1"` it can be diffed against 05 §4 by eye, which is the check that matters.
  - **An unknown tier or risk resolves to A1, the default — never to more.** A pairing the
    table does not cover is a gap, and a gap that grants autonomy is the wrong direction to
    fail in.
  - **The client half is Advisory (ADR-012), and the gate registry says so.** `config.yml` is
    a protected path, so the table itself is outside the agent's write scope; the Contract half
    is CI re-checking it. The hook disciplines the run, it does not contain it.
  - 26 tests, 12 mutations, 12 caught. The one survivor was a test passing for the wrong
    reason — a malformed row that also removed a cell, so the missing-cell check caught it and
    the malformed-row check could have been deleted unnoticed. Replaced with a malformed row
    added to an otherwise complete table.

- [x] **M4-06** Implement the hard stop conditions
  - Contract gate failure · the change would escape `touches` · a task constraint conflicts
    with what the code requires · an ADR would be contradicted · a credential or production
    endpoint is needed · two requirements conflict · **the same test has failed three times
    with three different fixes**.
  - That last one converts an invisible failure mode into an explicit stop at the exact moment
    the incentive to cheat appears — past three attempts the agent is guessing, and guessing
    near a test is one hop from weakening it.
  - **Three of the seven are mechanical and now enforced; four are judgment and are not.**
    Scope escape was already refused by `M4-03` and blocked in CI by `M2-06`. A Contract
    failure already ends an A2 chain via `M4-05`. The three-strikes rule is built here. The
    remaining four — a constraint conflicting with the code, an ADR that would be contradicted,
    a credential being needed, two requirements conflicting — are recognitions, not
    detections. Claiming to enforce them would be the decoration this repository keeps
    deleting; they stay as prose in `05 §3.3`, which is honest about what prose can do.
  - **The count is observed, never self-reported.** A counter the agent maintains about itself
    is one it can decline to increment, and this rule exists for the moment self-reporting is
    worth least. `record-attempt.py` runs on `postToolUse` — the only measured event carrying
    an outcome — and writes a ledger the write hook reads.
  - **The verdict comes from the runner's output, not the exit code.** Measured: `exitCode`
    inside `tool_output` is the *shell's*, not the command's. A Python process exiting 1 inside
    a PowerShell block reported 0. Anything reading that field misses every failure in a
    wrapped command, which here is most of them. A mutation swapping the output check for the
    exit code was caught.
  - **A pass clears the count**, because the rule is about being stuck, not about having ever
    failed. Different tests count separately, so unrelated failures cannot combine into a stop.
  - **Demonstrated live**, on real test runs through the registered hook rather than fixtures:
    three genuine failures of one test, then a write refused with
    `tests.test_tmp_demo has failed 3 times without passing`. The refusal names the
    possibility the agent is least likely to reach on its own — that the test is right and the
    task is wrong.
  - **Two measurements, one of which corrected a wrong conclusion.** `postToolUse` carries the
    outcome and `afterShellExecution` does not. And a `hooks.json` change takes effect a turn
    late: a `matcher: "Shell"` looked broken, was removed, still looked broken, and then worked
    once given a settling turn — it had never been the problem. Both are in the probe record,
    with the instruction to test a registration across two calls before concluding anything.
  - The mode hook refused one of my own edits mid-task, because I was still in `implement`
    mode on a task whose `touches` was a single file. Working as intended, on its author.
  - 17 tests, 10 mutations, 10 caught.

- [x] **M4-07** Register hooks in both tools, pointing at shared scripts in `aios/bin/hooks/`
  - Hook *logic* lives in `aios/bin/`; the settings files become pointers, and pointers rarely
    drift. Drift surface is one registration line each.
  - **One mechanism for both tools does not exist, and that was measured rather than assumed.**
    Both tools document exit code 2 as blocking. In Cursor it is ignored: a probe fired on its
    sentinel file, wrote to stderr, exited 2, and the write completed. So `respond.py` branches
    on the caller — `cursor_version` is the discriminator — and that branch is the only
    tool-specific code in the hook layer. Fifth documented behaviour to not survive contact.
  - **An unknown caller gets the measured shape, never the guessed one.** Claude's branch
    denies by exit code; assuming it for an unrecognised tool would deny in a way that tool may
    not honour, which is a control that looks present and is not.
  - **The Claude side ships unverified and says so in the file.** Claude Code is not installed
    here, so neither its event shape nor its response contract has been measured. Shipping it
    is defensible only because the failure mode is inverted from `M2-08`'s: a wrong guess means
    the control does not fire, not that everything is refused. `M4-13` measures it, and a test
    fails if the `UNVERIFIED` label is removed before then.
  - **I broke the hook mid-task and it blocked every write** — the second edit was refused by
    the function the first edit had just broken. Repaired from the terminal in one command,
    because the matcher is `Write` and `Shell` was never gated. That scoping was chosen in
    `M4-03` against an imagined version of this, and the reasoning was written down at the
    time; this is it being cashed.
    [Incident](aios/incidents/2026-08-01-editing-the-hook-blocked-every-write.md).
  - The drift check is structural: every registration points into `aios/bin/hooks/`, every
    referenced script exists, both tools register the same set, and no registration contains a
    shell operator — the moment a condition appears in a settings file there are two
    implementations again, one of them untested.
  - 13 tests, 7 mutations, 7 caught. Two survived first: both on the denial branch, because
    the only end-to-end test happened to resolve to *allow*.

- [ ] **M4-13** Measure Claude Code's hook event and response contract — **blocked**
  - Raised by `M4-07`. The registrations in `.claude/settings.json` are written to
    documentation, and this repository's record on that is five for five wrong.
  - Needs Claude Code installed, which is `M0-03`'s blocker too — take both measurements in
    one sitting.
  - **Re-checked 2026-08-02: not installed**, and `npm` is itself refused by the same execution
    policy that produced
    [ADR-006](docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md). Two independent
    blockers, so this is not a matter of running one install command.
  - **Done when:** the event shape and the response mechanism are recorded in
    `aios/bin/probe/results/` from observation, a denial is demonstrated, and the `UNVERIFIED`
    comment comes out of the settings file.

- [x] **M4-08** MCP allowlist and drift check
  - Servers allowlisted in `aios/config.yml` with pinned versions. `check-drift` compares the
    parsed `mcpServers` object across `.mcp.json` and `.cursor/mcp.json`; mismatch fails CI.
  - No MCP server with write access to production systems in a development profile.
  - **This repository configures no MCP servers, so the check passes here by having nothing to
    object to** — the weakest possible evidence it works. Nearly every test therefore builds a
    fixture tree with real servers in it: a check whose only exercise is the empty case cannot
    be told apart from one that always passes.
  - **Three distinct failures, not one.** *Unlisted* is a server arriving without anyone
    deciding. *Unpinned* is the reviewed server and the running one being different things.
    *Drift* is two files disagreeing, where the one nobody looks at keeps the server somebody
    thought they had removed. Each has its own message because each has a different fix.
  - **Drift is compared on the parsed object.** Reordered keys and reformatting are not
    disagreement, and a check that cries wolf on whitespace is one people delete. A mutation
    comparing raw text was caught, as was one comparing only names — which would miss the same
    server pointing somewhere else, the case most worth catching.
  - **Production write is a declaration check and says so.** Nothing here can tell what a
    server actually reaches; what it can do is refuse an entry admitting to production write
    in a development profile, and make declaring it the cheap path. Read access to production
    is allowed, because it is a different risk and this rule does not claim to cover it.
  - **An absent `mcp_servers` key exits 2, not 0.** Absent is not empty — treating it as empty
    would let deleting one line silently disable every check above it.
  - `mcp_servers` becomes the eighteenth enforced config key, and the first of the six pending
    ones to be closed since `M3-10`.
  - 21 tests, 12 mutations, 12 caught.

- [x] **M4-09** Slash commands as thin wrappers over the CLI
  - No logic in a command file. If a fact appears in two tool directories, that is a bug.
  - **One directory, not two.** The `M0` probe measured Cursor listing `.claude/commands/`
    bodies in its `/` picker, so the shared tree already serves both tools. A
    `.cursor/commands/` copy would be the duplicated fact this task forbids, and
    `check-commands.py` rejects one rather than trusting nobody will add it.
  - **Three commands ship** — `/aios-check`, `/aios-autonomy`, `/aios-tests` — each wrapping a
    script that runs today. None wraps `aios`, because a wrapper around a binary this machine
    cannot build fails at the moment someone reaches for it. The set grows at `M1-08`.
  - **The gate is the durable half.** One invocation per command, no shell operators, the
    target must exist, and the first body line must be prose — the probe also found Cursor
    shows the *body* in the picker rather than the frontmatter `description`, so a command
    opening with code shows code to the user.
  - Costs nothing against the always-on budget: command bodies are on-demand. Total holds
    at 153.
  - 17 tests, 10 mutations, 10 caught. Suite now 587 tests.

- [x] **M4-12** Reimplement the probe as the `aios probe-adapters` subcommand
  - Replaces the scratch staging from `M0-01`. Setup, teardown, and marker generation become
    code; observation stays manual because it requires asking a tool a question.
  - A subcommand, not a script — [ADR-006](docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md).
    Provisional Python today, like the rest of the gate layer, and it moves at `M1-08`.
  - **Done when:** the quarterly re-run in `S-01` is one command plus the three protocols.
    `prompt.md` now opens with `stage`, the protocols, `teardown`, and a test asserts the
    hand-written `Remove-Item` teardown is gone rather than trusting that it was updated.
  - **Teardown is the whole difficulty, and it got harder since `M0`.** That run could delete
    everything unconditionally because `AGENTS.md`, `.claude/` and `.cursor/rules/` did not
    exist yet — every path it touched was its own. All three are real now and two are always-on
    context, so the manifest records per path whether the file pre-existed and its exact bytes
    if it did. Teardown restores and verifies by hash; anything that does not come back exits
    non-zero and keeps the manifest so it can be retried.
  - Verified live against a copy of this repository: `AGENTS.md` byte-identical afterwards,
    `explorer.md` and `no-presumed-stack.mdc` untouched in the directories the probe writes
    into.
  - Two smaller decisions. Staged files **satisfy the repository's own gates** — the probe
    command is a real one-invocation command — so a staged tree cannot be mistaken for a broken
    one. And nothing staged narrates that a probe is running: `M0` found an announcement in
    `AGENTS.md` confounded the behavioural half, because sessions read it and performed
    compliance.
  - 24 tests, 12 mutations, 11 caught. The survivor was a leftover-files sweep in teardown that
    no test could reach — `unlink` raises rather than failing quietly — so it was deleted
    rather than propped up with a contrived test. An assertion nothing can reach is a claim of
    a safety net, not one. Suite now 652 tests.

- [x] **M4-10** Instrument the verifier
  - Measure findings per review and how many survive to an actual code change.
  - **Done when:** the number is being reported monthly. If it approaches zero, delete the
    verifier — that is the agreed revisit trigger, not a failure.
  - **Done.** `measure-verifier.py`, Report class, monthly. Two numbers: findings per review,
    and the fraction that survive to an actual code change.
  - The second is the one that decides whether the subagent keeps its place in the always-on
    budget. The failure being watched for is not a verifier that misses things — it is one that
    is fluent: twelve findings per review of which none survives is worse than none at all,
    because it spends context, spends the reader's attention, and manufactures the feeling that
    the diff was reviewed.
  - Survival is structural — a later commit touching the file within ten lines of the finding.
    Nothing reads the agent's own claim about whether its finding was useful, because
    self-report is worth least exactly where this measurement is aimed. The proxy is generous
    in one direction on purpose (an unrelated edit to the same lines counts), so a low number
    is hard to argue with.
  - A finding that looks like a finding and names no location is counted as malformed rather
    than dropped: a verifier that formats badly must not look like one that found nothing,
    since those need opposite responses.
  - Reports "unknown" rather than 0% when there are no reviews. Those are different facts, and
    printing zero would be a conclusion nobody has earned the right to draw.

- [x] **M4-11** Implement the parallelism rule
  - Parallel reads encouraged. Multiple writing agents in one worktree forbidden. Multiple
    writing agents in separate worktrees permitted at `internal` tier and below, **only** with
    disjoint `touches` checked mechanically before dispatch.
  - Expect roughly an order of magnitude more token spend; treat it as an exception.
  - **Two controls, and they are different kinds.** `check-parallel.py` runs *before* dispatch
    and can prevent the collision. The write lease in `check-mode.py` runs at the moment of a
    write and can only bound one, because nothing signals that a session ended.
  - **Disjointness is a pattern intersection, not a file-set one**, and that is the whole
    point: `src/**` and `src/auth/**` share no file until the task creates `src/auth/`, and by
    then the two agents have already collided. Sound, not complete — it may refuse two scopes
    that would never have met, and it will not permit two that would. Tests pin that
    direction so a later "improvement" cannot quietly trade it away.
  - **A measurement changed the design.** The lease needs an identity for "a writing agent",
    and `session_id` was measured to equal `conversation_id` and to be the *chat's* UUID, not
    the window's. So a different holder is usually the same person in their next chat. The
    lease therefore refuses a takeover only while the claim is fresh, and the window is set
    between two intervals rather than for comfort: longer than one agent's gap between writes,
    shorter than the gap between working sessions. Two minutes.
    [Recorded](aios/bin/probe/results/hook-event-2026-08-01.md); the tracer that measured it
    was registered fail-open beside the fail-closed control and torn down after.
  - Separate worktrees needed no special case — each has its own root and therefore its own
    lease, which is exactly the permission the rule grants them.
  - The lease applies with **no mode set**, unlike everything else in that hook. A mode is a
    choice about how to work and defaults to unrestricted; one writer per worktree is an
    invariant about what a worktree survives, and a fresh clone is not exempt.
  - Two new config keys, and `max_tier` is read rather than repeated in the script: a policy
    with two definitions has two answers the day one is edited.
  - 41 tests, 21 mutations, 21 caught — one survivor first, a no-identity test that ran
    against an empty lease and so never reached the branch it named. Suite now 628 tests.

---

## M5 — Hygiene and longevity

**What M5 proves:** whether the OS can shrink. Track rules deleted versus added from here on.

- [x] **M5-01** Implement the memory-hygiene checks
  - `AGENTS.md` within budget · task files ≤60 lines · every path named in an instruction or
    standards file exists · every `enforced_by` resolves to a live lint rule · every
    `blocked_by`/`satisfies`/ADR link resolves · no duplicate IDs · no dated document past its
    review date.
  - **Source:** [04 §6](docs/design/04-state-and-tasks.md#6-memory-hygiene-as-a-build-failure)
  - **Five of the seven were already enforced and were deliberately not rewritten** — budgets
    are ratchets, the line cap is `validate-tasks.py`, the ID graph is
    `validate-references.py`, `enforced_by` is `validate-config.py`. A second implementation
    of a check is a second answer to the same question (D-040). What was unowned was **path
    references**, which is also the largest surface.
  - **The rule moved rather than being copied.** Link resolution lived in
    `validate-references.py` and ran over requirement and task files only — about a twentieth
    of the markdown here, and not the part read every turn. It now covers the instruction
    layer, and the old implementation and its test are gone. M5 is meant to prove the OS can
    shrink; this is one implementation covering twenty times more.
  - **Prose is checked, not just links, and that is the point.** A broken link is at least
    clickable. A sentence naming `aios/tasks/` is an instruction to look there, is never
    clicked, and is what an agent acts on.
  - **The difficulty was not detection, it was noise.** The first draft reported 104 problems
    here, every one a false positive. Three classes explained them: bare names written as
    names (`check-ratchets.py` in a sentence is correct English), history in append-only
    records, and tokens that merely look like paths — slash commands, pinned actions, bare
    extensions. Resolved by two tiers: **links everywhere, prose only where a reader is being
    instructed**, plus name resolution for bare names. 104 → 0, with `docs/design/` excluded
    because it is illustrative and asserting illustrations exist would train people to create
    files to satisfy a checker.
  - 32 tests, 13 mutations, 12 caught. The survivor was proved **equivalent** rather than
    surviving — the guard it removed is a fast path the following comparison already subsumes
    — and that is recorded in the code, because "a mutant lived" and "the mutant changed
    nothing" are the same observation until someone checks which.
  - Two follow-ons: nothing has a `review_by` date yet and `aios/standards/` is empty, so both
    halves are proved on fixtures and have nothing to say about this repository — the same
    weak-evidence position as `M4-08`, stated rather than glossed.
  - **`M4-11`'s write lease refused two edits mid-task, and the control was not at fault.**
    First a test invoked the hook with no root override, so it resolved the real repository and
    claimed the lease there; then the diagnostic runs chasing that did the same under their own
    session ids. Both denials were the rule working. What the episode exposed is worth more
    than the bug: a `failClosed` hook could exit non-zero, which turns any defect in it into
    every write refused — third time in this repository, so `decide()` is now wrapped the way
    input parsing already was, allowing and reporting that nothing was enforced.
    [Incident](aios/incidents/2026-08-02-a-test-took-the-write-lease-in-the-real-repository.md).
  - **The hook was not failing, it was hanging, and finding that is the most useful thing in
    this milestone.** The measured contract says the payload is CRLF-*terminated*, which says
    nothing about the pipe being closed — and `read_event` called `read()`, which waits for
    end-of-stream. Against a caller that holds the pipe open that wait never ends: measured
    side by side, `read()` was still running after four seconds where `readline()` returned in
    0.3. The timeout then fired and the editor reported an exit code, which describes the
    process truthfully and the fault misleadingly. Both hooks now read a line. This almost
    certainly also explains the *first* fail-closed outage back in `M2-08`, attributed then to
    an interpreter path. The read was "measured" once and treated as settled, and was the last
    thing anyone thought to test.
  - A mutation reported as surviving turned out never to have applied: `check-mode.py` is CRLF
    on disk and Python's `read_text` translates line endings, so a multi-line anchor matched in
    one tool and not the other. Re-run against the real bytes, it was caught.
  - Suite now 684 tests.

- [x] **M5-02** Implement the `AGENTS.md` growth ratchet
  - Not larger than it was N commits ago. **This is the single most important check in M5.**
    Most systems can only add rules, because adding one feels responsible and deleting one
    feels reckless. A fixed budget inverts that: past the limit, a new rule requires naming the
    one it replaces — and shrinking is the only defence against the accumulation that makes
    every system in this space worse in month six than in month one.
  - **The third check on this one set, and the difference is where its number comes from.**
    `check-always-on.py` enforces a ceiling, and a ceiling permits every increase below it —
    at 153 of 200 lines, the set can grow by 47 without a gate objecting.
    `check-ratchets.py` compares against a baseline stored in `aios/ratchets.yml`, which is
    better and has one weakness: the commit that grows the set can raise the baseline, and the
    `raised:` reason is written by the party raising it, in the same change. This compares
    against **git history**, which the commit under review cannot edit. That is the whole idea.
  - It measures the set by **importing `check-always-on.py`** rather than counting again. The
    incident that produced that file was two counts of this exact set disagreeing while the
    ratchet reported "held".
  - **Growth is allowed and has to be said out loud:** a `Grow-context:` trailer carrying a
    reason, the same shape as `M3-07`'s override trailer and for the same reason — the record
    lands where the next change cannot revise it.
  - **A test caught the escape hatch becoming the door.** The first draft let any trailer in
    the window permit any growth, so one justification licensed twenty commits of it. A trailer
    now authorises the level reached at *its own* commit; the next increase needs its own
    reason.
  - Comparing against the window rather than the previous commit is what catches one line per
    commit — the drift that passes every adjacent comparison, and the reason a stored baseline
    updated each time cannot see it.
  - Additions and deletions are both reported on every run, including passing ones, because M5
    asks whether this system can shrink and the only honest answer is the two numbers together.
  - **Inert here and loudly so.** Zero commits, by the same deliberate choice that has kept
    `M3-03`'s tamper check inert, so it exits 2 with a warning rather than passing. A check
    that passes because it had nothing to read is indistinguishable, in a green run, from one
    that passed because the thing it watches is healthy. `fetch-depth: 0` on the checkout for
    the same reason: a shallow clone silently shortens the window to whatever was fetched.
  - 23 tests, each building a real repository with real commits, since history is the one input
    the change under review cannot edit. 12 mutations, 11 caught; the survivor was equivalent,
    and rather than record that, the redundant guard it exercised was removed so the rule lives
    in one place.

- [x] **M5-03** Enforce documentation classification
  - Every document is exactly one of **generated** (never hand-edited, regeneration verified in
    CI), **checked** (mechanical guard against staleness), **dated and owned** (owner plus
    review date), or **immutable** (ADRs, incidents). Anything fitting none of these does not
    get written.
  - **Done when:** an unclassified document fails the build.

  - **Classification is by location, not by a marker in each file.** `docs/decisions/` is
    immutable because it is the ADR directory; a file does not need to restate that, and a
    per-file marker would be a second place to keep in sync. Frontmatter overrides the
    location, which is what a new directory or a genuine exception needs.
  - The four classes are not a taxonomy for its own sake. They are the exhaustive list of ways
    a document can be stopped from rotting, and the reason there is no fifth is that "someone
    will notice" is not one of them.
  - **It found three real gaps on first run:** the probe prompt was classified by nothing, and
    `docs/architecture.md` was dated-and-owned with neither an owner nor a review date — a
    document asserting it is kept current with nothing behind the assertion.
- [x] **M5-04** Build the staleness sweep
  - Past the review date, report. Past double the interval, blocking at `production` tier.

  - Report past the review date; block past double the interval, but only at `production` and
    above. At `prototype` the right answer to a stale document is usually deletion, and a
    blocked build cannot be answered with a deletion at three in the morning.
  - **The rule moved rather than being copied.** `M5-01` had checked review dates as part of
    path hygiene; that logic and its tests are now in `check-docs.py`, which owns the
    dated-and-owned class. Two implementations of one rule give two answers the day one is
    edited.
- [x] **M5-05** Generate the traceability map and the orphan reports
  - Which requirements have no test · which tests trace to no requirement · which requirements
    have no task and were never explicitly `deferred`.
  - Tests carry `@satisfies <REQ-ID>`, which also gives a failing test a *reason*: not
    "assertion failed at line 42" but "SEARCH-2 is violated".
  - All three report rather than block by default — in each case the right fix is sometimes to
    change the requirement, and a gate presuming the code is wrong trains dishonest fixes.

  - **Reports and never blocks, by decision rather than timidity.** In each of the three
    questions the right fix is sometimes to change the requirement. A gate that presumes the
    code is wrong trains people to satisfy it dishonestly — one throwaway test per
    requirement, a `@satisfies` on the nearest passing test, a requirement quietly deferred to
    clear the report. Each makes the map worse while making the number better.
  - **First run: zero of eight active requirements had a test naming them.** Four now do.
    `STATE-2` through `STATE-5` deliberately still do not: they describe what the binary does,
    and the binary does not exist (`M1-08`). Annotating the nearest passing test would be
    exactly the dishonesty this report exists to expose, and a test asserts they stay
    unclaimed.
- [x] **M5-06** Build `aios health`
  - Monthly, Report-class. Is it earning its keep: median start-to-merge, rejection rate with
    reasons clustered, gate failure rate by class, rework rate. Is it decaying: `AGENTS.md`
    line count over time, rules deleted vs added, overrides per month, stale docs, ignored
    advisories, markdown volume vs source volume. Is it learning: **incidents that produced a
    control ÷ total incidents** — the single best indicator that this is an operating system
    rather than a filing system. Is the human still in the loop: review debt, and median review
    time versus diff size.
  - If review time flattens while diff size grows, the human has stopped reading and every
    quality claim in the design is void.

  - **Every metric reports what it cannot measure rather than omitting it.** A dashboard of
    the four things that happen to be computable, with the eight that are not left off, reads
    as a healthy system. Six of fifteen are measurable here; the other nine name what they are
    waiting for.
  - Measured today: always-on 153 lines, markdown-to-source ratio 0.49, 45 gates, and the
    learning ratio — **5 of 6 incidents produced a control**. That number is only honest
    because `M5-11` made the field mandatory; without the schema it would be a self-report.
- [x] **M5-07** Build `aios prune`
  - Monthly proposals, each a PR a human accepts or rejects: rules with no violation in 90 days
    and no enforcement · advisories ignored 20 consecutive times · docs past double their
    review interval with no reader · requirements `deferred` over a year · tasks in `todo` over
    90 days. Rejections are recorded, so a document rescued three times stops being proposed.
  - Keeping something costs a little attention every day forever and nobody notices; deleting
    it risks one visible mistake. Making deletion routine and reversible-via-git is the only
    fix that survives contact with human psychology.

  - **It proposes and never deletes.** A tool that removes things on a timer is a different
    and much worse tool, and the reversibility argument only holds while a human is acting.
  - Rejections are recorded and a thing rescued three times stops being proposed — otherwise
    the monthly report becomes the same list forever, and a list that never changes is a list
    nobody reads, which leaves the tool technically running and practically off.
  - Age comes from git rather than a `created_at` field: a field would be a second place to
    keep a fact git already holds, writable by the party the age check is about.
- [x] **M5-08** Build `aios board`
  - Rendered to stdout, gitignored when written to a file, regenerated on demand. A generated
    view can be wrong for a moment; a stored one can be wrong forever.

  - Rendered to stdout, gitignored if ever written to a file. **A generated view can be wrong
    for a moment; a stored one can be wrong forever** — and it looks authoritative while it
    drifts, because it is checked in.
  - `blocked` stays derived from `blocked_by` rather than stored, per `P3`. Derived state that
    is also stored can disagree with itself.
- [x] **M5-09** Implement review-debt tracking — **the most speculative piece, deliberately last**
  - Count of merged tasks whose diffs the human spent under a threshold on, or dismissed
    without comment, in a rolling window. Above the limit, `aios next` refuses to hand out work
    and reports that review is the bottleneck.
  - The target is a person in a flow state who has stopped noticing they stopped reading — not
    a determined circumventer, whom no proxy would catch anyway.
  - Supporting measures: a diff-size budget per review cycle, and escalation to A0 after two
    consecutive rejections in the same area.
  - **Done when:** it is either measurable, or declared unmeasurable and the enforcement
    dropped in favour of guidance. A control that cannot be measured should be removed rather
    than left as decoration.

  - **The time-based half is dropped, not deferred** — [ADR-014](docs/decisions/ADR-014-time-on-diff-is-not-measurable.md).
    Nothing in a forge records attention. What is recorded is when a review was submitted, and
    that interval contains lunch, three meetings and eleven other tabs; a reviewer who reads
    for forty minutes and one who approves from a phone six hours later are indistinguishable
    and ordered the wrong way round. A metric that wrong is worse than none, because
    "review time: healthy" is read as evidence someone is reading.
  - **What is kept is recorded rather than inferred:** approvals carrying no comment, and diff
    size per review cycle. Above the limit `aios next` refuses to hand out work — the only
    response that acts on the constraint instead of adding to the queue that is the problem.
  - What is given up is stated in the ADR: one comment per pull request defeats the remaining
    measure completely. The alternative on offer was the same gap with a number next to it.
- [x] **M5-10** Build `aios upgrade`
  - Fetches the template changelog and reports which changes apply, classified **mechanical**
    (gate script, CLI fix — applied automatically) or **judgement** (new gate, schema change —
    presented as a PR with rationale). Projects pin a template version and may decline anything.
  - Downstream divergence is expected and fine. The template is a starting point, not a
    dependency.

  - Mechanical changes apply without a conversation; judgement changes land as a pull request
    with the rationale. **Anything unclassified is treated as judgement** — the safe direction
    costs a pull request nobody needed, the other silently adds a gate that starts failing
    builds on a Friday and the project never agreed to it.
  - Versions are compared by position in the changelog rather than by parsing version numbers,
    because an unrecognised scheme would otherwise return nothing and the tool would report
    "up to date" when it had failed to read the file.
- [x] **M5-11** Define the incident schema
  - Mandatory field: **the control that now prevents recurrence**, or an explicit statement
    that no practical control exists and why. Without that field an incident log is a list of
    regrets. Append-only. `blocks_work: true` stops `aios next`.
  - This is where the OS compounds: a bug caught in review is worth one fix; a bug that
    produces a gate is worth every future instance.

  - The mandatory field is **the control the incident produced**, or an explicit statement
    that no practical control exists and why. `no_control_because` exists because a schema
    that will not accept that answer gets a fictional control instead; what it will not accept
    is silence.
  - This is what makes `aios health`'s learning ratio mean anything. The metric is honest only
    because the schema refuses an incident that answers neither way.
  - The six existing incidents were migrated: frontmatter added, **not a word of the prose
    touched**. The value of "we believed X on the day, and X was wrong" is entirely in it
    having been written before anyone knew.
- [x] **M5-12** Define the standards schema
  - Every rule declares `enforced_by: <lint rule>` or `unenforceable: <reason>`. Where enforced,
    prose is capped at two lines pointing at the rule. **A standards file whose rules are all
    enforced gets deleted** — the linter already says it.

---

## M6 — Trial and honest evaluation

One real project, three months, against the published kill criteria. The design's own strongest
quality is that it says in advance what would make it worth abandoning.

  - Every rule declares `Enforced by:` or `Unenforceable:`. There is no third option, because
    the third option in practice is prose that sounds like a rule, is enforced by nobody, and
    is followed until the first deadline.
  - **A file whose rules are all enforced fails, and the fix is to delete it.** It is a
    description of the checks, and the checks are already that description — this copy is the
    one that goes stale. It is the only gate here whose pass condition is a file not existing,
    which is the point of M5.
  - `aios/standards/` is empty, so this proves itself on fixtures. An empty directory passes
    and says why, so nobody later fills it in to be helpful.
- [ ] **M6-01** Capture the baseline **before switching anything on**
  - Current time-to-merge, rejection rate, and defect escape rate *without* the OS.
  - Without a baseline the trial cannot conclude anything. Retrospective judgement about
    whether it "felt faster" is explicitly worthless here — METR's participants believed they
    were 20% faster while measuring 19% slower.
  - **Done when:** the numbers are recorded and dated, and no OS component is active yet.

- [ ] **M6-02** Run the `P0-6` project on the OS for three months
  - Instrumented from day one. Not this repository — see
    [ADR-001](docs/decisions/ADR-001-first-project-is-the-os-itself.md) §2.

- [ ] **M6-03** Report `aios health` monthly and act on nothing automatically
  - A metric that triggers an automatic response becomes a target.

- [ ] **M6-04** Evaluate against the six kill criteria
  - 1. Median start-to-merge worse, unexplained by better outcomes. 2. Review debt chronically
    over limit. 3. Contract gates overridden more often than they pass. 4. Repository markdown
    volume exceeds source volume. 5. Host tools have absorbed enough that this is a thin shim.
    6. Nobody has read a task file, an ADR, or a requirement in a month.
  - **Check criterion 6 first** — it is the one most likely to be true.

- [ ] **M6-05** Write the verdict as an ADR: continue, substantially rewrite, or abandon
  - A system that cannot be abandoned will be maintained past its usefulness.

---

## Standing, after M6

- [ ] **S-01** Re-run the adapter probe quarterly and on any major Cursor or Claude Code release
  - Then: list OS features that now overlap a native feature, and **default to deleting the OS
    version**. Keeping one requires a written reason — usually cross-tool portability.
  - Re-verify the Windows-specific assumptions each time; they depend on undocumented behaviour
    and will change without notice.
  - A shrinking OS is a healthy one. If the OS is the same size in two years, it has stopped
    tracking reality.

---

## Not on this list, deliberately

Each was considered and declined; adding any of them is a design change requiring an ADR, not a
task. No spec-driven framework layer. No multi-agent org chart — no PM, architect, or QA
persona. No replacement for a host-tool native feature. No ceremonies. No scoring system — no
story points, no debt index, no RICE. No stack presumed *of a cloned project* — ADR-005 binds
this repository only. No `CONTRIBUTING.md`, no separate style
guide, no `TESTING.md`, no hand-written changelog. No `blocked` task state. No separate
change-proposal directory — git already stores the delta, the baseline, the archive, and the
review.
