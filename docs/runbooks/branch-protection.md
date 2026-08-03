---
owner: "@NishantRajiitkgp"
review_by: 2027-02-03
review_months: 6
---

# Branch protection on the default branch

**What this is for.** Every other containment control in this repository runs on the machine
being controlled. The pre-commit trailer, the tool deny lists and the mode hook are all
convenience: they are fast, they teach, and a determined party skips them without leaving a
trace. This setting is the only one that holds, because it is the only one enforced by
something the graded party cannot write to. `GUARD-2` is that statement as a requirement.

**Where the intended state lives.** `branch_protection` in `aios/config.yml`. That block is
the declaration; the settings below are how it is applied; `check-branch-protection.py` reads
the forge and fails when the two disagree. A setting that exists only as the current state of
a web form has no before, no reason and no author — it can be switched off in one click by
somebody who does not know why it was on, and nothing anywhere would say it had been.

## Applying it

GitHub → the repository → **Settings** → **Branches** → **Add branch ruleset**, or **Add
classic branch protection rule**. Either works; the checker reads the effect, not the
mechanism. Classic rules map one-to-one onto the list below, so they are described here.

Branch name pattern: `main`.

| Switch on | Set to | Why |
|---|---|---|
| Require a pull request before merging | on | Nothing reaches `main` without a diff to look at. |
| Required approvals | 1 | `required_reviews` |
| Dismiss stale pull request approvals when new commits are pushed | on | An approval is of a diff, not of a branch. Without this, approve-then-push is a merge nobody reviewed. |
| Require review from Code Owners | on | The switch that makes `.github/CODEOWNERS` mean anything. Without it that file is a document the forge does not consult. |
| Require status checks to pass before merging | on | `require_status_checks` |
| Require branches to be up to date before merging | on | Two branches that each pass alone can fail together. This is the only setting here that catches that. |
| Status checks required | `build`, `hygiene`, `secrets` | The three workflows that run on every push. Named individually, because "all checks" silently means "the ones that happened to run". |
| Allow force pushes | **off** | History is the evidence every verification record points at. A force push rewrites what a record was verified against, and the record still looks valid. |
| Allow deletions | **off** | |
| Do not allow bypassing the above settings | leave **off** | See below. |

## Why admin bypass is deliberately left on

`enforce_admins: false`, and it is a real decision rather than an oversight.

This repository has one maintainer. Locking the administrator out of their own default branch
in a one-person repository does not add a reviewer; it adds a locksmith visit. The honest
statement of what this configuration achieves is: it makes the unreviewed path *visible and
deliberate* rather than *default*. That is worth having and it is less than it sounds like.

Turn `enforce_admins` on the moment a second person can approve a pull request, and change the
value in `aios/config.yml` in the same commit, so the check fails until the setting follows.

## Verifying it

    python3 .github/scripts/check-branch-protection.py

Without a token it distinguishes protected from unprotected, which is the difference that
matters — no protection at all is the state a repository sits in by default and stays in
quietly. With a token that can read the repository, which CI has, it compares every declared
setting and names each disagreement. It never reports the first as though it were the second.

An unreachable API exits 2, not 1. A network check that reports a flaky lookup as a violation
trains people to re-run it until it passes, and after that it is not a check.

## If this is ever turned off

Turning it off is allowed. Turning it off silently is not: the check goes red on the next push
and stays red. Change `aios/config.yml` in the same commit as the setting, and say in the
commit message what was bought — that record is the entire difference between a decision and
a thing that happened.
