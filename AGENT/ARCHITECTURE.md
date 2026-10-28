# Architecture: Zairenkai-Release

## Overview

`unified-release.yml` resolves the `dev` heads of the configured Zairenkai repositories to
immutable commits, verifies each checkout in a GitHub Actions matrix, and builds one integrated
Android APK and one installable root module. Stable builds run on the schedule/source updates;
maintainers can dispatch the same pipeline for a beta build. Successful products are published as
separate stable or prerelease GitHub Releases in this repository. Release manifests bind the
channel, every source commit and artifact SHA-256.

## Components

| Path | Responsibility |
|---|---|
| `build/repositories.json` | Authoritative source list, ref, and explicit exclusions. |
| `scripts/resolve_sources.py` | Resolve configured refs to commit SHAs and write the source manifest. |
| `scripts/verify_checkout.py` | Reject a matrix checkout that differs from its resolved SHA. |
| `scripts/has_source_changes.py` | Compare source SHAs against both latest complete product manifests. |
| `scripts/select_versions.py` | Allocate increasing app and module versions from existing releases. |
| `scripts/prepare_build.py` | Apply exact source SHAs and generated versions to ephemeral App/Modules checkouts. |
| `scripts/create_build_manifest.py` | Record source, builder, product and artifact provenance. |
| `scripts/stage_gguf.py` | Route the Engine matrix's pinned GGUF to a central immutable release after size/SHA/licence checks. |
| `.github/workflows/unified-release.yml` | Coordinate checks, integrated build, signing, validation and publication. |

## Data flow and trust boundaries

Source resolution uses the GitHub API. The configured source repositories are public. The matrix
checks out exact commits and verifies each SHA before building. The builder then pins App and
Modules locks to those same commits. Signing keys are read only in the protected `release` environment and removed
from runner temporary storage before artifact upload. Build/test jobs have read-only repository
permissions. Only the final publish job receives `contents: write` and publishes immutable App
and module releases plus a separately downloadable GGUF release. Beta builds mark the App and
module as prereleases. GGUF tags use the exact Engine matrix commit and remain independent of the
App/module release feed. Existing model tags are reused only after manifest and checksum checks.
The model is prequantized upstream: Release stages the pinned GGUF unchanged and validates its
manifest-declared size and SHA-256; it does not quantize weights.

The module release is published before the App release. Both include `update.json`, so the latest
stable App release also serves as the central stable module update feed expected by root managers.
The App's Beta channel can read both App and module prereleases. Public client access
requires this repository and its releases to be public; repository visibility is an administrator
setting and is not changed by this workflow.

## Generated artifacts

The workflow builds `zairenkai-<version>.apk` and `zairenkai-v<version>.zip`, with individual
checksums, `SHA256SUMS`, update metadata and a shared `build-manifest.json`. The manifest records
the complete configured source matrix, including the builder commit, and SHA-256/size for both
products and the GGUF. The generated App model manifest points to a model tag keyed by the same
exact Engine commit in that matrix. Build staging is ephemeral and only release assets are retained.
