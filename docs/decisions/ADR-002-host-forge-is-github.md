# ADR-002 — GitHub is the host forge and CI

**Status:** accepted
**Date:** 2026-07-31
**Decides:** `P0-3`

## Context

The containment model in [07 §1.1] stacks three layers over the protected set, and is explicit
that only one of them is a real control: the host tool's permission deny-list and the pre-commit
hook are convenience, because both run on a machine the agent already controls. CODEOWNERS with
required review is the only layer enforced server-side, and it is therefore the only thing
standing between the agent and its own grader.

That makes the forge choice a containment decision rather than a preference. M2 is unprovable
without server-side required review.

## Decision

GitHub, with GitHub Actions as the CI host.

## Consequences

- Every primitive M2 depends on exists natively: CODEOWNERS, branch protection and rulesets,
  required status checks, required reviews, and restriction of force-push and history rewrite.
  M2 can be implemented as designed with no substitution.
- Build provenance and artifact attestation are available for M3's SLSA-shaped ratchet, which
  becomes Contract at `regulated` tier.
- The containment **implementation** is now tied to one vendor. The containment **design** is
  not — the protected set and the three-layer model are forge-independent.
- Branch protection must be recorded as configuration in the repository rather than clicked in a
  web UI, or the most important control in the system has no diff and no review. This is written
  into `M2-02`.

## Alternatives rejected

- **GitLab.** Has CODEOWNERS and push rules, but required-approval semantics differ enough that
  M2's checks would need rewriting rather than porting.
- **Azure DevOps.** Branch policies exist; there is no CODEOWNERS equivalent with the same
  path-scoped required-reviewer semantics, so the protected set would have to be expressed
  differently.
- **Bitbucket.** Same class of difference, smaller ecosystem for the CI side.
- **Local git only.** Removes layer three entirely. Every remaining gate becomes advisory, which
  is worse than having no gates because it produces a green signal that gets trusted. This would
  make M2 — and therefore everything M2 exists to make meaningful — unachievable.

## Revisit if

The M6 trial subject lives on a different forge, or GitHub changes required-review semantics such
that a CODEOWNERS-protected path can be merged by the pull request author.
