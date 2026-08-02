#!/usr/bin/env python3
"""Run the test suite in parallel shards.

PROVISIONAL. Moves into the binary with the rest of the gate logic (ADR-006).

Serially the suite takes about six minutes against a sixty-second budget (06 §6). Almost none
of that is work: the gates are separate programs, so nearly every test spawns an interpreter
and waits for it, and the wall clock is interpreter startup repeated a few hundred times. That
is latency with no computation behind it, and it is the kind that parallelises.

Sharded by test class rather than by module or by test. By module, one large module sets the
floor for the whole run. By test, the identifier list gets long enough to strain a command
line on Windows. Class granularity is small enough to balance and large enough to stay short.

Separate processes rather than threads, because unittest's result objects are not built to be
shared and a suite that races is worse than a slow one.

Exit codes: 0 all passed · 1 something failed · 2 could not run.
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

COUNT = re.compile(r"^Ran (\d+) test", re.MULTILINE)
PASSED, FAILED, CANNOT_RUN = 0, 1, 2


def classes(start: Path) -> list[str]:
    """Every test class, as a dotted identifier unittest can be given directly.

    Parsed rather than discovered. unittest's discovery wants the start directory to be an
    importable package, and `tests/` deliberately is not one; and parsing means the parent
    process never imports a test module, so a broken one is reported by the shard that runs it
    rather than taking down the runner before anything has run.
    """
    found: list[str] = []
    for path in sorted(start.glob("test_*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as exc:
            raise RuntimeError(f"{path.name} does not parse: {exc}")
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            # Named Test*, or holding a test method. The second case matters: a shared base
            # class carrying its own test would otherwise never be handed to any shard.
            has_test = any(isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
                           and item.name.startswith("test")
                           for item in node.body)
            if node.name.startswith("Test") or has_test:
                found.append(f"{start.name}.{path.stem}.{node.name}")
    return found


def shard(names: list[str], count: int) -> list[list[str]]:
    """Round-robin, so a run of slow classes in one module does not land in one shard."""
    buckets: list[list[str]] = [[] for _ in range(max(1, min(count, len(names) or 1)))]
    for index, name in enumerate(names):
        buckets[index % len(buckets)].append(name)
    return [bucket for bucket in buckets if bucket]


def run(bucket: list[str], root: Path) -> tuple[int, int, str, float, list[str]]:
    began = time.perf_counter()
    result = subprocess.run([sys.executable, "-m", "unittest", "-q", *bucket],
                            cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    output = result.stdout + result.stderr
    match = COUNT.search(output)
    return (result.returncode, int(match.group(1)) if match else 0, output,
            time.perf_counter() - began, bucket)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--jobs", type=int, default=0,
                        help="shards to run at once; 0 means one per CPU")
    parser.add_argument("--serial", action="store_true",
                        help="one shard, for comparing against the parallel result")
    parser.add_argument("--verbose", action="store_true",
                        help="per-shard timings, slowest first")
    args = parser.parse_args()

    root = args.root.resolve()
    start = root / "tests"
    if not start.is_dir():
        print(f"could not run: no tests directory at {start}", file=sys.stderr)
        return CANNOT_RUN
    try:
        names = classes(start)
    except RuntimeError as exc:
        print(f"could not run: {exc}", file=sys.stderr)
        return CANNOT_RUN
    if not names:
        print("could not run: discovery found no test classes", file=sys.stderr)
        return CANNOT_RUN

    jobs = 1 if args.serial else (args.jobs or os.cpu_count() or 4)
    buckets = shard(names, jobs)
    began = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(buckets)) as pool:
        outcomes = list(pool.map(lambda bucket: run(bucket, root), buckets))
    elapsed = time.perf_counter() - began

    total = sum(count for _, count, _, _, _ in outcomes)
    failed = [output for code, _, output, _, _ in outcomes if code != 0]
    for output in failed:
        print(output)

    if args.verbose:
        # The slowest shard is the run time, so the tail is the only number worth tuning.
        for _, count, _, seconds, bucket in sorted(outcomes, key=lambda o: -o[3]):
            print(f"  {seconds:6.1f}s  {count:4d} test(s)  {', '.join(bucket)}")
    slowest = max(seconds for _, _, _, seconds, _ in outcomes)
    print(f"ran {total} test(s) in {len(buckets)} shard(s) in {elapsed:.1f}s "
          f"(slowest shard {slowest:.1f}s)")
    if failed:
        print(f"{len(failed)} shard(s) failed.")
        return FAILED
    return PASSED


if __name__ == "__main__":
    raise SystemExit(main())
