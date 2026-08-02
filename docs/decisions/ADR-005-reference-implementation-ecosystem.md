# ADR-005 — Rust is the reference implementation's ecosystem

**Status:** accepted
**Date:** 2026-07-31
**Decides:** `P0-2`

## Context

[D-041](../design/10-decision-register.md#d-041--no-presumed-stack-the-ecosystem-is-derived-from-the-project)
holds that the OS names no default ecosystem and that the choice is derived per project from its
requirements. [ADR-001](ADR-001-first-project-is-the-os-itself.md) made the OS its own first
project, which puts this squarely on D-041's own revisit trigger: the OS is being built for
general distribution, and D-041 says that condition makes a *reference* implementation necessary
— as a worked example, still not as a default.

Two of the four original constraints survived unchanged. The third — "already present on a
machine that builds the host project" — is self-referential when the OS is its own host and
yields no signal. It was replaced by a stronger one, accepted as **hard**: a project cloned from
the template must be able to invoke `aios/bin/**` **without adopting the OS's runtime**.

That replacement is what actually decided this. It eliminates every interpreted ecosystem, since
each would make the OS a second runtime for every downstream project — the precise cost the
original constraint existed to prevent.

## Decision

Rust, producing a self-contained binary. This is the ecosystem of the **reference
implementation**. It is not a default for projects cloned from the template, which continue to
choose their own under D-041.

## Constraints, checked individually

| Constraint | Status | Basis |
|---|---|---|
| Runs identically under PowerShell | **Verified at `M1-08`** | A native Windows executable, not a shell script. A clean `windows-latest` checkout builds it with no setup step, and the exit-code assertions hold when it is invoked through PowerShell rather than through bash. Recorded here because this row scheduled its own verification; the decision above is unchanged. |
| Installs without a global install | Satisfied for consumers | Consumers run a released binary; nothing is installed. Contributors to the OS itself do need the toolchain, which is the accepted asymmetry. |
| Every gate script under `aios/bin/` is reachable | Satisfied | Gate scripts are subcommands of, or binaries invoked by, the same artifact. |
| A cloned project invokes `aios/bin/**` without the OS's runtime | Satisfied | A statically linked binary has no runtime to adopt. This is the constraint that decided the choice. |

## Consequences

1. **A per-platform release pipeline is now required**, and it is the direct price of the hard
   constraint. Tracked as `M3-11`, which also has to prove the runtime-free invocation from a
   project in a different ecosystem rather than assert it. This closes the deferral recorded in
   ADR-001 §4.

2. **How a cloned project obtains the binary is unresolved** and is a genuine open question, not
   an implementation detail. Committing it to git fights the artifact-size ratchet; fetching it
   on first use introduces a network dependency that must be checksum-verified or it becomes a
   supply-chain hole in the one tool whose job is closing those. Seeded into
   `aios/open-questions.md` at `M1-01`.

3. **One M3 gate is rescued.** ADR-001's revisit trigger warned that several gates would have
   nothing to bite on against a CLI-shaped project. The artifact-size ratchet now does have a
   meaningful notion of a shipped artifact — a binary — so it can be validated here. The
   accessibility ratchet, p95 latency budget, and DAST still cannot, leaving that trigger live.

4. **The suppression ratchet has a concrete escape hatch to count:** `#[allow(...)]`, which is
   already named in the design's own list of ecosystem-specific spellings.

5. **Compile time lands on contributors, not consumers.** The `aios check` budget of under 60
   seconds applies to the check run, and incremental builds must be kept inside it. If they
   cannot be, the budget is the thing to defend and the build is the thing to fix.

6. **Supply-chain controls map cleanly:** `--locked` for frozen installs, and the ecosystem's
   audit and policy tooling for the allowlist, age, and advisory checks. The OS's own dependency
   count should be kept near zero so it can satisfy its own M3 gates without exception.

7. **The toolchain must be pinned in-repo** so contributor and CI builds cannot diverge — the
   same equivalence `aios check` demands of local versus CI.

## Alternatives rejected

- **Go.** Also satisfies the hard constraint, with a smaller toolchain and faster builds, and it
  was the closest call. Rejected on the diff-scanning and state-machine work that dominates this
  codebase, where the pattern-matching and type expressiveness carry more weight than build
  speed. This is a judgement, not a measurement, and the revisit trigger below is written against
  it honestly.
- **.NET / C# with AOT publish.** Satisfies the constraint and is native on the target OS.
  Rejected for larger artifacts and the added build complexity AOT introduces on a project whose
  main claim is that its own machinery stays small.
- **Node / TypeScript.** Fails the hard constraint outright — imposes a runtime on every
  downstream project in another ecosystem — and carries the largest transitive dependency surface
  for the OS to police under its own supply-chain gates.
- **Python.** Fails the hard constraint for the same reason, with version fragmentation on
  Windows as an additional cost in the target environment.

## Revisit if

Either: (a) build times make the OS's own inner loop slow enough that contributors begin routing
around `aios check`, which is the exact bypass behaviour the design exists to prevent and would
mean the choice is undermining the system; or (b) the per-platform release pipeline costs more
maintenance than the runtime-free property returns — measured by how many projects actually
adopting the template differ in ecosystem. If that number is near zero, the hard constraint was
not worth its price and this decision and the constraint behind it should be reopened together.
