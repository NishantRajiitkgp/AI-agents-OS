# INVOCATION — how a project in another ecosystem calls this tool

What the OS must guarantee at the process boundary. A cloned project chose its own language,
runtime and package manager, and none of them is this one; everything it can rely on is what
happens when it runs an executable and reads a number.

The contract is [ADR-013](../../docs/decisions/ADR-013-the-cross-ecosystem-invocation-contract.md)
and the deciding constraint behind it is
[ADR-005](../../docs/decisions/ADR-005-reference-implementation-ecosystem.md). This area is
those decisions written as things the system must guarantee, which they were not — the
conformance suite existed for a milestone before any task could name what it was checking.

Requirements are never deleted. A withdrawn one keeps its entry, its status, and its reason.

---

## INVOCATION-1 — Invoked by path, never installed onto PATH

**Status:** active
**Rationale:** Installing makes the tool's version a property of the machine rather than of
the checkout, and two projects on one machine then share whichever version was installed last.
A committed shim was the alternative and is worse: ADR-008 is a standing record of committed
indirection arriving intact and wrong.

The system shall be invocable by the path of its executable, with no installation step and no
entry added to the caller's search path.

**Out of scope:** the platform's executable extension. Branching on it is one line in every
host ecosystem's task runner, and hiding it behind a shim costs a debugging session.

---

## INVOCATION-2 — Three exit codes, and the rest reserved

**Status:** active
**Rationale:** The 1-versus-2 distinction is the whole point. *Could not run* is the outcome
that gets silently treated as a pass, and a host mapping "non-zero means failed" must be
correct, as must a host mapping "zero means pass, anything else means investigate". Reserving
the remaining space is what makes the unsafe third mapping impossible rather than discouraged.

The system shall exit 0 when a check ran and passed, 1 when a check ran and failed, and 2 when
a check could not reach a verdict.

The system shall not use any other exit code, and shall require a decision recorded as an ADR
before one is added.

If a check cannot run, then the system shall report that separately from a check that ran and
failed, in both its output and its exit code.

---

## INVOCATION-3 — Human output by default, machine behind a flag

**Status:** active
**Rationale:** The primary consumer of a gate's output is a person reading a log after a red
build. A machine-readable default puts a parsing step between that person and the answer on
the worst day they will have with this tool.

The system shall write human-readable output to standard output by default, and shall write a
single machine-readable document there instead when asked for one.

The system shall write diagnostics to standard error in both modes, so that a caller can
capture the verdict without also capturing the commentary.

If asked for an output format it does not have, then the system shall refuse rather than fall
back to a format the caller did not ask for.

---

## INVOCATION-4 — The root is discovered upward, and refused rather than guessed

**Status:** active
**Rationale:** A tool that treats the working directory as the root gives a confident answer
about the wrong project, and the answer looks the same as a correct one. Walking upward also
settles the subdirectory question: invoking from anywhere inside a checkout finds one root.

The system shall determine the repository root by walking upward from the working directory to
the nearest ancestor containing a repository marker.

If no root is found, then the system shall exit could-not-run rather than treat the working
directory as one.

The system shall accept an explicit root and an explicit configuration path, and shall give
the flag precedence over the environment variable for each.

**Out of scope:** discovery for a project not under version control. It must pass its root
explicitly, and that cost is accepted: every mechanism here with teeth reads history, so a
checkout without it is already outside the design's assumptions.

---

## INVOCATION-5 — The caller adopts no runtime of this tool's

**Status:** active
**Rationale:** The hard constraint ADR-005 selected an ecosystem against. A tool that audits
other people's dependencies while requiring its own toolchain to be installed is not credible,
and the claim is only worth making where it can fail.

The system shall run on a machine that has none of the implementation ecosystem's toolchain
installed.

When the claim is checked, the system shall be exercised by a project in a different
ecosystem, on a machine where the toolchain's absence has been confirmed rather than assumed.

The system shall publish a checksum beside each released artifact, so that a project fetching
one can verify what it fetched.
