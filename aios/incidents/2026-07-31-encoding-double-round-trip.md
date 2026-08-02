---
date: 2026-07-31
detected_by: >-
  a reader noticing mojibake in a committed file
control: >-
  hygiene.yml rejects any file carrying a byte-order mark or the cp1252-through-utf-8 mojibake
  signature
blocks_work: false
---

# 2026-07-31 — Ten state files silently double-encoded by a text round-trip

**Severity:** would have been high if committed. Caught before the initial commit.
**Detected by:** a `StrReplace` that failed to match, because the text on disk no longer
matched the text that had been written there.

## What happened

During `M1-01`, relative Markdown links broken by moving the repository root were repaired
with a PowerShell helper that read each file, replaced a substring, and wrote it back:

```powershell
$c = Get-Content -LiteralPath $path -Raw
Set-Content -LiteralPath $path -Value $c.Replace($from, $to) -Encoding UTF8
```

Both halves are wrong in a way that only shows up together.

`Get-Content` in Windows PowerShell 5.1 defaults to the system ANSI code page, not UTF-8,
for a file with no byte-order mark. Every file involved was UTF-8 without a BOM. So an em
dash — three bytes `E2 80 94` — was decoded as three separate cp1252 characters. Then
`-Encoding UTF8` re-encoded each of those three as UTF-8, producing six bytes where there
had been three, and prepended a BOM for good measure.

Ten files were affected: `task.md`, seven ADRs, the probe prompt, and the probe results
matrix — 93 corrupted sequences in `task.md` alone. Nothing errored. Every file still
opened, still parsed as Markdown, and still rendered. It simply rendered each em dash as
three stray Latin-1 characters instead.

(The corrupted sequences are deliberately not quoted here. This file is checked by the gate
described below, and a report that embeds the byte pattern it warns about would fail it.)

## Why it mattered more than it looks

The corrupted set was almost exactly the OS's own memory: the decision records and the
measurement matrix from M0. Those exist to be the durable account of *why* things were
decided, and they had been damaged by a routine edit that reported success.

This is the failure mode the whole design is built against, reproduced against the design's
own artifacts on the first day of implementation: a silent, plausible-looking corruption
that no step in the process was positioned to notice. It was found by luck — a later edit
happened not to match — rather than by any control.

## Resolution

The corruption was deterministic and therefore reversible: decode as UTF-8, strip the
inserted BOM, re-encode as cp1252 to recover the original bytes, decode those as UTF-8 with
a strict decoder so that any failure is loud. All ten files were restored and verified
byte-clean, with a backup taken first. The strict decoder is what makes the reversal safe
to run: a lossy repair would have thrown rather than written.

## The control that now prevents it

1. **A hygiene gate rejects a BOM or mojibake in any tracked text file**
   (`.github/workflows/hygiene.yml`). The signatures are unambiguous: a leading `EF BB BF`,
   and the three byte sequences a re-encoded dash, symbol, or accented letter always
   produces. They are spelled as hex escapes in the workflow and deliberately not quoted
   here, for the same reason — no legitimate file in this repository contains them, and a
   file that describes them must not become the exception. This turns a silent corruption
   into a failed check on the pull request that introduces it.

2. **Text edits do not go through shell text round-trips.** Editing tools that preserve
   encoding are used instead. Where a bulk edit genuinely needs scripting, it must read and
   write through an explicit UTF-8 encoding with a strict decoder, never through a default.

The gate is the real control; item 2 is a convention, and conventions are what the OS
exists to replace. Item 1 holds when item 2 is forgotten, which is the point.

## What this does not fix

The gate detects this *specific* corruption signature, not encoding damage in general — a
file mangled a different way would still pass. The general defence is that the design set
and the ADRs are content-addressed by git once committed, so any later unintended change to
them shows up as a diff in review. That defence did not exist here only because the initial
commit had not happened yet, which is itself an argument for committing the skeleton early
rather than perfecting it first.
