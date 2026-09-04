---
name: release
description: >-
  Drive the envmgr release workflow: open a dev→master PR, wait for CI to pass,
  rebase-merge to trigger auto-tag and release, verify the published tag, and
  resync dev. Use when the user says "发版", "release" / "ship" an envmgr version,
  or asks to run the documented release flow. Scoped to this repo — the steps come
  from AGENTS.md and docs/release.md.
---

# Release

This skill is the trigger + pointer for the envmgr release workflow. The full
process is authoritative in the repo docs, not here.

## When to use

- You say 发版 / release / ship this / publish a new envmgr version.
- Not for routine commits, `envmgr self update` usage, or non-release PRs.

## Source of truth

Read both before acting and treat them as canonical:

- `AGENTS.md` → "Release Checklist".
- `docs/release.md` → "Developer Release Flow".

They must stay in sync. The version tag is derived from the
`origin/master..origin/dev` batch by git-cliff (`feat`→minor, `fix`→patch,
`feat!`→major; `docs`/`chore`-only batches yield no tag) because
`[tool.hatch.version] source = "vcs"`; confirm the batch and predicted tag before
any external mutation.

## Safety gates

The only confirmations unique to a release, per `AGENTS.md`:

- Merge only after all required CI is green and the user gives the go-ahead
  (merging triggers a public release).
- Never push to `master` directly; flag any deviation from the documented flow.
