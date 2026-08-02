# ADR-012 — Command denial is asymmetric across tools, and advisory in both

**Status:** accepted
**Date:** 2026-07-31
**Supersedes:** nothing. Corrects an assumption in
[03 §3.4](../design/03-repository-architecture.md).

## Context

`M2-08` requires a command-execution deny list at the tool layer.
[03 §3.4](../design/03-repository-architecture.md) assumed this would be one list generated
into two structurally similar artifacts, the way the MCP allowlist and hook registration rows
are. That assumption was not checked against either tool's actual configuration surface.

It is wrong, and the two tools differ more than in spelling.

**Claude Code** takes a deny array directly: `.claude/settings.json` under
`permissions.deny`, with entries shaped `Bash(rm -rf:*)`. Deny beats allow.

**Cursor's IDE agent has no repo-level command deny list.** `.cursor/permissions.json`
supports `terminalAllowlist` — an allowlist, with prefix matching — and no denylist key
exists. Two near-misses are worth naming so they are not rediscovered as options:

- `.cursor/cli.json` does support `permissions.deny: ["Shell(rm)"]`, structurally almost
  identical to Claude's. It governs the Cursor CLI only, not the IDE agent.
- Cursor can read `.claude/settings.json`, but the documented compatibility surface is
  **hooks only**. There is no evidence it reads Claude's `permissions` block, so a deny array
  written there is best assumed ignored by Cursor.

The only checked-in artifact that actually blocks a command in the Cursor IDE is a
`beforeShellExecution` hook in `.cursor/hooks.json`: a regex matcher against the full command
string, returning `permission: "deny"`, with `failClosed: true` to block rather than pass when
the hook itself errors.

There is also a ceiling on what any of this can achieve. Cursor's own documentation states in
two places that allowlists and the Auto-review classifier are **not a security boundary** —
"best-effort convenience". Repo-level and user-level permission files are *concatenated*, not
overridden, so a repository can only widen a developer's allowlist and can never narrow it.
The Run Mode itself — whether commands are approved at all — is chosen in the Settings UI or
by a team administrator, and cannot be pinned by a file in the repository.

## Decision

**One source, two dissimilar outputs, and no pretence of symmetry.**

`deny_commands` in `aios/config.yml` stays the single list. It renders to:

| Tool | Artifact | Mechanism |
|---|---|---|
| Claude Code | `.claude/settings.json` | `permissions.deny` entries |
| Cursor IDE | `.cursor/hooks.json` + hook script | `beforeShellExecution`, `failClosed: true` |
| Cursor CLI | `.cursor/cli.json` | `permissions.deny`, if the CLI is used |

Patterns are regexes matched against the whole command string, because the hook matcher is a
regex and a prefix list cannot express `curl … | sh`.

**The tool layer is classified Advisory, not Contract**, and the deny list is documented as
such. It is a guardrail against the obvious slip, not a containment boundary.

## Consequences

The design's claim that the permission layer is a *structural* defence needs narrowing.
`AGENTS.md` says an injected instruction to exfiltrate a secret fails "because the secret is
unreachable". That remains true where the reachability is enforced by something outside the
agent's tool configuration — a missing credential, a server-side branch rule. It is not true
by virtue of a deny list, in either tool, and a deny list is not what makes it true.

What actually contains the agent is unchanged and is where the effort belongs: server-side
required review on the protected set, and CI gates the agent cannot edit in the pull request
that trips them. This ADR lowers the claimed strength of one layer; it does not weaken the
system, because that layer was never the one holding.

Effort should therefore not be spent making the regexes airtight. A deny list that is 90%
effective against accidents and 0% effective against intent is exactly what an Advisory
control is, and polishing it toward 95% buys nothing that review does not already provide.

Because the Cursor side is a hook rather than a data file, the generator at `M2-03` produces
asymmetric output, and `M4-07` — which registers hooks in both tools — now overlaps this
decision. The hook script is provisional Python and becomes `aios hook before-shell` when the
binary exists, per [ADR-006](ADR-006-no-shell-scripts-in-aios-bin.md).

## Revisit when

Cursor ships a repo-level `terminalDenylist`, or documents the IDE agent reading Claude's
`permissions` block. Either would make symmetric generation possible and this ADR's central
asymmetry unnecessary.
