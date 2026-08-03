---
date: 2026-07-31
detected_by: >-
  rustup-init download failing, then curl against every rust-lang.org host
no_control_because: >-
  the block is network policy outside this repository's reach. The recorded route is to wait
  for CI rather than work around it, and each workaround was measured and is worse
blocks_work: false
---

# 2026-07-31 — The chosen ecosystem cannot be installed on the development machine

**Severity:** blocks `M1-08` through `M1-18`. Every remaining M1 task is an `aios`
subcommand, so nothing further in the milestone can proceed locally.
**Detected by:** attempting the `M1-08` toolchain install. Not by any check — no gate was
positioned to ask whether the ecosystem ADR-005 selected was obtainable here.

## What happened

`M1-08` needs a Rust toolchain. The machine had none, so the install was attempted three
ways. All three failed at the same layer.

| Attempt | Result |
|---|---|
| `Invoke-WebRequest` for `rustup-init.exe` | connection closed on send |
| `curl.exe` for the same URL | `(35) Recv failure: Connection was reset` |
| `winget install Rustlang.Rustup` | `InternetOpenUrl() failed, 0x80072eff` |

winget fails identically because its manifest points at `static.rust-lang.org`, the same
host the direct download uses. It was not an independent route.

The block is hostname-based, and the evidence separates it cleanly from the alternatives:

- **DNS resolves.** `static.rust-lang.org` → `151.101.210.137`, `crates.io` → `151.101.130.137`.
  Not a DNS block.
- **TCP 443 connects.** `Test-NetConnection` succeeds against every blocked host. Not an IP
  or port block.
- **The TLS handshake is reset**, and plain HTTP to the same host returns `503` rather than
  timing out — a filtering appliance answering, not a dead route.
- **Reachability is selective, not general.** `github.com` and `pypi.org` both return `200`.
  `static.rust-lang.org`, `crates.io`, `sh.rustup.rs` and `forge.rust-lang.org` are all reset.
- **`objects.githubusercontent.com` is also reset**, which closes the obvious escape route.
  GitHub's API and HTML host are permitted, but the host that serves release *assets* is not,
  so no published binary can be fetched here by any route — not a mirrored `rustup-init`, not
  anything else. The allowance is for browsing GitHub, not for downloading from it.

So the filter inspects the requested hostname and denies the Rust ecosystem specifically,
while permitting the ecosystems already in use here. There is no proxy configured, in the
environment or in the registry, so there is nothing to route around.

## Why it matters more than a missing tool

[ADR-005](../../docs/decisions/ADR-005-reference-implementation-ecosystem.md) chose Rust on
one deciding constraint: a cloned project must be able to invoke `aios/bin/` without adopting
the OS's runtime. That reasoning is untouched by this. A firewall rule is not an argument
about language design, and reversing a decision because of one machine's network policy would
be exactly the reflex the decision register exists to prevent.

What this does expose is that ADR-005 weighed the *properties* of the ecosystem and never
asked whether it could be obtained in the environment the work happens in. Availability was
assumed rather than measured — the same shape as the two constraints already recorded in
`AGENTS.md`, both of which contradicted a design assumption on contact with the machine.
This is the third, and the pattern is now strong enough to be worth naming: this repository
keeps discovering that the environment, not the design, is the binding constraint.

It also makes the deferred initial commit load-bearing in a way it was not this morning. Two
things now wait on the remote existing: `T-950a` cannot reach `done` without a commit to
record, and CI is the only place a Rust build can happen at all.

## Resolution

Not resolved. `M1-08` is held rather than worked around, because every route to working
around it is worse than waiting:

- **Vendoring a toolchain by hand** would produce a build nobody can reproduce, which is the
  opposite of what `M1-08` exists to establish ("pin the toolchain in-repo so contributor and
  CI builds cannot diverge").
- **Switching ecosystem** would trade a decision made on measured constraints for one made on
  a firewall rule, and Python — the reachable alternative — fails ADR-005's deciding
  constraint outright.

## The control this produces

**Before an ecosystem decision is recorded, its toolchain and package registry must be
fetched successfully from the machine the work happens on, and the result noted in the ADR.**

ADR-005 has a constraint table with rows marked `assumed` and `verified`. Reachability was
not a row in it. It is the cheapest possible check — one request — and it would have caught
this before the decision was recorded rather than three milestones after.

This does not become a CI gate. CI runs on GitHub's network, where the answer is always yes;
a gate there would assert something true in the only place it cannot fail. It belongs in the
ADR template as a required row, which is a documentation control, and the honest note is that
documentation controls are weaker than gates.

## 2026-08-03 — `blocks_work` set to false, and one measurement above is now wrong

Appended rather than edited, because the record of what was believed is the point of keeping
these. Nothing above has been changed except the frontmatter flag, and this section says why.

**The claim that no published binary can be fetched here is false as of today.** The release
built at `v0.1.0` was downloaded to this machine over
`github.com/.../releases/download/`, 354,304 bytes, and its SHA-256 matches the checksum
published beside it. The binary then ran: `aios --version`, `aios validate`, `aios list`, and
`aios next` — which is what produced this edit, by refusing to hand out work while this
incident was open.

Whether the earlier measurement was wrong or the network policy changed is not knowable from
here, and guessing between them would be inventing the more flattering one. What is knowable
is that the route works today and was checked rather than assumed.

**What this does not change.** The toolchain is still unreachable: nothing here was compiled
locally, and CI remains the only compiler. ADR-005 is untouched, and so is the control this
incident produced. What has gone is the consequence — `M1-08` through `M1-18` were held
because no binary could exist on this machine, and one now does, checksum-verified, built by
the only compiler that can reach the ecosystem.

`blocks_work` is therefore false. The incident stays open, because the condition it names is
still true and its control is still owed a row in the ADR template.

## What this does not fix

Nothing prevents the same discovery for a future dependency. The general defence is that the
supply-chain work at M3 has to pull from a registry, and it will fail loudly here for the
same reason — but that is a later milestone finding an earlier problem, which is the delay
this incident is about.
