#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Create the release provenance manifest and checksums after the complete build gate passes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def create(matrix_path: Path, output: Path, app_version: str, module_version: str,
           app_commit: str, module_commit: str, builder_commit: str, apk: Path, module_zip: Path,
           component_manifest: Path, channel: str = "stable", model: Path | None = None,
           model_manifest: Path | None = None) -> dict:
    if channel not in {"stable", "beta"}:
        raise ValueError("release channel must be stable or beta")
    if not all(SHA1.fullmatch(value) for value in (app_commit, module_commit, builder_commit)):
        raise ValueError("App, Modules, and builder source commits must be full SHA-1 values")
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    rows = matrix.get("repositories")
    if not isinstance(rows, list) or not rows:
        raise ValueError("source matrix has no resolved repositories")
    sources = {}
    for row in rows:
        name, sha = row.get("name"), row.get("sha")
        if not isinstance(name, str) or not SHA1.fullmatch(str(sha)) or name in sources:
            raise ValueError(f"invalid/duplicate source matrix row: {row!r}")
        sources[name] = {"repository": row["repository"], "ref": row["ref"], "commit": sha, "role": row["role"]}
    if sources.get("Zairenkai-App", {}).get("commit") != app_commit:
        raise ValueError("App checkout does not match its source matrix entry")
    if sources.get("Zairenkai-Modules", {}).get("commit") != module_commit:
        raise ValueError("Modules checkout does not match its source matrix entry")
    if (model is None) != (model_manifest is None):
        raise ValueError("model and model_manifest must be supplied together")
    model_record = None
    if model is not None and model_manifest is not None:
        engine_commit = sources.get("Zairenkai-Intelligence-Engine", {}).get("commit")
        model_data = json.loads(model_manifest.read_text(encoding="utf-8"))
        if not isinstance(model_data, dict):
            raise ValueError("GGUF manifest must be a JSON object")
        engine = model_data.get("engine", {})
        release = model_data.get("release", {})
        source = model_data.get("source", {})
        files = model_data.get("files", [])
        if not all(isinstance(value, dict) for value in (engine, release, source)):
            raise ValueError("GGUF manifest engine, release, and source fields must be objects")
        if not isinstance(files, list) or engine.get("commit") != engine_commit or len(files) != 1:
            raise ValueError("GGUF manifest does not bind to the Engine source matrix")
        if release.get("repository") != "ZairenkaiPrjctX/Zairenkai-Release":
            raise ValueError("GGUF release must point to the central Release repository")
        if release.get("tag") != f"model-{model_data.get('model_id')}-{engine_commit}":
            raise ValueError("GGUF release tag does not bind to the Engine matrix commit")
        if not SHA1.fullmatch(source.get("revision", "")):
            raise ValueError("GGUF source revision must be an immutable full SHA")
        item = files[0]
        if not isinstance(item, dict) or model.stat().st_size != item.get("size_bytes") or digest(model) != item.get("sha256"):
            raise ValueError("GGUF bytes do not match the Engine manifest")
        model_record = {
            "id": model_data["model_id"], "engine_commit": engine_commit,
            "source_revision": model_data["source"]["revision"], "release_tag": release["tag"],
            "file": model.name, "size_bytes": model.stat().st_size, "sha256": digest(model),
        }
    components = json.loads(component_manifest.read_text(encoding="utf-8"))
    if not isinstance(components, dict):
        raise ValueError("component provenance file is not a JSON object")
    for path in (apk, module_zip):
        if not path.is_file() or path.stat().st_size <= 0:
            raise ValueError(f"release artifact is missing or empty: {path}")
    output.mkdir(parents=True, exist_ok=True)
    artifacts = []
    for path in (apk, module_zip):
        target = output / path.name
        if path.resolve() != target.resolve():
            target.write_bytes(path.read_bytes())
        artifacts.append({"name": target.name, "size_bytes": target.stat().st_size, "sha256": digest(target)})
        (output / f"{target.name}.sha256").write_text(f"{digest(target)}  {target.name}\n", encoding="ascii")
    if model is not None:
        model_record["file"] = model.name
        artifacts.append({"name": model.name, "size_bytes": model.stat().st_size, "sha256": digest(model), "kind": "gguf"})
    manifest = {
        "format": 1,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "repository": "ZairenkaiPrjctX/Zairenkai-Release",
        "source_ref": matrix.get("ref"),
        "channel": channel,
        "builder": {"repository": "ZairenkaiPrjctX/Zairenkai-Release", "commit": builder_commit},
        "app": {"version": app_version, "repository": "ZairenkaiPrjctX/Zairenkai-App", "commit": app_commit},
        "module": {"version": module_version, "repository": "ZairenkaiPrjctX/Zairenkai-Modules", "commit": module_commit},
        "source_repositories": sources,
        "excluded_repositories": matrix.get("excluded", []),
        "integration_components": components,
        "artifacts": artifacts,
        "verification": {"matrix": "passed", "integration": "passed", "release_gate": "passed", "signature": "passed"},
    }
    if model_record is not None:
        manifest["model"] = model_record
    manifest_path = output / "build-manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (output / "build-manifest.json.sha256").write_text(f"{digest(manifest_path)}  build-manifest.json\n", encoding="ascii")
    sum_paths = sorted(p for p in output.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{digest(p)}  {p.name}\n" for p in sum_paths), encoding="ascii")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--app-version", required=True)
    parser.add_argument("--module-version", required=True)
    parser.add_argument("--app-commit", required=True)
    parser.add_argument("--module-commit", required=True)
    parser.add_argument("--builder-commit", required=True)
    parser.add_argument("--apk", type=Path, required=True)
    parser.add_argument("--module-zip", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--channel", choices=("stable", "beta"), default="stable")
    parser.add_argument("--model", type=Path)
    parser.add_argument("--model-manifest", type=Path)
    args = parser.parse_args()
    try:
        manifest = create(args.matrix, args.output, args.app_version, args.module_version, args.app_commit,
                          args.module_commit, args.builder_commit, args.apk, args.module_zip, args.components,
                          args.channel, args.model, args.model_manifest)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"create_build_manifest: {exc}", file=sys.stderr)
        return 1
    print(f"manifest verified: {len(manifest['source_repositories'])} source repos, {len(manifest['artifacts'])} artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
