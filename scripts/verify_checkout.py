#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fail unless a checked-out source tree is exactly the matrix's immutable commit."""
import argparse
import re
import subprocess
import sys
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--path", type=Path, required=True)
    args = parser.parse_args()
    if not SHA.fullmatch(args.expected):
        parser.error("expected must be a full SHA-1")
    actual = subprocess.run(["git", "-C", str(args.path), "rev-parse", "HEAD"], text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if actual.returncode:
        print(f"{args.repository}: cannot read checkout: {actual.stderr.strip()}", file=sys.stderr)
        return 1
    if actual.stdout.strip() != args.expected:
        print(f"{args.repository}: checkout {actual.stdout.strip()} does not match {args.expected}", file=sys.stderr)
        return 1
    print(f"verified {args.repository} at {args.expected}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
