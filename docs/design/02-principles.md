# 02 — Design principles

Eight principles. Each one is a compression of evidence from [01](01-evidence-base.md), and each is stated with its inverse so it is falsifiable rather than motivational. Every decision in [10](10-decision-register.md) cites at least one of these.

---

## P1. Facts, not procedures

**State what is true about the project. Do not state what should be done.**

Agents apply facts reliably and follow procedures unreliably ([1: 2.3]). `AGENTS.md` should read like a project fact sheet: package manager, module boundaries, where auth lives, what `Money` means, which directories are generated. It should not read like a process manual.

*Test:* if a line in an instruction file starts with "always", "never", "make sure to", or "remember to", it is a procedure. Either mechanise it or delete it. The only surviving procedures are the ones a machine genuinely cannot check.

*Inverse:* if agents demonstrably obeyed written procedure at high rates, this principle would be wrong and the cheapest system would be a long style guide.

---

## P2. Gates, not guidelines

**A rule that matters is executable. A rule that is only written down is a preference.**

Everything the project actually depends on — dependency policy, secret handling, test integrity, API contract stability — must exist as a check that fails a build. Writing it in a rules file *as well* is optional and usually redundant.

*Corollary (P2a):* the grader must live outside the graded party's write scope ([1: 5.7]). Tests, CI config, gate config, and lint config are agent-read-only and CODEOWNERS-protected. Without this the entire gate layer is advisory.

*Inverse:* if agents never modified their own evaluation criteria, containment would be unnecessary overhead. Measured reward hacking ([1: 5.1], [1: 5.2]) says otherwise.

---

## P3. Derived, not duplicated

**Every fact has exactly one home. Everything else is a view or a link.**

Duplication is the mechanism by which documentation becomes wrong. A backlog is a query over task files, not a file. Architecture documentation points at the module boundaries the linter enforces. The API reference is generated from the schema. Cursor and Claude Code read the same core through thin adapters ([1: 7.1], [1: 7.2]).

*Test:* for any statement in any document, name the single place it lives. If two places can disagree, one of them must become a pointer, or a drift check must exist.

*Inverse:* where generation is impossible and a check is impractical, accept the duplicate and make it loud — a stale-marker comment naming its source.

---

## P4. Budget the context

**Always-on context is a fixed, small, enforced allowance. Everything else loads on demand.**

Long context degrades ([1: 2.1]) and instruction adherence collapses ([1: 2.2]) far below the window limit. So `AGENTS.md` gets a hard line budget enforced in CI, path-scoped rules attach only to the files they govern, and deep reference material is pulled by explicit request.

*Corollary:* adding a rule has a price. Past the budget, a new rule requires deleting an old one. This is what makes rule count able to decrease, which no system that only appends can do.

*Inverse:* if adherence were flat in context length, the right design would front-load everything and this principle would be pure cost.

---

## P5. Deterministic state

**The project's status is computed from small, per-unit files. It is never asserted by an agent.**

`aios next` reads task frontmatter and the dependency graph and returns an answer that does not depend on whether anyone remembered to tick a box ([1: 4.2]). One file per task, no aggregate store, no format where a bad merge stays valid ([1: 4.3]).

*Corollary:* `done` is not a value an agent may write on its own authority. It requires a named verification command exiting zero.

*Inverse:* for a solo developer on a three-task project this is overhead, and a checklist is genuinely better. The design should be honest that it earns its keep past roughly ten concurrent units of work.

---

## P6. Verification is the scarce resource

**Optimise for the reviewer's attention, not the agent's throughput.**

Verification failure is the dominant multi-agent failure class ([1: 3.2]); artifact volume exceeding review capacity is the dominant SDD failure ([1: 4.1]). It follows that every artifact must justify its cost in reviewer attention, small diffs beat large ones ([1: 6.1]), and fresh-context review is worth its tokens ([1: 3.4]) while role-played review is not ([1: 3.1]).

*Corollary:* the system must notice when it is producing more review demand than a human is supplying, and slow down. That is what review debt in [05](05-workflows.md) is for.

---

## P7. Emergent structure, recorded

**Do not decide up front what can be decided later. Do record what has been decided.**

Scopes are discovered while building ([1: 6.3]). So: requirements up front (they are the "what" and the "why"), tasks a slice at a time, architecture as it emerges — captured in ADRs at the moment of decision, and in delta specs that fold into a baseline ([1: 4.4]) so the spec stays current without anyone rewriting it.

*Tension with P5:* determinism wants a complete graph; emergence wants a partial one. Resolved by making the graph *complete for the current slice* and explicitly open beyond it, with an `open-questions` list that is a first-class artifact rather than a gap.

---

## P8. No number nobody can produce honestly

**Reject metrics that look precise and predict nothing.**

No story points, no complexity scores, no debt index, no RICE ([1: 6.2]). Priority is a small ordinal a human sets. Risk is a three-value enum that *changes system behaviour* (it selects the autonomy tier), which is what earns it a place. Coverage is a ratchet and a map, never a target ([1: 5.5], [1: 5.6]).

*Test for any proposed field:* what decision changes when this value changes, and can the person filling it in produce it honestly? If either answer is missing, the field does not ship.

---

## How the principles resolve against each other

They conflict. The ordering below is the tiebreaker, and it is worth arguing about because it encodes a value judgement.

**P2 > P1.** When something can be either written or checked, check it.
**P6 > P5.** If determinism demands artifacts a human will not read, cut the artifacts. A less complete graph that gets reviewed beats a total one that does not.
**P4 > P3.** If avoiding duplication requires putting a large reference into always-on context, duplicate the small summary instead and link the rest.
**P7 > P5.** Do not fabricate a task graph to satisfy determinism. An empty, honest backlog is correct; a speculative one is not.
**P8 is absolute.** No exceptions have been found worth making.
