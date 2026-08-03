---
id: T-9a3c
title: Report health monthly through the trial and act on nothing automatically
status: todo
satisfies: [TRIAL-4]
priority: 2
risk: medium
blocked_by: [T-9a2b]
touches:
  - .github/workflows/monthly.yml
  - docs/
acceptance:
  - "The system shall report its own health on a fixed monthly interval throughout the trial"
  - "The system shall take no action in response to any metric it reports"
  - "Where the report identifies something to remove or demote, the system shall propose it and shall require a decision recorded outside itself before the proposal takes effect"
verify:
  - python3 .github/scripts/report-health.py
  - python3 .github/scripts/check-advisory-deletion.py
constraints:
  - "A metric that triggers an automatic response becomes a target, and it does so at exactly the moment the metric is least trustworthy."
  - "The monthly workflow already exists. This task is the reading and the deciding, which is the part no workflow can do."
---

## Context

Carried over from `M6-03`. The machinery is built — `monthly.yml` runs the health report, the
prune proposal, the review-debt check, the upgrade check and both counters — so what is left is
the discipline that `TRIAL-4` describes: the report informs, and a person decides.

The counters are the sharp case. The advisory-deletion counter and the demotion counter both
produce a proposal that would be trivially easy to apply automatically, and both would then be
making an unreviewed change driven by a number nobody interrogated. The proposal is the
deliverable; the action is somebody's.

## Outcome

Open, blocked on the trial running.
