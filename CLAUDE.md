@AGENTS.md

<!-- Claude Code specific notes below this line only. -->

This file is an import shim, and it is deliberately not a symlink. On a checkout with
`core.symlinks` disabled — the Git for Windows default, and the setting on the development
machine — a committed symlink arrives as a small plain file whose entire content is the
string `AGENTS.md`. It has the right name, it is not empty, and every tool that reads it
sees a valid file. A CI check asserts the import line above is present rather than trying to
recognise that failure by its shape.

`.claude/` is not a Claude-only tree. Cursor was measured reading skill descriptions,
subagent descriptions, and command bodies from it. Anything placed there is loaded by both
tools, so project knowledge belongs in `AGENTS.md` and this tree holds only tool wiring.
