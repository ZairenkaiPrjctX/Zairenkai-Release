<!-- Managed by ZairenkaiPrjctX/.github agent-foundation v1.1.0. Edit the central template, then re-sync. -->
# Playbook: Release process

**Status: Not Configured.** This repository's GitHub description ("Release Build Zairenkai") indicates
it is meant to hold release builds, but on 2026-10-18 it contained no release automation,
artifacts, or signing configuration. This playbook is the gate for *defining* the process; it
does not describe one that exists.

## Decisions to make and record in `AGENT/PROJECT_CONTEXT.md` before the first release
1. **Inputs:** which repositories and revisions feed a release build.
2. **Build:** the CI workflow that produces artifacts (never a developer machine).
3. **Versioning:** scheme and where the version string lives.
4. **Signing:** which key signs artifacts, stored as a named CI secret; who controls it.
5. **Publication:** channel (GitHub Releases, other), who approves.
6. **Rollback:** how a user uninstalls or downgrades a bad release.

## Once defined, every release
1. Run `/release-readiness` on the candidate; all checks pass or are explained.
2. A human approves, tags, and publishes. Agents never tag or publish.
3. Record the release (version, revision, checksums) in the changelog.
