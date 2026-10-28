# Project context: Zairenkai-Release

## Identity

| Field | Value | Status |
|---|---|---|
| Repository | `ZairenkaiPrjctX/Zairenkai-Release` | Verified. Evidence: configured Git origin. |
| Visibility | public | Verified. Evidence: anonymous GitHub API repository metadata, 2026-10-27. |
| Working/default branch | `dev` | Verified. Evidence: anonymous GitHub API `default_branch` and `origin/HEAD -> origin/dev`, 2026-10-27. |
| Purpose | Matrix builder and central App/Modules release publisher | Verified. Evidence: `.github/workflows/unified-release.yml`. |

## Architecture and commands

See `AGENT/ARCHITECTURE.md`. The workflow uses Python 3 standard library scripts and GitHub
Actions; App and Modules supply their own Gradle, Python, Android NDK, Rust, and signing steps.

| Purpose | Command | Status |
|---|---|---|
| Resolve matrix | `python3 scripts/resolve_sources.py --output <path>` | Configured; live run requires GitHub source access. |
| Test builder scripts | `python3 -m unittest discover -s tests -v` | Configured. |
| Validate source checkout | `python3 scripts/verify_checkout.py --repository <owner/repo> --expected <sha> --path <checkout>` | Configured. |
| Build and publish | GitHub Actions `Unified Zairenkai Matrix Release` | Configured; requires release environment secrets and workflow rollout. |
| Validate agent foundation | `python3 <path-to-.github>/agent-foundation/scripts/validate_agent_setup.py .` | Configured. |

## Workflow facts and rollout conditions

- `build/repositories.json` lists 15 public repositories at `dev` and explicitly excludes
  `anime-extensions`. Anonymous GitHub API metadata checks confirmed all are public and
  `git ls-remote` confirmed every `dev` ref on 2026-10-27. This verifies ref visibility/existence,
  not GitHub Actions buildability.
- The Release repository is public, so anonymous App and root-module update requests can access
  releases. Anonymous GitHub API returned zero published releases on 2026-10-27, so client
  download behavior against real central assets is not yet verified.
- Configure secrets in the Release repository's `release` environment:
  `ZAIRENKAI_MODULE_SIGNING_KEY`, `ZAIRENKAI_RELEASE_KEYSTORE_BASE64`,
  `ZAIRENKAI_RELEASE_KEYSTORE_PASSWORD`, `ZAIRENKAI_RELEASE_KEY_ALIAS`, and
  `ZAIRENKAI_RELEASE_KEY_PASSWORD`. Names are documented; secret values are not inspected/copied.
- Scheduled workflows run only from GitHub's configured default branch. Verify that `dev` is
  still the default branch when rolling out this workflow.
- Workflow release publishing has not been run. App/Modules client updates, signed outputs,
  hardware behavior, and public feed access remain unverified until a successful release and
  device validation.

## Related repositories

App and root-module updater clients consume this repository's release feed. The build matrix lists
their source repositories and their direct components in `build/repositories.json`.

- Verified release failures (runs 40561867253 and 40610242897): first, the App catalog fixture had an older module commit than the immutable source matrix; after aligning it, `CoreContractTest` exposed that its `modules-installed.json` fixture still reported version 0.3.1 while the selected build version was 0.3.2. The workflow helper now aligns both temporary contract fixtures from the verified built catalog and fails closed on a lock mismatch or malformed version. Regression tests cover both fixture versions and mismatch behavior. The latest workflow run failed before this follow-up fix.
