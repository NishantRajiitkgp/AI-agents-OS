# Glossary

Domain terms with precise definitions. A term earns an entry here only when it is used in a
narrower or different sense than its ordinary meaning, and getting it wrong would change
what someone builds. Restating a common word is noise; this file competes for the same
attention as everything else an agent reads.

Terms are defined once. Where a term has a longer treatment in the design set, the entry is
one line and a link — the design document is the truth and this is the index (P3).

---

**Contract gate** — a check that blocks a merge and cannot be waived by the agent or the
author. Distinct from a Ratchet, Advisory, or Report gate, which fail differently on
purpose. See [06 §1](../docs/design/06-quality-gates-and-testing.md).

**Done** — a task state reached only when a machine-verified record says its acceptance
criteria hold. It is not a claim an agent or a human can make directly, which is the single
property M1 exists to prove.
See [D-010](../docs/design/10-decision-register.md#d-010--done-requires-a-machine-verified-record).

**Override** — not a flag, a setting, or a re-run. It is a human commit adding an incident
file whose frontmatter names the Contract gate, the date, the approver and the reason. The
agent cannot perform one, cannot request one, and cannot edit an existing record. Three
against one gate in thirty days demote it.
See [06 §1](../docs/design/06-quality-gates-and-testing.md).

**Ratchet** — a gate that permits the current value of a metric and forbids any worsening of
it, rather than demanding a fixed threshold. Used where an absolute standard would fail a
legacy codebase on day one and be switched off.

**Tier** — the `aios/config.yml` key that determines which gates block and how much autonomy
an agent has. It changes gate policy and nothing about the folder layout
([03 §1.3](../docs/design/03-repository-architecture.md#13-the-structure-does-not-change-with-project-size)).

**The always-on set** — the files a tool loads into every session regardless of what is being
worked on, measured rather than assumed. It is the denominator the context budget is
enforced against.
See [ADR-010](../docs/decisions/ADR-010-budget-covers-the-measured-always-on-set.md).

**Flattened symlink** — a file that was committed as a git symlink (mode `120000`) and
checked out on a machine with `core.symlinks=false` as a small plain text file whose
contents are the link target. It looks valid to every tool that reads it, which is why it
needs a detector rather than a convention.
See [ADR-008](../docs/decisions/ADR-008-symlink-detection-and-shim-validation.md).
