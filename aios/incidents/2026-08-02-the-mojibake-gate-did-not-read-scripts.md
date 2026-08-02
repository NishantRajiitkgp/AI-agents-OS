---
date: 2026-08-02
detected_by: >-
  the first CI run on the first commit, plus a manual sweep that read more files than the gate did
control: >-
  the hygiene mojibake scan now covers script suffixes, not markup and configuration only
blocks_work: false
---

# 2026-08-02 — Four more double-encoded files, two of which the gate was not reading

**Severity:** low in effect, high in what it says about the control.
**Detected by:** the byte-order-mark and mojibake step of `hygiene.yml`, on the first CI run
that ever reached it — and, for the two files that step does not read, by scanning the whole
tracked set by hand afterwards.

## What happened

The incident of 2026-07-31 recorded the same corruption, repaired ten files, and produced a
gate. Four further files carried it into the first commit anyway: `aios/config.yml` (a
byte-order mark and nine sequences), `aios/ratchets.yml` (a byte-order mark),
`.github/scripts/check-memory.py` (ten sequences) and
`.github/scripts/validate-references.py` (two). All of the damage sat in comments and
docstrings, so nothing behaved differently and nothing failed to parse — the same silence as
the first time.

The gate caught the two YAML files the moment it ran. It did not catch the two Python files,
and would not have caught them on any future run either, because the step is named for
tracked *text* files but its file list was markup and configuration: `.md`, `.mdc`, `.yml`,
`.yaml`, `.toml`, `.rs`, `.txt`, `.json`. The largest body of prose in this repository is
docstrings and comments in the provisional gate scripts, and the gate written to protect
prose from silent corruption was not reading any of it.

Two of the four are the gate scripts themselves.

## Why the first CI run is when this surfaced

The step sits below the ratchet step in `hygiene.yml`, and the ratchet step failed on the
same run, so the job stopped before reaching it. The corruption became visible only on the
second push. A gate positioned below a gate that fails is a gate that has not run, and until
this repository had CI at all, none of them had ever run.

## Resolution

Repaired by the procedure the first incident established and the workflow's own failure
message prints: decode as UTF-8, strip the byte-order mark, re-encode the corrupted runs as
cp1252 to recover the original bytes, decode those with a strict UTF-8 decoder. A run was
rewritten only where the round trip produced exactly one character, which is what keeps a
greedy match from consuming the character after it. Twenty-one sequences and two byte-order
marks; the whole tracked set then re-scanned and clean.

## The control

The step's file list gains `.py`, `.sh` and `.ps1`. This is a one-line change and it is the
entire lesson: the first incident produced a control that named the right rule and applied it
to the wrong set, and nothing in between noticed, because a gate that passes and a gate that
is not looking are indistinguishable from the outside.

## What this does not fix

The list is still a list. Any suffix added to this repository later is outside the scan until
someone remembers to add it, and the failure mode above is precisely that nobody does. The
honest alternative is to scan every tracked file and exclude known-binary suffixes instead,
so that the default for a new kind of file is *checked* rather than *ignored*. That is not
done here because the exclusion list has the same forgettability problem pointed the other
way, and getting it wrong makes the gate fail on binaries rather than miss corruption — a
better direction to be wrong in, but a change worth making deliberately rather than while
repairing something else.
