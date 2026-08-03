# GUARD — containment: what the graded party may not reach

What the OS must guarantee about the boundary between the agent doing the work and the
machinery judging it. A gate the agent can edit is worse than no gate, because it produces a
green signal that gets trusted.

This area exists because the M2 work had nothing to point at. Its requirements were argued in
`docs/design/` and recorded as decisions; they were never written as things the system must
guarantee, so the tasks implementing them satisfied nothing nameable.

Requirements are never deleted. A withdrawn one keeps its entry, its status, and its reason.

---

## GUARD-1 — The grader is outside the graded party's write scope

**Status:** active
**Rationale:** [D-020](../../docs/design/10-decision-register.md#d-020--the-grader-is-outside-the-graded-partys-write-scope).
Containment is the precondition for every other gate meaning anything. Ordering M2 before the
broader gate set was deliberate for this reason: a check the agent can weaken reports on
whatever it was last weakened to.

The system shall declare the set of paths the agent may not modify, in one place, and shall
name that place as the authority when the set is read.

If a change modifies a protected path, then the system shall require an approval recorded by a
party that is not the agent.

**Out of scope:** whether the approving party is human. That word cannot be enforced by
anything in this repository — a trailer is as easy to type as it is to mean — and claiming
otherwise would be the failure this area exists to prevent.

---

## GUARD-2 — Enforcement is server-side; local checks are convenience

**Status:** active
**Rationale:** A control that runs on the machine it is controlling can be skipped by the
thing it is controlling, and the skip is invisible afterwards. Local hooks are worth having
because they are fast and they teach, not because they hold.

The system shall treat a check running in the working copy as advisory.

Where a control must hold against a determined party, the system shall place the enforcing
decision with the forge rather than with the checkout.

---

## GUARD-3 — A test change carries the weight of the code it covers

**Status:** active
**Rationale:** The cheapest way to make a failure go away is to amend the thing that noticed
it, and the amendment looks like ordinary maintenance in isolation. What makes it visible is
requiring it to arrive beside the code it is about.

When a pull request weakens an assertion, removes a test, or marks one skipped, the system
shall report the weakening and the file it occurred in.

If a suite shrinks by any route, then the system shall fail rather than record a smaller
suite as the new normal.

---

## GUARD-4 — An override is recorded, never silent

**Status:** active
**Rationale:** A Contract gate that can be waived quietly is a Ratchet nobody declared. The
record is what makes the waiver a decision with a name on it instead of a thing that happened.

When a Contract gate is overridden, the system shall require a dated record naming the gate,
the approver and the reason.

If a commit claims an override with no record, or a record appears with no commit claiming
it, then the system shall fail and report which half is missing.

The system shall reject an edit or deletion of an existing override record.

---

## GUARD-5 — A gate overridden routinely is demoted, not ignored

**Status:** active
**Rationale:** A gate that is waived every time is already not a Contract; it is a Contract in
name, and the gap between the name and the practice is where people stop reading the output.
Demotion makes the practice the record.

When one gate is overridden three times within thirty days, the system shall demote it from
Contract to Ratchet and record the demotion with the overrides that caused it.

**Out of scope:** automatic promotion. Tightening a gate is a judgement about whether the
repository can now afford it, and nothing here can make that judgement.

---

## GUARD-6 — A secret is unreachable, not declined

**Status:** active
**Rationale:** An injected instruction to exfiltrate a credential must fail because the
credential is not there, not because the agent chose well. Defences that depend on the agent's
judgement are defences that work until the input is adversarial, which is the only time they
matter.

The system shall keep credentials outside the reach of the agent's execution environment.

When a credential appears in the working tree or in history, the system shall fail at every
tier and name the file and the commit.

**Out of scope:** the tool-layer command deny list. It is advisory, it differs between tools,
and it cannot narrow what a developer has already permitted. It is worth having and it is not
this requirement.
