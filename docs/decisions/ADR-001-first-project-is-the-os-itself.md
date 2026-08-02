# ADR-001 — The OS's own repository is the first project it is built against

**Status:** accepted
**Date:** 2026-07-31
**Decides:** `P0-1`

## Context

The roadmap's open question 1 asks for "the first real project". That question conflates two
different projects:

- the project the OS is **built against** during M0–M5, which supplies the requirements the
  stack is derived from and exercises the loop while it is being written;
- the project the OS is **evaluated on** at M6, which must run for three months against the
  kill criteria.

They have different requirements. The first needs to exist now. The second needs a *pre-OS
delivery baseline* — time-to-merge, rejection rate, defect escape rate measured before anything
is switched on — because without one the trial cannot conclude anything.

## Decision

The OS's own repository is the first project it is built against. **The M6 trial subject is a
separate decision and remains open.**

## Consequences

1. **The meta-process becomes the development method.** [09 §5] already required that changes to
   the OS be tasks, with requirements, in the OS's own repository. From `M1-18` onward that is
   not just a rule the OS imposes on itself — it is how the remaining milestones get built.

2. **M6 cannot use this repository.** It has no pre-OS delivery history, so the baseline cannot
   be captured and kill criterion 1 ("median time from start to merge is worse") would be
   unmeasurable. A trial subject must be nominated **before M5 completes**, or instrumentation
   lands too late to produce a baseline — which is the specific failure the roadmap warns about.

3. **The OS is now simultaneously its own host project and a template for unknown future
   projects.** That is precisely the revisit condition recorded in
   [D-041](../design/10-decision-register.md#d-041--no-presumed-stack-the-ecosystem-is-derived-from-the-project):
   extraction for general distribution makes a *reference* implementation necessary. The
   practical effect on `P0-2` is that its fourth constraint — "already present on a machine that
   builds the host project" — is self-referential here and yields no signal. The ecosystem must
   therefore be derived from the OS's own requirements and recorded as a reference
   implementation, **explicitly not a default** for projects cloned from the template.

4. **Gate scripts need a cross-ecosystem invocation contract.** A project cloned from the
   template will often not share the OS's ecosystem, so `aios/bin/**` must be callable from a
   project that does not have the OS's runtime. Deferred to M2/M3 and tracked in
   `open-questions.md`; it is a real cost of this decision, not an oversight.

## Alternatives rejected

- **An existing maintained project.** Would supply a genuine pre-OS baseline, which is the one
  thing this choice gives up. None was nominated.
- **A new greenfield project.** Delays M1 until that project has real requirements, and a
  project with no history has no baseline either — so it costs time without buying the thing
  the baseline was for.

## Revisit if

The OS's own requirements prove unrepresentative enough that gates are being calibrated on the
wrong workload. Concretely: it is a CLI, so the accessibility ratchet, the p95-latency budget,
DAST, and possibly the artifact-size ratchet have nothing to bite on, and the supply-chain
controls are only exercised if it acquires real dependencies. If three or more M3 gates cannot
be validated here, the trial subject must be brought forward rather than deferred.
