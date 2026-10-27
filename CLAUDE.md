# CLAUDE.md: Zairenkai-Release

Instructions for Claude Code in `ZairenkaiPrjctX/Zairenkai-Release`. Keep this file under 200 lines;
put detail in `AGENT/`.

@AGENTS.md
@AGENT/PROJECT_CONTEXT.md

## Current state (read first)

This repository contains the source matrix builder and central App/Modules release workflow.
See `AGENT/ARCHITECTURE.md` and `AGENT/PROJECT_CONTEXT.md` for verified behavior and rollout
conditions. The workflow has not yet published a release.

## Commands

| Purpose | Command | Status |
|---|---|---|
| Build and publish | GitHub Actions `Unified Zairenkai Matrix Release` | Configured; needs documented secrets and rollout conditions |
| Builder tests | `python3 -m unittest discover -s tests -v` | Configured |
| Lint / format | — | Not Configured |
| Validate agent foundation | `python3 <path-to-.github>/agent-foundation/scripts/validate_agent_setup.py .` | Configured |

Only list commands that exist in this repository. Never invent one.

## Working rules

- Inspect the relevant code before editing it. Preserve unrelated and uncommitted changes.
- Generated files are edited at their source, then regenerated. Managed foundation files
  (listed in `AGENT/.foundation-manifest.json`) are edited in `ZairenkaiPrjctX/.github`, not here.
- Destructive or outward-facing actions (deleting data, force-push, history rewrites,
  publishing releases, deploying, flashing devices) need explicit human approval each time.
- Do not claim a build, test, or signature succeeded without showing the output.

## Git

- Work on a topic branch; open **draft** pull requests; never merge or approve.
- Commits must be cryptographically signed. If signing fails, stop and report the error.
  Trailer format and verification: `AGENT/policies/git-and-commit-signing.md`.

## Where things are

- `AGENT/README.md`: index of the agent library (prompts, policies, playbooks, templates).
- `.claude/skills/`: run `/repo-audit`, `/implement-feature`, `/bug-fix`, `/test-and-verify`,
  `/security-review`, `/release-readiness`.
- `.claude/rules/`: path-scoped rules, loaded automatically.
