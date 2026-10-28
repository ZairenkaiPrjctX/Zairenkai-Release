#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Resolve every included Zairenkai repository to an immutable commit on the configured ref."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"^[0-9a-f]{40}$")


def resolve(owner: str, name: str, ref: str) -> dict[str, str]:
    url = f"https://api.github.com/repos/{owner}/{name}/commits/{ref}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Zairenkai-Release-source-matrix/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    error = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read())
            sha = payload.get("sha", "")
            html = payload.get("html_url", "")
            if not SHA.fullmatch(sha) or f"github.com/{owner}/{name}/commit/{sha}" not in html:
                raise ValueError(f"GitHub returned a malformed or foreign commit for {owner}/{name}/{ref}")
            return {"repository": f"{owner}/{name}", "name": name, "ref": ref, "sha": sha, "url": html}
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace").lower()
            rate_limited = exc.code == 429 or (
                exc.code == 403 and ("rate limit" in body or exc.headers.get("X-RateLimit-Remaining") == "0")
            )
            if not rate_limited:
                raise RuntimeError(f"GitHub API rejected {owner}/{name}/{ref} with HTTP {exc.code}") from exc
            error = RuntimeError(f"GitHub API rate limit exceeded for {owner}/{name}/{ref}")
            if attempt < 2:
                try:
                    retry_after = int(exc.headers.get("Retry-After", "0"))
                    reset_at = int(exc.headers.get("X-RateLimit-Reset", "0"))
                except ValueError:
                    retry_after, reset_at = 0, 0
                delay = max(retry_after, reset_at - int(time.time()), 2 << attempt)
                if delay <= 60:
                    time.sleep(delay)
                    continue
            break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, ValueError) as exc:
            error = exc
            if attempt < 2:
                time.sleep(1 << attempt)
    raise RuntimeError(f"cannot resolve {owner}/{name}/{ref}: {error}") from error


def load_config(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("format") != 1 or not re.fullmatch(r"[A-Za-z0-9_.-]+", data.get("owner", "")):
        raise ValueError("source matrix config has an unsupported format or invalid owner")
    if not re.fullmatch(r"[A-Za-z0-9._/-]+", data.get("ref", "")):
        raise ValueError("source matrix ref is invalid")
    rows = data.get("repositories")
    if not isinstance(rows, list) or not rows:
        raise ValueError("source matrix must contain repositories")
    names = [r.get("name") for r in rows]
    if len(names) != len(set(names)):
        raise ValueError("source matrix contains duplicate repository names")
    excluded = {x.get("repository", "").split("/", 1)[-1] for x in data.get("excluded", [])}
    if excluded.intersection(names):
        raise ValueError("an explicitly excluded repository appears in the build matrix")
    for row in rows:
        if not isinstance(row, dict) or not re.fullmatch(r"[A-Za-z0-9_.-]+", row.get("name", "")):
            raise ValueError(f"invalid source matrix row: {row!r}")
        if not isinstance(row.get("role"), str) or not row["role"].strip():
            raise ValueError(f"repository {row['name']} has no purpose")
    return data


def build_matrix(config: dict) -> dict:
    resolved = [resolve(config["owner"], row["name"], config["ref"]) for row in config["repositories"]]
    return {
        "format": 1,
        "owner": config["owner"],
        "ref": config["ref"],
        "resolved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "excluded": config.get("excluded", []),
        "repositories": [
            {**item, "role": next(row["role"] for row in config["repositories"] if row["name"] == item["name"])}
            for item in resolved
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / "build/repositories.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build_matrix(load_config(args.config))
    except (OSError, json.JSONDecodeError, ValueError, RuntimeError) as exc:
        print(f"resolve_sources: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"resolved {len(result['repositories'])} repositories at {result['ref']}")
    for row in result["repositories"]:
        print(f"{row['repository']} {row['sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
