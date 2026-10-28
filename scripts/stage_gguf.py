#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Stage and verify the matrix-pinned GGUF from the model manifest in the locked Engine source."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

ENGINE_REPOSITORY = "ZairenkaiPrjctX/Zairenkai-Intelligence-Engine"
SHA1 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
MODEL_ID = re.compile(r"^[a-z0-9_]{1,64}$")
MODEL_FILE = re.compile(r"^[A-Za-z0-9._-]{1,128}\.gguf$")
HF_URL = re.compile(r"^https://huggingface\.co/[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
REPOSITORY = re.compile(r"^[A-Za-z0-9-]+/[A-Za-z0-9._-]+$")
TAG = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class StageError(ValueError):
    pass


def read_manifest(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageError(f"cannot read model manifest {path}: {exc}") from exc
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("format") != "gguf":
        raise StageError("only schema 1 GGUF model manifests are accepted")
    model_id = value.get("model_id")
    if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
        raise StageError("model_id is malformed")
    files = value.get("files")
    if not isinstance(files, list) or len(files) != 1 or not isinstance(files[0], dict):
        raise StageError("the model manifest must describe exactly one GGUF file")
    item = files[0]
    if not isinstance(item.get("name"), str) or not MODEL_FILE.fullmatch(item["name"]):
        raise StageError("model file name is unsafe")
    if not isinstance(item.get("sha256"), str) or not SHA256.fullmatch(item["sha256"]):
        raise StageError("model SHA-256 is malformed")
    if type(item.get("size_bytes")) is not int or item["size_bytes"] <= 0:
        raise StageError("model size_bytes must be a positive integer")
    source = value.get("source")
    if not isinstance(source, dict) or not isinstance(source.get("url"), str) or not HF_URL.fullmatch(source["url"]):
        raise StageError("model source must be a Hugging Face repository URL")
    if not isinstance(source.get("revision"), str) or not SHA1.fullmatch(source["revision"]):
        raise StageError("model source revision must be a full commit SHA")
    licenses = value.get("licenses")
    if not isinstance(licenses, dict) or not all(isinstance(licenses.get(k), str) and licenses[k].strip()
                                                  for k in ("weights", "tokenizer", "config")):
        raise StageError("weights, tokenizer, and config licence declarations are required")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(manifest_path: Path, app_manifest_path: Path, prepared_path: Path,
            engine_commit: str, release_repository: str) -> dict:
    if not SHA1.fullmatch(engine_commit):
        raise StageError("Engine matrix commit must be a full Git SHA")
    if not REPOSITORY.fullmatch(release_repository):
        raise StageError("central release repository must be owner/name")
    manifest = read_manifest(manifest_path)
    model_id = manifest["model_id"]
    release_tag = f"model-{model_id}-{engine_commit}"
    if not TAG.fullmatch(release_tag):
        raise StageError("generated model release tag is unsafe")
    manifest["release"] = {"repository": release_repository, "tag": release_tag}
    manifest["engine"] = {"repository": ENGINE_REPOSITORY, "commit": engine_commit}
    source = manifest["source"]
    filename = manifest["files"][0]["name"]
    urls = {
        "tag": release_tag,
        "model_url": f"{source['url']}/resolve/{source['revision']}/{filename}",
        "license_url": f"{source['url']}/resolve/{source['revision']}/LICENSE",
        "model_filename": filename,
        "model_id": model_id,
    }
    raw = json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"
    prepared_path.parent.mkdir(parents=True, exist_ok=True)
    prepared_path.write_text(raw, encoding="utf-8")
    app_manifest_path.parent.mkdir(parents=True, exist_ok=True)
    app_manifest_path.write_text(raw, encoding="utf-8")
    return urls


def stage(manifest_path: Path, model_path: Path, license_path: Path, output: Path) -> list[Path]:
    manifest = read_manifest(manifest_path)
    release, engine = manifest.get("release"), manifest.get("engine")
    if not isinstance(release, dict) or not isinstance(engine, dict):
        raise StageError("prepared manifest lacks its central release and Engine source pins")
    if not isinstance(release.get("repository"), str) or not REPOSITORY.fullmatch(release["repository"]):
        raise StageError("prepared manifest has an unsafe central release repository")
    if not isinstance(release.get("tag"), str) or not TAG.fullmatch(release["tag"]):
        raise StageError("prepared manifest has an unsafe model release tag")
    if engine.get("repository") != ENGINE_REPOSITORY or not isinstance(engine.get("commit"), str) or not SHA1.fullmatch(engine["commit"]):
        raise StageError("prepared manifest has an invalid Engine commit pin")
    expected_tag = f"model-{manifest['model_id']}-{engine['commit']}"
    if release["tag"] != expected_tag:
        raise StageError("model release tag does not match the Engine matrix commit")
    item = manifest["files"][0]
    if model_path.is_symlink() or not model_path.is_file():
        raise StageError("GGUF source is missing or a symlink")
    if model_path.stat().st_size != item["size_bytes"]:
        raise StageError(f"GGUF size {model_path.stat().st_size} does not match manifest {item['size_bytes']}")
    digest = sha256(model_path)
    if digest != item["sha256"]:
        raise StageError(f"GGUF SHA-256 {digest} does not match manifest {item['sha256']}")
    if license_path.is_symlink() or not license_path.is_file() or license_path.stat().st_size == 0:
        raise StageError("pinned source LICENSE is missing, empty, or a symlink")
    output.mkdir(parents=True, exist_ok=True)
    assets = [output / item["name"], output / f"{manifest['model_id']}.LICENSE.txt",
              output / f"{manifest['model_id']}.manifest.json"]
    shutil.copyfile(model_path, assets[0])
    shutil.copyfile(license_path, assets[1])
    assets[2].write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    sums = output / "SHA256SUMS"
    sums.write_text("".join(f"{sha256(path)}  {path.name}\n" for path in assets), encoding="ascii")
    notes = output / "notes.md"
    notes.write_text(
        f"{manifest['display_name']} for Zairenkai Local AI.\n\n"
        f"- GGUF: `{item['name']}`, {item['size_bytes']} bytes, SHA-256 `{item['sha256']}`\n"
        f"- Source weights: {manifest['source']['url']} at immutable revision `{manifest['source']['revision']}`\n"
        f"- Zairenkai-Intelligence-Engine matrix commit: `{engine['commit']}`\n"
        f"- Licences: weights {manifest['licenses']['weights']}; tokenizer {manifest['licenses']['tokenizer']}; config {manifest['licenses']['config']}\n\n"
        "The pinned GGUF is downloaded unchanged and retained only after size and SHA-256 verification.\n",
        encoding="utf-8",
    )
    return assets + [sums, notes]


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--app-manifest", type=Path, required=True)
    p.add_argument("--prepared-manifest", type=Path, required=True)
    p.add_argument("--engine-commit", required=True)
    p.add_argument("--release-repository", required=True)
    p.add_argument("--github-output", type=Path, required=True)
    s = sub.add_parser("stage")
    s.add_argument("--manifest", type=Path, required=True)
    s.add_argument("--model", type=Path, required=True)
    s.add_argument("--license", type=Path, required=True)
    s.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            result = prepare(args.manifest, args.app_manifest, args.prepared_manifest,
                             args.engine_commit, args.release_repository)
            with args.github_output.open("a", encoding="utf-8") as out:
                for key, value in result.items():
                    out.write(f"{key}={value}\n")
            print(f"Prepared {result['tag']} from Engine commit {args.engine_commit}")
        else:
            for path in stage(args.manifest, args.model, args.license, args.output):
                print(path)
    except (OSError, StageError) as exc:
        print(f"stage_gguf: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
