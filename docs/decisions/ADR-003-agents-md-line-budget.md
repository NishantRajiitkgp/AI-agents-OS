# ADR-003 — `AGENTS.md` line budget starts at 150

**Status:** accepted
**Date:** 2026-07-31
**Decides:** `P0-4`

## Context

[P4] requires that always-on context be a fixed, small, enforced allowance, because instruction
adherence collapses well before the context window fills. The budget is what makes the
instruction surface capable of *shrinking*: past the limit, adding a rule requires naming the one
it replaces, which inverts the asymmetry that makes every system in this space worse in month six
than in month one.

The design uses 150 throughout and is explicit that it is a convergent practitioner estimate
[01: 2.2], not a measurement. It is listed as genuinely unproven in the architecture's own
assessment.

## Decision

150 lines. Stored as a key in `aios/config.yml`, enforced as a Contract gate from M1, with the
growth ratchet from `M5-02` layered on top once M5 lands.

## Consequences

- The budget is enforced from M1 even though the ratchet arrives at M5. The budget alone caps the
  size; the ratchet is what stops it sitting permanently at the cap.
- Because it is a config key, changing it is a one-line reviewable commit. That is deliberate:
  this number should be **tuned against observation, not defended**. A budget nobody may change
  becomes a rule people route around.
- Adopting an unmeasured number means the first real signal will come from friction — the point
  at which a fact that demonstrably changes agent behaviour cannot be added. That is the datum
  to watch for, and it is written into the revisit trigger below.

## Alternatives rejected

- **100.** Tighter and would create deletion pressure earlier, but there is no more evidence for
  100 than for 150, and an over-tight root budget pushes facts down into nested `AGENTS.md`
  files, where they are only loaded if the agent happens to open that directory. That converts a
  visible budget problem into an invisible coverage problem.
- **200.** Loosens the one constraint that does the most work, on no evidence.
- **Set it after `AGENTS.md` is drafted (`M1-02`).** Inverts the control. The budget exists to
  constrain the draft; letting the draft set the budget guarantees it is exactly large enough for
  whatever was written first.

## Revisit if

Either of these is observed: (a) `AGENTS.md` is at budget and a fact that demonstrably changes
agent behaviour cannot be added without deleting one that also does; or (b) a measurement of
instruction adherence against file length produces a real number, at which point this stops being
an estimate.
