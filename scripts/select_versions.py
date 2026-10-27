#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Select monotonically increasing stable versions for the next integrated build."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^(0|[1-9]\d{0,3})\.(0|[1-9]\d?)\.(0|[1-9]\d?)(?:-beta\.([1-9]\d?))?$")
OWNER_REPO = "ZairenkaiPrjctX/Zairenkai-Release"


def parse(value: str) -> tuple[int, int, int, int | None] | None:
    match = VERSION.fullmatch(value)
    if not match:
        return None
    a, b, c, beta = match.groups()
    return int(a), int(b), int(c), int(beta) if beta else None


def code(v: tuple[int, int, int, int | None]) -> int:
    a, b, c, beta = v
    return a * 1_000_000 + b * 10_000 + c * 100 + (beta or 99)


def stable(v: tuple[int, int, int, int | None]) -> tuple[int, int, int, int | None]:
    return v[0], v[1], v[2], None


def bump(v: tuple[int, int, int, int | None]) -> tuple[int, int, int, int | None]:
    major, minor, patch, _ = stable(v)
    patch += 1
    if patch == 100:
        minor += 1
        patch = 0
    if minor == 100:
        major += 1
        minor = 0
    if major > 2000:
        raise ValueError("version exceeds the App's supported Android versionCode range")
    return major, minor, patch, None


def text(v: tuple[int, int, int, int | None]) -> str:
    return f"{v[0]}.{v[1]}.{v[2]}" + (f"-beta.{v[3]}" if v[3] else "")


def choose(base: str, latest: list[str], prefix: str = "") -> str:
    base_tuple = parse(base)
    if base_tuple is None:
        raise ValueError(f"invalid source version {base!r}")
    candidates = [parse(tag.removeprefix(prefix).removeprefix("v")) for tag in latest if tag.startswith(prefix)]
    published = [v for v in candidates if v is not None and v[3] is None]
    newest = max(published, key=code) if published else None
    base_stable = stable(base_tuple)
    if newest is None or code(base_stable) > code(newest):
        return text(base_stable)
    return text(bump(newest))


def releases() -> list[str]:
    url = f"https://api.github.com/repos/{OWNER_REPO}/releases?per_page=100"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Zairenkai-Release-version-selector/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"cannot read central releases: {exc}") from exc
    if not isinstance(payload, list):
        raise RuntimeError("central GitHub releases response is not a list")
    return [str(row.get("tag_name", "")) for row in payload if isinstance(row, dict) and not row.get("draft")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-gradle", type=Path, required=True)
    parser.add_argument("--module-lock", type=Path, required=True)
    parser.add_argument("--release-list", type=Path, help="JSON array of tags, useful for offline testing")
    args = parser.parse_args()
    try:
        gradle = args.app_gradle.read_text(encoding="utf-8")
        match = re.search(r'^val appVersion = "([^"]+)"', gradle, re.M)
        if not match:
            raise ValueError("app/build.gradle.kts has no source appVersion")
        module = json.loads(args.module_lock.read_text(encoding="utf-8"))["module"]["version"]
        tags = json.loads(args.release_list.read_text(encoding="utf-8")) if args.release_list else releases()
        app_version = choose(match.group(1), tags)
        module_version = choose(module, tags, prefix="module-v")
    except (OSError, json.JSONDecodeError, KeyError, ValueError, RuntimeError) as exc:
        print(f"select_versions: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"app_version": app_version, "module_version": module_version}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
