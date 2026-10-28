#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Align the App's module catalog contract fixture with the verified build matrix."""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path

SHA = re.compile(r"^[0-9a-f]{40}$")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read valid JSON from {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return value


def refresh(app: Path) -> str:
    lock_path = app / "integration/repository-lock.json"
    catalog_path = app / "integration/out/assets/system-modules.json"
    fixture_path = app / "integration-core/src/test/resources/contracts/system-modules/catalog.json"

    lock = read_json(lock_path)
    components = lock.get("components")
    if not isinstance(components, list):
        raise ValueError("repository lock has no components array")
    locked = [row for row in components if isinstance(row, dict) and row.get("id") == "zairenkai-module"]
    if len(locked) != 1:
        raise ValueError("repository lock must contain exactly one zairenkai-module component")
    expected = locked[0].get("commit")
    if not isinstance(expected, str) or not SHA.fullmatch(expected):
        raise ValueError("zairenkai-module lock commit is not a full Git SHA")

    catalog = read_json(catalog_path)
    modules = catalog.get("modules")
    if not isinstance(modules, list):
        raise ValueError("built module catalog has no modules array")
    entries = [row for row in modules if isinstance(row, dict) and row.get("id") == "zairenkai"]
    if len(entries) != 1:
        raise ValueError("built module catalog must contain exactly one zairenkai module")
    source = entries[0].get("source")
    actual = source.get("commit") if isinstance(source, dict) else None
    if actual != expected:
        raise ValueError(f"built zairenkai module commit {actual!r} does not match locked commit {expected}")

    # Replace atomically so a failed/interrupted workflow cannot leave a partial fixture.
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=fixture_path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(catalog_path.read_bytes())
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, fixture_path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return expected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    args = parser.parse_args()
    try:
        commit = refresh(args.app)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(f"Aligned module catalog test fixture with verified zairenkai-module commit {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
