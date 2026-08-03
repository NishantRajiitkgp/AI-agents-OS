# ADAPTERS — what the coding tools actually read

What the OS must guarantee about its interface to the tools an agent runs inside. This is the
layer where the design's assumptions have been wrong most often: three of the four constraints
recorded in `AGENTS.md` contradicted something the design took for granted, and each was found
by running a measurement rather than by reasoning.

Every requirement here is about preferring a measured answer to a plausible one, and preferring
a control the tool enforces to a control written as prose an agent may read.

Requirements are never deleted. A withdrawn one keeps its entry, its status, and its reason.

---

## ADAPTERS-1 — What a tool reads is measured, not assumed

**Status:** active
**Rationale:** A nested instruction file that no tool reads is worse than no file: it looks
like configuration, it is edited in good faith, and it changes nothing. The measurement is
cheap and the assumption is expensive, and the record of which is which is the only thing that
stops the same guess being made again.

Where the system relies on a tool reading a file, the system shall record a measurement
showing that it does, naming the tool and the date.

If a file is found not to be read, then the system shall record that result rather than delete
the attempt, so the same approach is not tried again from scratch.

---

## ADAPTERS-2 — Path-scoped knowledge attaches to the path

**Status:** active
**Rationale:** Knowledge that applies to one directory costs nothing until that directory is
worked, and knowledge that must shape an approach before any file is opened cannot be scoped
that way. Putting each in the other's place is how the always-on budget gets spent on things
nobody needed and how the thing everybody needed arrives too late.

Where knowledge applies to a subset of paths, the system shall attach it to those paths rather
than to every turn.

Where knowledge must be available before any file is opened, the system shall load it on every
turn and count it against the budget.

---

## ADAPTERS-3 — Always-on context is a budget, not a preference

**Status:** active
**Rationale:** Four things load on every turn and share one budget. Past its limit a new one
requires deleting an old one, and that is the property that lets the total go down rather than
only up. A cap nobody is at is a cap that has already been spent.

The system shall measure the total lines loaded on every turn, across every contributor.

If the total would exceed its declared limit, then the system shall fail rather than accept
the addition.

The system shall forbid the measured total worsening, separately from the limit, so that
headroom left deliberately is not consumed by accretion.

---

## ADAPTERS-4 — A control the tool enforces beats a control the agent reads

**Status:** active
**Rationale:** Prose describing what an agent should not do is advice, and advice is followed
until the moment it matters. A hook that declines a call is the only checked-in artifact that
refuses rather than requests.

Where a rule must hold against the agent, the system shall implement it as something the tool
enforces at the point of the call.

If such a control cannot decide, then the system shall permit the call and report loudly that
it enforced nothing, rather than convert its own defect into a refusal of every call.

**Out of scope:** treating these controls as a security boundary. They run on the developer's
machine with the developer's permissions; GUARD-2 says where enforcement actually lives.

---

## ADAPTERS-5 — The measurements are re-run when the tools change

**Status:** active
**Rationale:** Every measurement here is a fact about a version. Tools ship, discovery
behaviour changes, and a recorded result quietly becomes a recorded belief. The re-run is
cheap; discovering by accident that a control stopped attaching is not.

When a tool the system depends on releases a major version, the system shall re-run the
discovery measurements and record the results against that version.

The system shall re-run them on a fixed interval regardless of releases, so that a result
cannot age indefinitely because no release was noticed.
