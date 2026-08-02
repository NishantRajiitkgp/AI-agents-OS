# 09 — Long-term maintenance and self-evolution

Every system in this space is better in month one than in month six. Rules accumulate, documents go stale, gates get bypassed, and the artifacts quietly stop being read while continuing to cost tokens. This document is about making that trajectory visible and reversible, which is a different and harder problem than getting the initial design right.

---

## 1. The four decay modes, and the counter to each

| Decay | What it looks like | Counter |
|---|---|---|
| **Accretion** | Rules only ever added; `AGENTS.md` at 600 lines by month six | Hard budget + a ratchet. Past the budget, adding requires deleting. |
| **Staleness** | Docs describe a system that no longer exists | Every doc is generated, checked, dated, or immutable ([03](03-repository-architecture.md#41-the-classification-rule)). Nothing else may exist. |
| **Bypass** | Gates overridden routinely; green means nothing | Override counting + automatic demotion ([06](06-quality-gates-and-testing.md#2-the-demotion-rule)) |
| **Obsolescence** | Host tools ship the feature natively; the OS duplicates it worse | Quarterly overlap review with a bias to delete (§4) |

Accretion is the one that kills these systems, and it kills them because adding a rule feels responsible and deleting one feels reckless. The budget inverts that: with a fixed allowance, every addition forces an explicit judgement about what it is worth more than. That single constraint does more for long-term health than any amount of discipline.

---

## 2. Health metrics

Reported monthly by `aios health`. These are Report-class ([06](06-quality-gates-and-testing.md)) — measured, surfaced, never automatically acted on, because a metric that triggers an automatic response becomes a target.

**Is the OS earning its keep?**
- Median time from `aios start` to merge
- Rejection rate at human review, and the reasons, clustered
- Gate failure rate by class — Contract failures should be *rare*; frequent Contract failures mean the gates are miscalibrated, not that the agent is bad
- Rework rate: tasks reopened after `done`

**Is the OS decaying?**
- `AGENTS.md` line count over time (must trend flat or down)
- Rules deleted vs added, cumulative
- Overrides per month, by gate
- Stale docs past review date
- Advisory findings ignored consecutively
- Total repository markdown volume vs source volume

**Is the loop learning?**
- **Incidents that produced a control, divided by total incidents.** The single best indicator that this is an operating system rather than a filing system. A number near zero means failures are being fixed and forgotten.
- Recurring rejection reasons that have not yet produced a control

**Is the human still in the loop?**
- Review debt ([05](05-workflows.md#the-review-fatigue-problem))
- Median review time versus diff size

That last pair is the honest one to watch. If review time flattens while diff size grows, the human has stopped reading and every quality claim in this design is void.

---

## 3. Deletion is a first-class operation

`aios prune` proposes, monthly:

- Rules with no violation in 90 days *and* no enforcement — either the rule is unnecessary or it was never doing anything
- Advisory checks ignored 20 consecutive times
- Docs past double their review interval with no reader (measured by links and greps, imperfectly)
- Requirements `deferred` for over a year — either commit or drop
- Tasks in `todo` for over 90 days — a backlog nobody is going to reach is a lie about intent

Every proposal is a PR a human accepts or rejects. Rejection is recorded, so a doc rescued three times stops being proposed.

The asymmetry this fights is straightforward: keeping something costs a little attention every day forever and nobody notices, while deleting something risks one visible mistake. Left alone, that asymmetry guarantees monotonic growth. Making deletion routine, scheduled, and reversible-via-git is the only fix that survives contact with human psychology.

---

## 4. Tracking the host tools

By [01: 4.5] the tools are absorbing framework features — Agent OS deleted its own spec commands in favour of native plan mode; SuperClaude's own gap analysis lists skills, hooks, and plan mode as migration targets. Anything here that overlaps with a native feature is on borrowed time.

Quarterly, or on any major release of Cursor or Claude Code:

1. Re-run `aios probe-adapters`; commit the dated result.
2. List OS features that now overlap a native feature.
3. **Default to deleting the OS version.** Keeping it requires a written reason — usually cross-tool portability, occasionally a capability the native feature lacks.
4. Re-verify the Windows-specific assumptions ([03](03-repository-architecture.md#33-claudemd-is-an-import-shim-never-a-symlink)), which depend on undocumented behaviour and will change without notice.

A shrinking OS is a healthy one. If the OS is the same size in two years, it has stopped tracking reality.

---

## 5. How the OS changes itself

The meta-process, and it is deliberately the same process the OS imposes on product code, because a system whose own maintenance is exempt from its rules is not a system:

- Changes to the OS are tasks, with requirements, in the OS's own repository.
- A change to a rule or gate must cite an incident, a recurring rejection reason, or a metric — **not an intuition**. "This feels like good practice" is the mechanism by which all of these systems bloat.
- Adding a Contract gate requires evidence it would have caught something real.
- Adding a rule while at budget requires naming its replacement.
- The OS versions semantically; downstream projects consume updates by cherry-pick, not by merge.

### 5.1 Propagating updates to existing projects

A template is copied, so downstream projects diverge immediately and there is no clean upstream merge. The mechanism:

- `aios upgrade` fetches the template's changelog and reports which changes apply.
- Changes are classified **mechanical** (a gate script, a CLI fix — applied automatically) or **judgement** (a new gate, a schema change — presented as a PR with the rationale).
- Projects pin a template version in `aios/config.yml` and may decline anything.

Downstream divergence is expected and fine. The template is a starting point, not a dependency, and a project that has adapted the OS to its domain is a success rather than a drift problem.

---

## 6. Kill criteria

Stated up front, because a system that cannot be abandoned will be maintained past its usefulness.

Abandon or substantially rewrite this OS if, after a fair trial (three months, one real project):

1. Median time from start to merge is worse than without it and the difference is not explained by better outcomes.
2. Review debt is chronically over limit — the human loop does not scale, and everything here depends on it.
3. Contract gates are overridden more than they pass.
4. Repository markdown volume exceeds source volume.
5. Host tools have absorbed enough that the OS is a thin shim over native features.
6. Nobody has read a task file, an ADR, or a requirement in a month. If the artifacts are unread, they are cost with no benefit, and the honest response is deletion rather than a campaign to make people read them.

Criterion 6 is the one to check first and the one most likely to be true.
