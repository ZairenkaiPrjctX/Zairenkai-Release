#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Compare the resolved source matrix with the latest central release manifest."""
import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = "ZairenkaiPrjctX/Zairenkai-Release"


def request(url: str, accept: str = "application/vnd.github+json") -> bytes:
    headers = {"Accept": accept, "User-Agent": "Zairenkai-Release-source-change-check/1.0",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read(2 * 1024 * 1024 + 1)


def has_changes(matrix_path: Path) -> bool:
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    current = {r["name"]: r["sha"] for r in matrix["repositories"]}
    try:
        releases = json.loads(request(f"https://api.github.com/repos/{REPO}/releases?per_page=100"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return True
        raise RuntimeError(f"cannot read central releases: HTTP {exc.code}") from exc
    if not isinstance(releases, list):
        raise RuntimeError("central GitHub releases response is not a list")

    def first_release(predicate):
        return next((r for r in releases if isinstance(r, dict) and not r.get("draft") and predicate(r)), None)

    def asset_url(release, name):
        if release is None:
            return None
        asset = next((a for a in release.get("assets", []) if a.get("name") == name), None)
        return asset.get("browser_download_url") if asset else None

    app_release = first_release(lambda r: re.fullmatch(r"v\d+\.\d+\.\d+", str(r.get("tag_name", "")))
                                and any(a.get("name", "").endswith(".apk") for a in r.get("assets", [])))
    module_release = first_release(lambda r: str(r.get("tag_name", "")).startswith("module-v")
                                   and any(a.get("name", "").endswith(".zip") for a in r.get("assets", [])))
    if app_release is None or module_release is None:
        return True
    app_url = asset_url(app_release, "build-manifest.json")
    module_url = asset_url(module_release, "build-manifest.json")
    if not app_url or not module_url:
        return True
    app_manifest = json.loads(request(app_url, "application/octet-stream"))
    module_manifest = json.loads(request(module_url, "application/octet-stream"))
    if len(json.dumps(app_manifest)) > 2 * 1024 * 1024 or len(json.dumps(module_manifest)) > 2 * 1024 * 1024:
        raise RuntimeError("published build manifest exceeds 2 MiB")
    previous_app = {name: row.get("commit") for name, row in app_manifest.get("source_repositories", {}).items()}
    previous_module = {name: row.get("commit") for name, row in module_manifest.get("source_repositories", {}).items()}
    if not previous_app or not previous_module:
        raise RuntimeError("published build manifest contains no source repository commits")
    return not (current == previous_app == previous_module and
                app_manifest.get("app", {}).get("version") == app_release["tag_name"].removeprefix("v") and
                module_manifest.get("module", {}).get("version") == module_release["tag_name"].removeprefix("module-v"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    args = parser.parse_args()
    try:
        changed = has_changes(args.matrix)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, urllib.error.URLError, TimeoutError, RuntimeError) as exc:
        print(f"has_source_changes: {exc}", file=sys.stderr)
        return 1
    print("true" if changed else "false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
