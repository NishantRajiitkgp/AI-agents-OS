#!/usr/bin/env python3
"""Review debt (M5-09), and the half of it that was dropped.

PROVISIONAL. Moves into the binary at `M1-08`.

The design asked for "merged tasks whose diffs the human spent under a threshold on". **Time
spent on a diff is not measurable**, and no amount of care makes it so. Nothing in a forge
records attention. What is recorded is when a review was submitted, which is wall-clock time
between two events with lunch, a meeting and three other tabs inside it — and a proxy that
wrong does not become right by being enforced. ADR-014 records that decision; the enforcement
based on time is dropped rather than left as decoration, because a control that cannot be
measured misleads people into thinking the thing is being watched.

What *is* recorded, and is kept:

- **Approvals carrying no comment at all.** Not proof of inattention, but the design's actual
  target is a person in a flow state who has stopped noticing they stopped reading, and that
  person approves without comment. It does not catch a determined circumventer, whom no proxy
  would catch either.
- **Diff size per review cycle.** Reading does not scale linearly with lines and everyone
  knows it, so the budget is on the diff rather than on the reader.

Above the limit, `aios next` refuses to hand out work and says review is the bottleneck.
Refusing to create more work is the only lever that acts on the actual constraint; every other
response adds to the queue that is already the problem.

Reads review data as JSON — from `gh pr list` in CI, or a file in tests — because this
repository has no reviews and inventing a shape to match would be the same mistake as the time
proxy.

Exit 0 within limits, 1 over, 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

WITHIN, OVER, COULD_NOT_RUN = 0, 1, 2

DEFAULTS = {"window": 10, "max_uncommented_percent": 50, "max_diff_lines": 400}


def summarise(reviews: list[dict], window: int) -> dict:
    recent = reviews[-window:] if window else reviews
    if not recent:
        return {"count": 0}
    uncommented = [r for r in recent
                   if r.get("state") == "APPROVED" and not (r.get("comments") or 0)]
    oversized = [r for r in recent if (r.get("diff_lines") or 0) > DEFAULTS["max_diff_lines"]]
    return {
        "count": len(recent),
        "uncommented": len(uncommented),
        "uncommented_percent": round(len(uncommented) * 100 / len(recent)),
        "oversized": len(oversized),
        "median_diff_lines": sorted(r.get("diff_lines") or 0 for r in recent)[len(recent) // 2],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reviews", type=Path,
                        help="JSON list of {state, comments, diff_lines}")
    parser.add_argument("--root", type=Path)
    args = parser.parse_args()

    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    try:
        config = yaml.safe_load((root / "aios" / "config.yml").read_text(encoding="utf-8"))
        limits = {**DEFAULTS, **((config.get("review_debt") or {}) if config else {})}
    except (OSError, yaml.YAMLError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    if not args.reviews:
        print("No review data supplied, so review debt is not being measured. This is the "
              "state this repository is in: zero merged pull requests, therefore zero "
              "evidence about whether anyone is still reading.")
        print("The time-on-diff half of this control was dropped, not deferred — see "
              "ADR-014. What remains is measurable and waits for reviews to exist.")
        return COULD_NOT_RUN

    try:
        reviews = json.loads(args.reviews.read_text(encoding="utf-8"))
        if not isinstance(reviews, list):
            raise ValueError("expected a list of reviews")
    except (OSError, ValueError) as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return COULD_NOT_RUN

    summary = summarise(reviews, limits["window"])
    if not summary["count"]:
        print("no reviews in the window.")
        return WITHIN

    print(f"{summary['count']} review(s) in the window: {summary['uncommented']} approved "
          f"with no comment, median diff {summary['median_diff_lines']} lines, "
          f"{summary['oversized']} over the {limits['max_diff_lines']}-line budget.")

    over = False
    if summary["uncommented_percent"] > limits["max_uncommented_percent"]:
        print(f"::error::{summary['uncommented_percent']}% of recent reviews were "
              f"approvals with no comment, over the "
              f"{limits['max_uncommented_percent']}% limit. `aios next` should "
              f"stop handing out work: review is the bottleneck, and adding to the queue is "
              f"the one response that makes it worse.")
        over = True
    if summary["oversized"]:
        print(f"::warning::{summary['oversized']} diff(s) over the budget. Reading does not "
              f"scale with lines, so the budget is on the diff rather than on the reader.")

    return OVER if over else WITHIN


if __name__ == "__main__":
    raise SystemExit(main())
