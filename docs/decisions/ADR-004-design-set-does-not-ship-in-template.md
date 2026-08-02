# ADR-004 — The design set stays in the OS repository and does not ship in the template

**Status:** accepted
**Date:** 2026-07-31
**Decides:** `P0-5`

## Context

The eleven numbered design documents carry the reasoning behind every mechanism the template
ships. Shipping them gives each cloned project that reasoning on hand. It also puts eleven
documents into a repository whose central argument is that artifact volume exceeding review
capacity is a dominant failure mode, and that every document must justify its cost in reader
attention.

## Decision

`docs/design/` stays in the OS repository. The template ships without it.

## Consequences

- A cloned project gets the mechanisms without the prose behind them. The mitigations are that
  **ADRs travel** — they live in `docs/decisions/`, are project-specific, and are written at the
  moment of decision — and that each shipped gate names the design document it derives from by
  **link rather than by copy**.
- This is the P3-consistent outcome. A copy of the design set inside every cloned project is a
  copy that diverges from the OS repository the first time a document changes, producing two
  places that can disagree about why a gate exists.
- The cost is real and falls on a downstream maintainer asking "why does this gate exist", who
  must follow a link out of their own repository to find out. That is the trade being accepted.
- The root markdown cap of five files is unaffected either way, since the design set was never
  going to sit at root.

## Alternatives rejected

- **Ship the full set.** Eleven documents into a repository preaching restraint, and they go
  stale relative to the OS repository immediately.
- **Ship a one-page pointer.** Still a file to maintain and keep accurate, and it buys nothing
  over a single link in `AGENTS.md` or `README.md`, which are files that have to exist anyway.

## Revisit if

Downstream users repeatedly ask why a given gate exists, or a gate is repeatedly overridden and
the override reasons indicate its rationale was not available at the point of decision. Either
observation means the link was not enough.
