# ADR-008 — Flattened symlinks are detected from the git index; shims are validated positively

**Status:** accepted
**Date:** 2026-07-31
**Arose from:** `M0-05`

## Context

[03 §3.3](../design/03-repository-architecture.md#33-claudemd-is-an-import-shim-never-a-symlink)
specifies a CI check that greps `CLAUDE.md` for the flattened-symlink signature — "a file whose
entire trimmed content matches a bare path ending in `.md`" — with `03 §3.4` giving the regex
`^[\w.\-/]+\.md$`. `M0-05` verified this against a real Windows checkout.

**The failure mode reproduced exactly as documented.** This machine has `core.symlinks=false` at
**system** scope, which is the Git for Windows default. A repository containing a mode `120000`
entry clones to a 9-byte plain file with the `Archive` attribute, no reparse point, and content
exactly `AGENTS.md`. Nothing warns. Every tool reading it sees a valid file.

The regex catches that case. Measured against a corpus, it misses three others that are equally
broken and equally silent — an empty file, a whitespace-only file, and a backslash-separated
target path — and it *passes* a `CLAUDE.md` that has drifted into duplicated content, which D-001
forbids outright. Score: 4 of 7. A positive check scored 7 of 7 on the same corpus.

## Decision

Three checks, each doing a different job. The first is the primary gate.

1. **Repository level, machine-independent — the CI gate.** No entry in the git index may have
   mode `120000`. This enforces D-002's "never a symlink" rule directly and exactly, with no
   heuristics and no content inspection. It gives the same answer on every machine, which is what
   [06 §6](../design/06-quality-gates-and-testing.md#6-feedback-speed) requires of
   local versus CI.

2. **Working-copy level — the local diagnostic.** Any mode `120000` entry must be a reparse point
   on disk. This detects *your checkout is broken* rather than *the repo is broken*, and is the
   check that would have caught the original problem. It is machine-dependent by nature and so
   cannot be the CI gate.

3. **Shim level — positive validation.** A shim file must contain its import directive on a line
   of its own. A positive assertion of the required shape, not a negative match against one
   known-bad shape.

## Consequences

- **The content regex in `03 §3.4` is superseded.** That snippet is labelled illustrative, but the
  rule it implements in `03 §3.3` is not, and this ADR corrects the rule.
- **Check 1 applies from M1 even though `CLAUDE.md` does not ship** ([ADR-007](ADR-007-claude-adapter-deferred.md)).
  Any symlink anyone commits — from any machine, for any reason — flattens silently on this one.
  The check is worth having regardless of which adapter files exist.
- **Check 3 has no target until a shim ships.** It is specified now, while the evidence is fresh,
  and wired up when a second tool arrives.
- Check 3 hardcodes a vendor-specific import syntax that may change between releases. Accepted:
  it fails loudly with a red build rather than silently, which is the correct direction for this
  class of failure.
- **The general lesson, which outlives this file:** an adapter shim should assert the shape it
  requires, never merely fail to match one shape it forbids. The set of ways to be wrong is
  unbounded; the set of ways to be right is one.

## Alternatives rejected

- **Keep the content regex alone.** Measured 4 of 7, and silently passes content drift — the
  exact failure D-001 exists to prevent.
- **Set `core.symlinks=true`.** A per-machine setting needing privileges on Windows. The entire
  point is that the failure happens on machines nobody configured, so a fix requiring
  configuration does not address it.
- **Ban symlinks by convention.** A preference, not a control ([P2](../design/02-principles.md)).

## Revisit if

Git on Windows makes symlinks reliable by default — which is also
[D-002](../design/10-decision-register.md)'s revisit trigger, and the two should be
reopened together.
