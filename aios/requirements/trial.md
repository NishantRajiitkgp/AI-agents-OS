# TRIAL — the evaluation that decides whether any of this was worth it

What the OS must guarantee about judging itself. The whole design is a bet, and M6 is where
the bet is settled: a real project runs on the OS for a fixed period, against criteria written
before the evidence arrived, and the verdict is recorded whichever way it goes.

This area exists because a system that measures everything except its own value is the most
likely failure mode here. Every mechanism in this repository produces a number; none of them
answers whether the work went faster or the software got better.

Requirements are never deleted. A withdrawn one keeps its entry, its status, and its reason.

---

## TRIAL-1 — The baseline is captured before anything is switched on

**Status:** active
**Rationale:** A baseline measured after adoption is not a baseline, it is a second reading of
the treated state. There is exactly one opportunity to take it and it is before the first
gate runs, which is also the moment when everyone is least interested in stopping to measure.

The system shall record a trial project's current value for each metric the evaluation will
use, before the first gate runs on that project.

If a baseline value cannot be measured, then the system shall record that it could not, rather
than substitute an estimate.

---

## TRIAL-2 — The trial runs on a real project for a fixed period

**Status:** active
**Rationale:** A trial on a toy project measures the toy. A trial with no end date is not
evaluated, it is inhabited — the decision point arrives only when someone happens to ask, and
by then the cost of stopping has been paid anyway.

The system shall be evaluated on a project chosen before the trial begins, doing work that
would have happened regardless.

The system shall run for a period fixed in advance, and shall not extend it in response to the
evidence accumulating.

---

## TRIAL-3 — The kill criteria are written before the evidence

**Status:** active
**Rationale:** Criteria written afterwards are a description of the outcome. This is the
single requirement here that cannot be satisfied late: once the results are visible, no one
can un-see them while deciding what would have counted as failure.

The system shall record the conditions under which it would be abandoned, before the trial
begins.

If a kill criterion is met, then the system shall report it against the criterion as written,
without reinterpreting the criterion.

---

## TRIAL-4 — Reports inform; nothing acts on them automatically

**Status:** active
**Rationale:** An automated response to a health metric is an unreviewed change driven by a
number nobody interrogated, and it arrives exactly when the number is least trustworthy. The
proposal is the deliverable; the action is a person's.

The system shall report its own health on a fixed interval and shall take no action in
response.

Where the system identifies something to remove or demote, the system shall propose it and
shall require a decision recorded outside itself before the proposal takes effect.

---

## TRIAL-5 — The verdict is recorded as a decision, including a negative one

**Status:** active
**Rationale:** The failure mode is not a bad verdict, it is no verdict: the trial ends, nobody
writes it down, and the system continues by default. A recorded abandonment is worth more to
whoever finds this repository later than a system quietly still running.

When the trial period ends, the system shall record the verdict as a decision with its
reasoning, whether that verdict is to continue, to rewrite substantially, or to abandon.

The system shall retain the record of a negative verdict on the same terms as a positive one.
