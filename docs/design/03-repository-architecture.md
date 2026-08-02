# 03 — Repository architecture

Covers: folder hierarchy, the tool adapter layer, and documentation architecture.
Decisions referenced here are recorded with full alternatives in [10](10-decision-register.md).

---

## 1. The layout

```
<project>/
├── AGENTS.md                  # tool-agnostic core. Facts only. ≤150 lines, CI-enforced.
├── CLAUDE.md                  # import shim: "@AGENTS.md" + Claude-only notes. Not a symlink.
├── README.md                  # human entry point: what this is, how to run it, where to look.
│
├── aios/                      # the OS: project state + its own executables
│   ├── config.yml             # tier, budgets, gate policy, paths
│   ├── glossary.md            # domain terms with precise definitions
│   ├── open-questions.md      # known unknowns; a first-class artifact, not a gap
│   ├── requirements/          # one file per capability area, e.g. auth.md, search.md
│   ├── tasks/                 # one file per task; done/ subtree for completed
│   │   └── done/YYYY-MM/
│   ├── standards/             # only conventions a linter cannot express
│   ├── incidents/             # failures that produced a control
│   └── bin/                   # the aios CLI + gate scripts (shared by both tools)
│
├── docs/
│   ├── decisions/             # ADRs, immutable once accepted
│   ├── architecture.md        # module map + boundaries; points at enforced config
│   ├── runbooks/              # operational procedures
│   └── design/                # this design set (delete after cloning if unwanted)
│
├── .cursor/
│   ├── rules/                 # Cursor-only behaviours. Expected to be nearly empty.
│   └── mcp.json               # duplicate of .mcp.json, drift-checked
├── .claude/
│   ├── agents/                # explorer, verifier
│   ├── commands/              # thin wrappers over aios/bin
│   ├── skills/
│   └── settings.json          # permission deny-list + hook registrations
├── .mcp.json
│
├── .github/
│   ├── CODEOWNERS             # protects tests, CI, gate config, aios/config.yml
│   └── workflows/
│
├── src/
└── tests/
```

### 1.1 Why `aios/` is not `.aios/`

This looks like bikeshedding and is not. **`ripgrep` skips dot-directories by default**, and ripgrep is what coding agents actually run to find things. Putting requirements and tasks in a hidden directory means an agent searching for `R-004` gets zero hits and concludes the requirement does not exist. Hidden directories are also collapsed or omitted in many file trees, which harms the human half of the audience for no benefit.

The counter-argument — that tooling belongs out of sight next to `.github/` and `.vscode/` — applies to configuration nobody reads. It does not apply to a directory that holds the project's requirements. `.cursor/` and `.claude/` stay hidden because their location is dictated by the host tools and their contents are loaded by the tool rather than searched by the agent.

The directory name is a config key, so a project that hates it can rename it in one place.

### 1.2 What the top level is allowed to contain

Root files are the most expensive real estate in the repository: everything scans them, humans and agents alike. The template ships exactly four (`AGENTS.md`, `CLAUDE.md`, `README.md`, plus whatever manifest the chosen ecosystem requires at root), and a CI check fails if the count of markdown files at root exceeds five. This is a deliberately petty rule that prevents the observed drift toward `CONTRIBUTING.md`, `ARCHITECTURE.md`, `STYLE.md`, `TODO.md`, `NOTES.md` accumulating at root where each one competes for the same attention.

### 1.3 The structure does not change with project size

"MVP to enterprise" is handled by `aios/config.yml`'s `tier`, which changes **which gates block** and **how much autonomy an agent has** ([06](06-quality-gates-and-testing.md), [05](05-workflows.md)). It does not change the folder layout. A prototype has the same directories as a regulated system, most of them nearly empty, because the alternative — a migration step when a prototype becomes real — is a step nobody performs. Empty directories cost nothing; restructuring a live repository costs a great deal.

---

## 2. Project state: what lives where and why

Each store below is separated from the others because it has a **different lifecycle**. This is the direct response to the single-mutable-memory-file collapse in [01: 2.4] — a file an agent may rewrite wholesale needs to be small and recoverable, and a file that must never change should be structurally incapable of changing.

| Store | Mutability | Written by | Read when |
|---|---|---|---|
| `aios/requirements/` | Append-mostly; edits are reviewed diffs | Human-approved PR | Planning; task validation |
| `aios/tasks/` | High churn, small files | Agent + human, one file at a time | Every task cycle |
| `docs/decisions/` (ADRs) | **Immutable** once accepted; superseded, never edited | Human-approved PR | On demand, by link |
| `aios/incidents/` | **Append-only** | Human after a failure | On demand |
| `aios/standards/` | Low churn | Human-approved PR | Path-scoped |
| `aios/glossary.md` | Low churn | Either | Path-scoped / on demand |
| `aios/open-questions.md` | Medium churn | Either | Planning |

Requirements and tasks are specified in [04](04-state-and-tasks.md). The rest:

**ADRs** use a trimmed MADR: context, decision, consequences, alternatives rejected with the reason. Immutability is the entire point — an ADR edited in place destroys the record of why the old choice was made, which is the only thing an ADR is for. Superseding creates a new ADR that links back.

**Incidents** exist to close the learning loop. Every entry names what failed, and — mandatory field — **the control that now prevents it**, or an explicit statement that no control is practical and why. An incident log without that field becomes a list of regrets. This is where an OS actually gets better over time: a bug caught in review is worth one fix, but a bug that produces a gate is worth every future instance.

**Standards** hold only what a linter cannot express. Every standards file must declare, per rule, either `enforced_by: <lint rule id>` or `unenforceable: <reason>`. Where `enforced_by` is present the prose is capped at two lines pointing at the rule, because the rule is the truth and the prose is a courtesy (P3). A standards file whose rules are all `enforced_by` is deleted; the linter already says it.

### 2.1 Change proposals: rejected as a separate artifact

OpenSpec's delta model is the best idea in the spec-driven tooling space ([01: 4.4]): describe only what changes, fold it into the baseline on completion, archive the proposal. We adopt the *discipline* and reject the *directory*.

The reason is that a `changes/` tree with proposals, deltas, and an archive is a reimplementation of version control in markdown. Git already stores the delta (the PR diff), the baseline (the file on `main`), the archive (history), and the review (the PR). Adding a parallel copy means two things that can disagree, which is precisely what P3 forbids.

What we keep as a rule: **a requirement change and the tasks implementing it land in the same pull request.** The PR is the change proposal. The diff is the delta. Merging is the fold.

What we lose: a long-lived, visible-on-`main` proposal for a change nobody has started yet. That is real, and the mitigation is `aios/open-questions.md`, which is where "we will probably need X, here is the shape of it, undecided" belongs. If a project finds itself with more than a handful of long-lived proposals, this decision should be revisited — the trigger is recorded in [10](10-decision-register.md#d-006).

---

## 3. The tool adapter layer

### 3.1 The rule

**One source of truth, adapters that only ever point.** An adapter file may contain an import, a path, or a tool-specific setting. It may not contain project knowledge. If a fact appears in both `.cursor/` and `.claude/`, that is a bug.

### 3.2 The portable primitives

Two mechanisms are supported by both tools and carry almost all the weight:

**`AGENTS.md` at root** — the emerging cross-tool standard ([01: 7.1]). Claude Code reaches it via an import from `CLAUDE.md`.

**Nested `AGENTS.md` in subdirectories** — the portable path-scoping primitive. `src/payments/AGENTS.md` carries payments-specific facts and is picked up when the agent works in that directory. This matters more than it first appears: it means `.cursor/rules/*.mdc` — the obvious place to put path-scoped rules — is the *wrong* place, because it is Cursor-only and would need a duplicate for Claude Code. Path-scoped knowledge goes in nested `AGENTS.md`; `.cursor/rules/` is reserved for genuinely Cursor-specific behaviour and is expected to stay nearly empty. An almost-empty `.cursor/rules/` is a sign the adapter layer is working.

### 3.3 `CLAUDE.md` is an import shim, never a symlink

On Windows, a git checkout without `core.symlinks` produces a plain text file containing the target path. It has the right name, it is not empty, and every tool that reads it sees a valid file whose entire content is the string `AGENTS.md` ([01: 7.3]). The failure is silent and looks exactly like an agent that has stopped following instructions.

```markdown
<!-- CLAUDE.md -->
@AGENTS.md

<!-- Claude Code specific notes below this line only. -->
```

A CI check greps `CLAUDE.md` for the flattened-symlink signature (a file whose entire trimmed content matches a bare path ending in `.md`) and fails the build. The check costs three lines and catches a whole class of "why is the agent ignoring the rules" investigations. The user's environment is Windows/PowerShell, so this is load-bearing rather than defensive.

### 3.4 Genuinely duplicated configuration

Some things have no single-source option and must be duplicated. The policy for each is a **drift check**, not a clever hack:

| Duplicated | Files | Handling |
|---|---|---|
| MCP servers | `.mcp.json`, `.cursor/mcp.json` | `aios/bin/check-drift` compares the parsed `mcpServers` object; mismatch fails CI |
| Hook registration | `.claude/settings.json`, `.cursor/hooks.json` | Both register the *same script* in `aios/bin/hooks/`; only the registration differs, so drift surface is one line each |
| Permission deny-lists | tool-specific | Both derive from `aios/config.yml`'s deny list via a generator, with the generated files checked in and verified up-to-date in CI |

Putting hook *logic* in `aios/bin/` rather than inline in either settings file is what keeps this cheap. The configs become pointers; pointers rarely drift.

```powershell
# aios/bin/check-drift.ps1  (illustrative; a cross-platform twin in the project's own
# language ships alongside, once that language is chosen — see D-041)
$claude = (Get-Content .mcp.json -Raw | ConvertFrom-Json).mcpServers |
          ConvertTo-Json -Depth 20 -Compress
$cursor = (Get-Content .cursor/mcp.json -Raw | ConvertFrom-Json).mcpServers |
          ConvertTo-Json -Depth 20 -Compress
if ($claude -ne $cursor) {
  Write-Error "MCP drift between .mcp.json and .cursor/mcp.json"; exit 1
}

$c = (Get-Content CLAUDE.md -Raw).Trim()
if ($c -match '^[\w.\-/]+\.md$') {
  Write-Error "CLAUDE.md looks like a flattened symlink: '$c'"; exit 1
}
```

### 3.5 The discovery matrix must be probed, not assumed

Which tool reads which directory is a moving target, and the asymmetry noted in [01: 7.2] (Cursor reads parts of `.claude/`; Claude Code does not read `.cursor/`) is the kind of fact that changes between releases. The design's response is not to encode a matrix in prose that will be wrong in six months, but to ship `aios/bin/probe-adapters`, which writes a uniquely-tagged fact into each candidate location and reports which tool surfaces it. Implementation milestone 1 runs it; the results go in a generated file with the tool versions recorded, and it is re-run when either tool updates.

This is the honest way to handle a dependency on undocumented behaviour: make the assumption testable and date-stamped rather than authoritative and stale.

### 3.6 Subagents

Two, both for context isolation rather than role ([01: 3.2], [01: 3.4]):

- **explorer** — read-only, no write tools. Answers "where does X live", "is there already an implementation of Y", "what calls Z". Exists to keep large search output out of the main context, and to make the duplicate-code check from [01: 1.2] cheap enough that it actually happens.
- **verifier** — receives a diff and the task's acceptance criteria in a fresh context, with no memory of writing the code. Returns findings, not edits.

No PM, architect, QA, or security persona. `.claude/agents/` holds both; the Cursor equivalent is whatever `probe-adapters` reports, and if Cursor reads `.claude/agents/` directly then there is nothing to duplicate.

---

## 4. Documentation architecture

### 4.1 The classification rule

Every document in the repository must be exactly one of:

1. **Generated** — produced from a source artifact by a command; never hand-edited; regeneration is verified in CI. *(API reference from schema, CLI help, dependency inventory, coverage map.)*
2. **Checked** — hand-written but with a mechanical guard against going stale. *(Architecture doc: the boundaries it describes are enforced by an import linter, and a check confirms every module it names exists. Standards: every `enforced_by` must name a live lint rule.)*
3. **Dated and owned** — hand-written narrative with no mechanical guard, carrying an owner and a review date. Past the date, CI reports it as stale; past double the interval, the staleness becomes blocking at `production` tier. *(Runbooks, architecture narrative sections.)*
4. **Immutable** — a historical record. Cannot go stale because it describes a moment. *(ADRs, incidents.)*

Anything that fits none of these categories does not get written. This is the concrete answer to documentation being the top reported source of technical debt at Google ([00](00-charter.md)): the problem is not too little documentation, it is documentation with no mechanism for being true.

### 4.2 The doc set

| Document | Class | Notes |
|---|---|---|
| `README.md` | Checked | Every command it shows is executed in CI. A README with a broken quickstart is worse than none. |
| `AGENTS.md` | Checked | Line budget; every path it names must exist. |
| `docs/architecture.md` | Checked | Module map, boundaries, data flow. Boundaries are enforced by import rules; the doc explains *why* they exist, which the linter cannot. |
| `docs/decisions/ADR-*.md` | Immutable | |
| `aios/requirements/*.md` | Checked | IDs unique; every requirement reachable from a task or explicitly marked `deferred`. |
| `aios/standards/*.md` | Checked | `enforced_by` must resolve. |
| `docs/runbooks/*.md` | Dated & owned | |
| API reference | Generated | From OpenAPI/schema. Never written by hand. |
| Database schema | Generated | From migrations. |
| Test/requirement coverage map | Generated | Which requirements have tests. Feeds the orphan report in [06](06-quality-gates-and-testing.md). |

Note what is absent: no `CONTRIBUTING.md` (the workflow is in `AGENTS.md` and enforced by gates), no separate style guide (linter config), no `TESTING.md` (the strategy is in the standards file, the practice is in CI config), no changelog written by hand (generated from conventional commits).

### 4.3 Ordering: what gets written when

Against `plan.txt`'s proposal to write the documentation set before implementation. The rule is that **a document may be written only once the thing it describes is decided**, which puts most of it after code starts:

- *Before any code:* `README` stub, requirements for the first slice, glossary seed, `open-questions.md`.
- *At the moment of decision:* ADRs. Not before, not in a batch afterwards.
- *As it becomes true:* architecture, standards, runbooks.
- *Continuously and automatically:* everything in the Generated class.

Requirements come first because they are the "why", and the "why" is the one thing no amount of code reading recovers. Architecture written before the code is a prediction; architecture written after is a description; only one of those can be checked.
