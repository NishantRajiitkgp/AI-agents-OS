# Open questions

Known unknowns, tracked as a first-class artifact rather than left as a gap in a design
document. An entry here is a decision that has been *identified and deliberately not made
yet*, which is a different state from one nobody has noticed.

Each entry names what would close it and the point by which it must be closed. An entry with
no closing condition is not an open question, it is an opinion, and belongs somewhere else.
When one closes it becomes an ADR in [`docs/decisions/`](../docs/decisions/) and is struck
from this file with a link.

This file is also where "we will probably need X, here is its shape, undecided" belongs —
it is the mitigation for not keeping a long-lived change-proposal tree
([03 §2.1](../docs/design/03-repository-architecture.md#21-change-proposals-rejected-as-a-separate-artifact)).

---

## Q-001 — How does a cloned project obtain the `aios` binary?

**Status:** open. **Must be answered by:** `M3-11` (the release pipeline).
**Raised by:** [ADR-005 §2](../docs/decisions/ADR-005-reference-implementation-ecosystem.md).

[ADR-005](../docs/decisions/ADR-005-reference-implementation-ecosystem.md) chose a
self-contained binary so that a cloned project never adopts the OS's runtime. It did not
decide how that binary reaches the clone, and the two obvious answers each break something
the OS is supposed to enforce:

- **Commit it to git.** No network dependency and no supply-chain surface, but a
  multi-megabyte binary per platform fights the artifact-size ratchet the OS ships — the
  tool would be violating its own gate in its own repository.
- **Fetch on first use.** Keeps the repository small, but introduces a network dependency
  that must be checksum-verified and pinned, or it becomes a supply-chain hole in the one
  tool whose stated job is closing those.

Neither is disqualified. The question is which cost is worth paying, and it cannot be
settled before there is a release pipeline to measure the artifact against.

**What would close it:** a measured artifact size per platform from `M3-11`, and a decision
on whether the checksum-verified fetch can be made to satisfy the OS's own supply-chain
gates without an exception. An exception granted here would be the first, and would set the
precedent for every one after it.

**Where that measurement now comes from:** the "Checksum it and record its size" step in
[`release.yml`](../.github/workflows/release.yml) writes a size per platform to the job
summary. The pipeline is written and has never run, because the toolchain that builds the
thing being measured is unreachable from this network. So this question is not blocked on a
decision anyone is avoiding — it is blocked on a number that cannot exist yet, and guessing
the number is the one way to close it wrongly.

**Do not close it by:** picking whichever is easier to implement in the week it comes up.

---

## Q-002 — What is the invocation contract for `aios/bin/**` across ecosystems?

**Status:** closed by
[ADR-013](../docs/decisions/ADR-013-the-cross-ecosystem-invocation-contract.md) on 2026-08-01.

All four bullets are decided: invocation by path with the platform's extension, exit codes 0
/ 1 / 2 with the rest of the space reserved, human output by default with `--format json` and
diagnostics on stderr, and root discovery walking upward for `.git` with `--root` and
`AIOS_ROOT` overrides.

The sequencing requirement it carried was met — the contract was written before the test, so
the test can fail it. Two independent conformance implementations exist
([Python](../tests/test_invocation_contract.py), [Node](../tests/host-project/check.mjs)), and
both reject all twelve deliberately non-conforming stand-ins.

**Still owed, and tracked in `M3-11` rather than here:** the conformance run against a real
binary on a machine with no Rust toolchain. It is wired in
[`release.yml`](../.github/workflows/release.yml) and guarded by a test that fails the moment
an executable appears, so it cannot be quietly skipped.

---

## Q-003 — How is `config.yml` located when the state directory has been renamed?

**Status:** open. **Must be answered by:** `M1-08`, which builds the CLI entry point and is
the first thing that has to resolve this for real.
**Raised by:** `M1-05`, on wiring `paths.state_dir` into its first consumer.

`paths.state_dir` exists so a project that dislikes the name `aios/` can change it in one
place. But `config.yml` lives *inside* that directory, and reading it is what tells you the
directory's name. The key cannot locate the file that declares it.

Today the validator tries `aios/config.yml` and falls back to a single-level glob for a
directory holding both `config.yml` and `requirements/`. That works and is convention, not
contract: two such directories are ambiguous, and a state directory nested deeper is missed.

The candidates each cost something:

- **Fix the config path and let only the state subdirectories move.** Simplest, but then the
  protected path `aios/config.yml` stays literal while everything around it is configurable,
  which is the kind of half-indirection that misleads.
- **Search upward and inward from the working directory**, as version-control tools do for
  their own config. Predictable, and it answers the related question of what happens when the
  CLI is invoked from a subdirectory — which `Q-002` also needs settled.
- **Require an explicit flag or environment variable when the location is not conventional.**
  Honest and boring; the cost is that every invocation in every wrapper has to carry it.

**Partly closed by**
[ADR-013 §4](../docs/decisions/ADR-013-the-cross-ecosystem-invocation-contract.md) on
2026-08-01, which took the first option: the config path is fixed at `<root>/aios/config.yml`
with `--config` and `AIOS_CONFIG` overrides, and only the state subdirectories move. The cost
this entry named — a literal `aios/config.yml` surrounded by configurable directories — is
accepted rather than solved. `Q-002` had to decide root discovery for the invocation contract,
and answering the two differently would have given the tool two ways to find the same
repository.

**What remains:** the provisional Python validators still use the single-level glob. Replacing
it with the ADR-013 rule is `M1-08`'s work, and until then the fallback this entry warns about
is still what runs.

**Do not close it by:** leaving the glob in place and calling it discovery. It is a fallback
that happens to work on a repository with one candidate directory.

---

## Q-004 — Where does a task's creation time come from?

**Status:** open. **Must be answered by:** `M1-10`, which builds the selector that uses it.
**Raised by:** `M1-06`, on closing the task field list.

[04 §4](../docs/design/04-state-and-tasks.md) sorts candidate tasks by `created_at` at
tie-break (d). [04 §3.1](../docs/design/04-state-and-tasks.md#31-schema) does not list
`created_at` as a field, and the list is explicitly closed. The selector reads something the
schema does not define.

Both readings are defensible and they differ in what can be forged:

- **Derive it from git** — the first commit that added the file. Nothing is stored, so it
  cannot drift or be edited, which suits a value the selector depends on. The costs are that
  it is unavailable before the first commit, it changes under rebase and squash, and it makes
  the selector depend on repository history rather than on working-tree state.
- **Add it as a field.** Simple, readable, and stable under history rewriting. It reopens a
  closed field list, and it is a value the agent writes and the selector then trusts — the
  shape of thing this design generally refuses.

Note that ordering is already **total without it**: tie-break (e), ID lexicographic,
guarantees a unique answer. So `created_at` is not load-bearing for determinism. It is
load-bearing only for the *intent* that older ready work is picked first, which is a
different and weaker claim.

**What would close it:** the `M1-10` decision, taken together with whether that intent is
worth either cost. Dropping tie-break (d) entirely is a real third option and should be
priced rather than assumed away.

**Do not close it by:** adding the field because the selector referenced it. The design
closed that list deliberately, and one reference is not an argument for reopening it.

---

## Q-005 — What interpreter does a checked-in hook invoke?

**Status:** open. **Must be answered by:** `M2-10`, which re-registers the hook.
**Raised by:** `M2-08`, by breaking on it.

A hook registered in `.cursor/hooks.json` names a command. Written as `python3` it does not
exist on Windows; written as `python` it may be absent, or be Python 2, on a Linux or macOS
checkout. Combined with `failClosed: true` either mistake blocks every shell command in the
editor rather than degrading, which is what happened
([incident](incidents/2026-07-31-fail-closed-hook-blocked-every-command.md)).

The options differ in what they assume about the machine:

- **Name one interpreter and document the requirement.** Simplest, and wrong on some
  checkouts by construction. A template cannot assume the clone's ecosystem ([D-041]).
- **Probe at registration time** and write the resolved name. Correct per machine, but the
  generated file then differs per developer, so it either cannot be committed or produces
  spurious diffs.
- **Ship the hook as the `aios` binary.** No interpreter is named at all, which is the same
  argument [ADR-006](../docs/decisions/ADR-006-no-shell-scripts-in-aios-bin.md) already made
  about gate logic, arriving from a second direction.

**What would close it:** the binary existing. This question is largely an artefact of the
provisional Python implementation and mostly disappears with it — which is a reason to weigh
it lightly rather than design around it now.

**Do not close it by:** picking whichever name works on the machine in front of you. That is
what produced the incident, and it fails silently on somebody else's checkout.
