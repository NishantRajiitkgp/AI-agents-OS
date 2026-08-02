# ADR-013 — The cross-ecosystem invocation contract

**Status:** accepted
**Date:** 2026-08-01
**Closes:** [Q-002](../../aios/open-questions.md) in full, and the repository-root half of
[Q-003](../../aios/open-questions.md).
**Supersedes:** nothing.

## Context

[ADR-005](ADR-005-reference-implementation-ecosystem.md) chose Rust against one hard
constraint: a cloned project must be able to invoke `aios/bin/**` without adopting the OS's
runtime. A static binary satisfies that constraint *by construction* — there is no runtime to
adopt — and `Q-002` was raised because that argument covers the runtime and nothing else.
Everything around the call was undefined.

`Q-002` also states the sequencing requirement, and it is the reason this ADR exists now
rather than alongside the implementation: **the contract has to be written down before the
test, so that the test can fail it.** A contract derived from whatever the binary happened to
do would be a description, and a test generated from a description passes by definition.

The binary does not exist yet — the Rust toolchain is unreachable from this network
([incident](../../aios/incidents/2026-07-31-rust-toolchain-unreachable.md)), so `M1-08` is
held. That blocks the *proof*, not the *specification*, and this ADR is the specification.

## Decision

Four things, matching `Q-002`'s four bullets.

### 1. Naming and discovery: invoked by path, not found on `PATH`

The executable is `aios/bin/aios`, plus the platform's executable extension — `aios.exe` on
Windows. A host project calls that path. Nothing is installed onto `PATH`, and no per-platform
shim is committed.

The rejected alternative was a committed shim per platform giving one extension-free name.
It was rejected because [ADR-008](ADR-008-symlink-detection-and-shim-validation.md) is a
standing warning about committed indirection: on a checkout with `core.symlinks` disabled a
committed symlink arrives as a plain file with the right name and the wrong content, and every
tool that reads it sees something valid. A shim layer would be a second thing that can be
subtly wrong while looking right. Branching on the extension is one line in every host
ecosystem's task runner; being wrong about what a file is costs a debugging session.

Installing onto `PATH` was rejected for a different reason: it makes the tool's version a
property of the machine rather than of the checkout, and two projects on one machine would
then share whichever version was installed last.

### 2. Exit codes: 0, 1, 2, and nothing else means anything

| Code | Meaning |
|---|---|
| 0 | The check ran and passed. |
| 1 | The check ran and failed. There is a finding, and it is legitimate. |
| 2 | The check could not reach a verdict. Missing config, unparseable state, absent dependency. |
| 3–125 | Reserved. A host must treat any of these as not-pass. |
| >125 | Signal or shell convention. Not the tool's to define. |

The 1-versus-2 distinction is the whole point, and `Q-002` names the failure it prevents:
*could not run* is the outcome that gets silently treated as pass. A host project that maps
"non-zero means failed" is correct and safe. A host that maps "zero means pass, everything
else means investigate" is correct and safe. The unsafe mapping — treating an unrecognised
code as success — is made impossible by reserving the whole space rather than leaving it
undefined.

This codifies measured practice rather than inventing a scheme. Every provisional gate script
under `.github/scripts/` and the dispatch skeleton in `src/main.rs` already use exactly these
three codes; the contract is what makes them a promise instead of a habit.

### 3. Output: human by default, machine behind a flag, streams split by role

Human-readable output on stdout is the default. `--format json` switches stdout to a single
machine-readable document. Diagnostics — progress, warnings, anything not the verdict — go to
stderr in both modes.

Machine-readable *by default* was the serious alternative, on the argument that a
cross-ecosystem tool's primary caller is a wrapper. It was rejected because the primary
consumer of a gate's output is a human reading a CI log after a red build, and a default that
optimises for the wrapper puts a `| jq` between that human and the answer on the worst day
they will have with this tool.

Splitting the streams by role is what makes both modes usable at once: a host project can
capture stdout for the verdict and let stderr flow to the log, without either mode needing a
quiet flag.

### 4. Repository root: discovered upward from the working directory, refused if ambiguous

The root is the nearest ancestor of the working directory containing a `.git` entry. `--root`
overrides it; `AIOS_ROOT` overrides it with lower precedence than the flag. If no root is
found, the tool exits 2 — it does not guess, and it does not treat the working directory as a
root.

Configuration is read from `<root>/aios/config.yml`, at that fixed path, overridable with
`--config` or `AIOS_CONFIG`.

**This is the half of `Q-003` that `Q-002` needed.** `Q-003` observed that `paths.state_dir`
cannot locate the file that declares it, and priced three options. This takes the first —
the config path is fixed and only the state subdirectories move — and accepts the cost
`Q-003` named, that `aios/config.yml` stays literal while the directories around it are
configurable. The reason is that the alternative, searching for a directory that looks like a
state directory, is ambiguous by construction: two candidates cannot be resolved, and the
current single-level glob is a fallback that works on a repository with one candidate rather
than a rule. A fixed path plus an explicit override is boring and total.

The cost is explicit: **a project not under Git cannot be discovered**, and must pass `--root`
or `AIOS_ROOT`. That is accepted rather than overlooked. Every mechanism in this OS that has
teeth — override records, the demotion window, scope checking, the ratchet's tamper detection
— reads history, so a checkout without it is already outside the design's assumptions. The
override exists so that the tool still runs there rather than refusing on principle.

Walking upward for `.git` rather than for the state directory also answers the subdirectory
question directly: invoking from `aios/tasks/` finds the same root as invoking from the top,
which is what makes the tool usable from wherever a host project's task runner happens to put
its working directory.

## Consequences

The contract is now falsifiable, which is the point. `tests/test_invocation_contract.py`
encodes all four sections as executable conformance checks that run against any candidate
executable, and they are written to fail a non-conforming one — proven by running them against
deliberately non-conforming stand-ins rather than by inspection.

`Q-001` is *not* closed by this. How the binary reaches a clone is a separate question that
needs a measured artifact size, and no artifact has been built.

The end-to-end proof `Q-002` demands — a real host project in another ecosystem calling a real
gate and acting on the result — remains owed. It is guarded by a test that fails the moment an
executable appears, so the proof cannot be quietly skipped once the block on `M1-08` lifts.

## Revisit when

- The first host project in another ecosystem finds any of the four sections awkward enough to
  wrap rather than call. That is the signal the contract was written from the implementation's
  point of view instead of the caller's.
- A subcommand needs an exit code that is not pass, fail, or could-not-run. The reserved range
  exists so that adding one is a decision recorded here rather than a number that appears.
