#!/usr/bin/env python3
"""Run every example study for one image against the dev network and check the
result envelope (AGENTS.md §6's `make smoke`): fails if any study's envelope comes
back `status: error`, or if the run itself raises (timeout, bad params, ...).

Usage: uv run python dev-network/scripts/smoke.py <algorithm-name>
"""

import glob
import sys

import yaml

from v6run import run


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <algorithm-name>", file=sys.stderr)
        return 2
    algorithm = sys.argv[1]

    studies = [
        path
        for path in sorted(glob.glob("examples/studies/*.yaml"))
        if yaml.safe_load(open(path)).get("algorithm") == algorithm
    ]
    if not studies:
        print(f"No example study found for '{algorithm}' under examples/studies/", file=sys.stderr)
        return 1

    failures = []
    for path in studies:
        print(f"--- smoke: {path} ---")
        try:
            result = run(path)
        except Exception as exc:
            print(f"FAILED: {path} raised {exc!r}", file=sys.stderr)
            failures.append(path)
            continue
        if result.envelope.get("status") == "error":
            print(f"FAILED: {path} returned status=error: {result.envelope.get('errors')}", file=sys.stderr)
            failures.append(path)

    if failures:
        print(f"\n{len(failures)}/{len(studies)} smoke study(s) failed: {failures}", file=sys.stderr)
        return 1
    print(f"\nAll {len(studies)} smoke study(s) for '{algorithm}' passed (status ok/partial).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
