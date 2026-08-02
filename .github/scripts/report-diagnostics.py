#!/usr/bin/env python3
"""Run a command and, when it fails, republish its output as workflow annotations.

A failing check writes its diagnostics to the job log, and the REST endpoint serving job logs
refuses anyone without administrator rights — on a public repository as readily as on a private
one. Annotations are served to anyone who can read the repository. So a diagnostic that exists
only in the log is unreadable to most of the people it is addressed to, and to every tool
acting on their behalf.

That is not hypothetical here. A formatting diff held this repository's build red across three
pushes while the diff itself could not be retrieved, and the checks below it never ran, so
whether the binary compiled at all stayed unknown for the same three pushes.

The output still goes to the log, unchanged and in full. This adds a second copy where it can
be read; it moves nothing and it suppresses nothing. The exit code is passed through, so a
check that failed still fails.
"""
import argparse
import subprocess
import sys

# Below the documented caps rather than at them. GitHub accepts ten error annotations per step
# and truncates an over-long message, and a diagnostic silently cut in half is the failure this
# script exists to prevent — so the last slot is kept for saying how much was left out.
MAX_ANNOTATIONS = 9
CHUNK_LINES = 90


def escape(text: str) -> str:
    """Escape the data portion of a workflow command, per the runner's parser."""
    return text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def escape_property(text: str) -> str:
    """Property values carry two more delimiters than the data portion does."""
    return escape(text).replace(":", "%3A").replace(",", "%2C")


def annotate(title: str, message: str) -> None:
    print(f"::error title={escape_property(title)}::{escape(message)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True,
                        help="what the annotation is called in the pull request")
    parser.add_argument("command", nargs=argparse.REMAINDER,
                        help="the command to run, after a bare --")
    args = parser.parse_args()

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("no command given", file=sys.stderr)
        return 2

    try:
        completed = subprocess.run(command, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
    except FileNotFoundError:
        annotate(args.title, f"{command[0]} is not on PATH")
        return 2

    output = (completed.stdout or "") + (completed.stderr or "")
    sys.stdout.write(output)
    sys.stdout.flush()

    if completed.returncode == 0:
        return 0

    lines = output.rstrip("\n").splitlines()
    if not lines:
        annotate(args.title, f"exited {completed.returncode} and wrote nothing")
        return completed.returncode

    groups = [lines[at:at + CHUNK_LINES] for at in range(0, len(lines), CHUNK_LINES)]
    shown = groups[:MAX_ANNOTATIONS]
    for index, group in enumerate(shown, start=1):
        title = f"{args.title} ({index}/{len(shown)})" if len(shown) > 1 else args.title
        annotate(title, "\n".join(group))

    remaining = sum(len(group) for group in groups[len(shown):])
    if remaining:
        annotate(f"{args.title} (truncated)",
                 f"{remaining} further line(s) are in the job log and not here.")

    return completed.returncode


if __name__ == "__main__":
    sys.exit(main())
