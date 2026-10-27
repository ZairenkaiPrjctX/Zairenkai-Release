#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Prepare temporary App/Modules source locks from the verified source matrix."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

APP_COMPONENTS = {
    "zart": "Zairenkai-ART",
    "zthermal": "Zairenkai-ThermalTools",
    "afid-device-candidates": "Zairenkai-Database-Source",
    "zie-run": "Zairenkai-Intelligence-Engine",
}
MODULE_COMPONENTS = {
    "zairenkai-core": "Zairenkai-Core",
    "zairenkai-fas": "Zairenkai-FAS",
    "zairenkai-tuning": "Zairenkai-Tuning",
}
SHA = re.compile(r"^[0-9a-f]{40}$")
VERSION = re.compile(r"^(0|[1-9]\d{0,3})\.(0|[1-9]\d?)\.(0|[1-9]\d?)$")
OWNER = "ZairenkaiPrjctX"


def read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def source_map(matrix: dict) -> dict[str, str]:
    rows = matrix.get("repositories")
    if not isinstance(rows, list):
        raise ValueError("source matrix has no repositories array")
    result = {}
    for row in rows:
        name, sha = row.get("name"), row.get("sha")
        if not isinstance(name, str) or not SHA.fullmatch(str(sha)):
            raise ValueError(f"malformed matrix row: {row!r}")
        if name in result:
            raise ValueError(f"duplicate source repository {name}")
        result[name] = sha
    for required in {*APP_COMPONENTS.values(), *MODULE_COMPONENTS.values(), "Zairenkai-App", "Zairenkai-Modules"}:
        if required not in result:
            raise ValueError(f"source matrix is missing required repository {required}")
    return result


def prepare(app: Path, modules: Path, matrix_path: Path, app_version: str, module_version: str,
            app_notes_path: Path, module_notes_path: Path) -> dict:
    if not VERSION.fullmatch(app_version) or not VERSION.fullmatch(module_version):
        raise ValueError("generated versions must be MAJOR.MINOR.PATCH")
    matrix = read_json(matrix_path)
    heads = source_map(matrix)
    module_lock_path = modules / "components.lock.json"
    module_lock = read_json(module_lock_path)
    if module_lock.get("format") != 1:
        raise ValueError("unsupported Modules component lock format")
    module_rows = {row.get("name"): row for row in module_lock.get("components", [])}
    if set(module_rows) != set(MODULE_COMPONENTS):
        raise ValueError(f"unexpected Modules component set: {sorted(module_rows)}")
    for component, repo in MODULE_COMPONENTS.items():
        row = module_rows[component]
        if row.get("repository") != f"{OWNER}/{repo}":
            raise ValueError(f"{component}: source repository mismatch")
        row["commit"] = heads[repo]

    app_lock_path = app / "integration/repository-lock.json"
    app_lock = read_json(app_lock_path)
    app_rows = {row.get("id"): row for row in app_lock.get("components", [])}
    app_repos = {**APP_COMPONENTS, "zairenkai-module": "Zairenkai-Modules"}
    for component, repo in app_repos.items():
        if component not in app_rows:
            raise ValueError(f"App repository lock is missing {component}")
        row = app_rows[component]
        if row.get("repository") != f"{OWNER}/{repo}":
            raise ValueError(f"{component}: source repository mismatch")
        row["commit"] = heads[repo]
        row["branch"] = "dev"
        row["merged"] = True
        row.pop("release_artifact", None)
    for contract_id, module_component in (("zcored-ctl-contract", "zairenkai-core"),
                                          ("zfasd-ctl-contract", "zairenkai-fas")):
        if contract_id not in app_rows:
            raise ValueError(f"App repository lock is missing {contract_id}")
        app_rows[contract_id]["commit"] = module_rows[module_component]["commit"]
        app_rows[contract_id]["branch"] = "dev"
        app_rows[contract_id]["merged"] = True
    stamp = datetime.now(timezone.utc).date().isoformat()
    app_lock["locked_at"] = stamp
    app_lock["note"] = "Generated for this immutable full-source matrix build; all direct components and the module's Core/FAS contract pins use the source SHAs recorded in build-manifest.json."
    write_json(module_lock_path, module_lock)
    write_json(app_lock_path, app_lock)

    inventory_path = app / "integration/organization-repositories.json"
    inventory = read_json(inventory_path)
    for row in inventory.get("repositories", []):
        name = row.get("name")
        if name in heads:
            row["audited_branch"] = "dev"
            row["audited_commit"] = heads[name]
            evidence = str(row.get("evidence", "")).rstrip()
            row["evidence"] = (evidence + " " if evidence else "") + f"Generated source-matrix build {stamp} at {heads[name]} (see central build manifest)."
    write_json(inventory_path, inventory)

    notes = (
        f"Automated integrated Zairenkai build {app_version}.\n\n"
        f"The installable App and root module were built from the immutable source matrix recorded in `build-manifest.json`.\n"
        f"App version: {app_version}.\nModule version: {module_version}.\n\n"
        "All source revisions and SHA-256 values are published with the release. The build is offered only after the complete matrix, integration tests, release gate, and signing checks pass."
    )
    app_notes_path.parent.mkdir(parents=True, exist_ok=True)
    module_notes_path.parent.mkdir(parents=True, exist_ok=True)
    app_notes_path.write_text(notes + "\n", encoding="utf-8")
    module_notes_path.write_text(notes + "\n", encoding="utf-8")
    changelog_path = app / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    marker = f"## [{app_version}] - automated build"
    if marker not in changelog:
        lines = changelog.splitlines(keepends=True)
        insert = next((i + 1 for i, line in enumerate(lines) if line.startswith("# ")), 0)
        lines[insert:insert] = ["\n", marker + "\n", "\n", "- Integrated release generated from the immutable source matrix.\n",
                                "- See the central build manifest for source SHAs and artifact digests.\n", "\n"]
        changelog_path.write_text("".join(lines), encoding="utf-8")
    return {"sources": heads, "app_version": app_version, "module_version": module_version}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app", type=Path, required=True)
    parser.add_argument("--modules", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--module-version", required=True)
    parser.add_argument("--app-notes", type=Path, required=True)
    parser.add_argument("--module-notes", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.app, args.modules, args.matrix, args.app_version, args.module_version,
                         args.app_notes, args.module_notes)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"prepare_build: {exc}", file=sys.stderr)
        return 1
    print(json.dumps({"app_version": result["app_version"], "module_version": result["module_version"],
                      "source_count": len(result["sources"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
