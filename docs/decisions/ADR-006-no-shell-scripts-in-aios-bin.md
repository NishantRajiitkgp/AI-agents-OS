# ADR-006 — Executable gate logic ships as binary subcommands, never as shell scripts

**Status:** accepted
**Date:** 2026-07-31
**Arose from:** `M0-01`, unplanned

## Context

`M0-01` was written as a PowerShell harness, on the reasoning that the target environment is
Windows/PowerShell and that M0 precedes the CLI by design. It could not run. The machine reports:

```
      Scope ExecutionPolicy
      ----- ---------------
 UserPolicy      Restricted        <-- set by Group Policy
CurrentUser    RemoteSigned
LocalMachine    RemoteSigned
```

`UserPolicy` is a Group Policy scope and takes precedence over the `Process` scope, so
`-ExecutionPolicy Bypass` does not override it. **No `.ps1` file executes on this machine at
all.** Inline `powershell -Command` is unaffected — the restriction is on script *files*, not on
the shell.

This is not an exotic configuration. It is the ordinary posture of a managed corporate Windows
machine, which is the stated target environment.

Three consequences reach past the harness:

1. [03 §3.4](../design/03-repository-architecture.md#34-genuinely-duplicated-configuration)
   illustrates the drift check as `aios/bin/check-drift.ps1`. That shape does not run here. The
   document labels it illustrative; this ADR is the record of it not hardening into a pattern.

2. **The dangerous failure mode is CI, not local.** GitHub-hosted Windows runners do not carry
   this policy, so a `.ps1` gate would pass in CI and be unrunnable on the developer's machine.
   That breaks the `aios check` ≡ CI equivalence that
   [06 §6](../design/06-quality-gates-and-testing.md#6-feedback-speed) calls a hard
   requirement, and converts every check into late feedback — losing the fast-feedback capability
   that DORA identifies as the thing making AI adoption net-positive.

3. Git on Windows runs hooks through its own bundled `sh`, so the `M2-04` pre-commit hook is not
   itself blocked. It must not delegate to a `.ps1`, which is the obvious way to write it.

## Decision

Everything executable under `aios/bin/` is a subcommand of the `aios` binary. No `.ps1`, no `.sh`,
no ecosystem-specific script runner. Adapter files and hook registrations may contain a one-line
invocation of the binary; they may not contain logic.

## Consequences

- **ADR-005's hard constraint is now justified from a second, independent direction.** It was
  accepted to avoid imposing a runtime on downstream projects. It also happens to be the only
  form that runs in the target environment at all, since a native executable is not subject to
  execution policy.
- The M0 probe harness cannot be a script. Its setup is a handful of static files and is done
  directly; the repeatable version is the `aios probe-adapters` subcommand at `M4-12`.
- Gate logic becomes testable, lintable, and reviewable as ordinary code rather than as strings.
  That was already desirable and is now compulsory.
- Anyone cloning the template onto a managed Windows machine inherits this property without
  discovering the problem themselves, which is the whole value of finding it at M0.
- **A general lesson worth keeping:** the roadmap listed three assumptions for M0 to test. This
  was not one of them, and it was found in the first hour by trying to run something. That is an
  argument for M0 being hands-on rather than a review exercise.

## Alternatives rejected

- **Ask for the execution policy to be relaxed.** Makes installability depend on an
  administrative exception, in a project whose premise is that it works on the machine you
  actually have. Non-portable to the next managed machine.
- **Sign the scripts.** `Restricted` blocks all script files regardless of signature; signing
  only helps against `AllSigned` or `RemoteSigned`. It does not solve this.
- **Wrap logic in inline `-Command` strings.** Runs, but logic embedded in command strings is
  unreviewable, unlintable, and untestable, and it is the shape of the `curl | sh` pattern that
  [07 §1.2](../design/07-security-and-agent-containment.md#12-command-execution)
  explicitly denies.
- **Write gate scripts as POSIX `sh` for git-bash.** Works for hooks specifically, but assumes a
  POSIX shell that is not guaranteed present, and splits gate logic across two languages — which
  doubles the surface the OS must keep correct.

## Revisit if

A second target environment shows no such restriction *and* the maintenance cost of subcommands
exceeds that of scripts. Note that even then the decision stands on ADR-005's reasoning alone, so
this trigger would justify at most a relaxation for non-shipped developer utilities — never for
anything a gate depends on.
