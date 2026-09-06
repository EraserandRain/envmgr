---
name: release
description: >-
  Drive the envmgr release workflow: open a dev→master PR, wait for CI to pass,
  rebase-merge to trigger auto-tag and release, verify the published tag, and
  resync dev. Use when the user says "发版", "release" / "ship" an envmgr version,
  or asks to run the documented release flow. Scoped to this repo — the steps come
  from docs/release.md.
---

# Release

This skill is the trigger + pointer for the envmgr release workflow. The full
process is authoritative in the repo docs, not here.

## When to use

- You say 发版 / release / ship this / publish a new envmgr version.
- Not for routine commits, `envmgr self update` usage, or non-release PRs.

## Source of truth

The step-by-step flow is canonical in `docs/release.md` → "Developer Release
Flow". `AGENTS.md` carries only the release invariants (protected `master`, no
manual tags) and a pointer to this skill. Read `docs/release.md` before acting and
treat it as canonical; do not restate the flow here.

The version tag is derived from the `origin/master..origin/dev` batch by git-cliff
(`feat`→minor, `fix`→patch, `feat!`→major; `docs`/`chore`-only batches yield no
tag) because `[tool.hatch.version] source = "vcs"`. The computed batch and predicted
tag are informational (surfaced as part of the flow); they are not a confirmation
gate.

## Safety gates

Per `AGENTS.md`, the only hard boundaries in the release flow are:

- The user handles `git push`; the agent never pushes. Before creating the PR,
  verify `origin/dev` is up to date and, if not, ask the user to push and wait.
- Merge `gh pr merge --rebase` directly once all required CI is green. The user's
  release request plus green CI is the authorization to merge; merging publishes a
  version publicly, so do not skip the CI wait.
- Never push to `master` directly; flag any deviation from the documented flow.
