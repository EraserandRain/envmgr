# Repository Guidelines

This guide is the maintainer and coding-agent source of truth for envmgr. Keep the
README short for users and put detailed runtime/development/release material under
`docs/`. This file carries the repo's invariants, the CLI/docs contracts that must
stay in sync, and pointers. The command inventory that used to live here is now in
`docs/` and the `dev-helpers/` scripts, and is enforced by contract tests and CI.

## Architecture Principles

These guardrails keep envmgr's runtime, CLI, and data layers from drifting apart.
When you add a new CLI option, command, `--json` field, role metadata field, or
persisted state, classify it against the rules below, then implement it with the
matching docs and contract test.

### State/data is separated from execution

- `InstallPlan` and `DoctorReport` are pure data. Building a plan or a report
  never mutates `~/.envmgr/` and never launches Ansible. Running it is a
  separate, thin layer that consumes the plan and returns an exit code.
- `commands/` is a presentation boundary: it marshals CLI args into a service
  call, renders the result through Rich, and emits `--json` payloads verbatim.
  Business logic lives in `services/`.

### Machine output is a versioned contract

- Every `--json` payload carries `schema_version`. Adding or renaming a field is
  a contract change and must update the JSON payload, `docs/runtime.md`, and the
  matching `tests/checks/*` contract test together.
- Rich rendering is only a view over the same data; it never redefines the
  machine contract.

### Role metadata is the single source of truth

- `roles/<role>/meta/envmgr.yml` drives tag discovery, dependency closure,
  generated playbooks, and `envmgr install -l`. Do not hard-code role metadata
  in Python. An inconsistency between metadata, docs, and CLI output is a bug,
  not a fallback.

### Concept ownership is declared and enforced

- A domain or technical concept is owned by exactly one module. Before
  implementing, search for the domain term, URL, or schema constant; if a module
  already owns it, deepen that module instead of re-implementing it. New concepts
  are registered in `tests/checks/single_source_of_truth.yml` and guarded by
  `tests/checks/single_source_of_truth.py`, so a second implementation fails a
  contract check instead of silently duplicating logic.

### Runtime state lives under `ENVMGR_HOME` / `~/.envmgr/`

- Runtime config, inventories, logs, and installer state are user-local and may
  be changed by the user. Never treat repo-local files as mutable runtime state.
- Persisted state is versioned. Bump the schema version and run the migration
  before changing the shape of `config.toml` or `install.toml`.

### Detection / classification is decoupled and evidence-based

- Tag and role resolution reads role metadata; it never guesses from screen
  output.
- When adding an AI-tool integration, drive it from the shared tool registry
  rather than scattered per-role conditionals.

### Multiplicative loops stay narrow

- Doctor and catalog scans are `O(roles)` or `O(checks)`, not `O(roles × roles)`.
  Before widening a loop over roles, tags, or checks, keep the work proportional
  to one pass and add a deterministic behavioral test rather than a wall-clock
  timeout.

## Hard Rules

- Don't push to `master`; it is protected and direct pushes are rejected. Use a
  `dev`→`master` PR merged with `--rebase`.
- Never commit secrets. Store sensitive runtime values under
  `~/.envmgr/inventory/group_vars/all/vault.yml` and encrypt them with
  `ansible-vault`.
- Never manually create tags; `.github/workflows/auto-tag.yml` tags on merge to
  `master`, and `release.yml` publishes from the tag.
- Treat documentation updates as part of the code change, not follow-up cleanup.
  Always review `README.md` and any user-facing command examples a change affects.
- Only set `become: true` for a role/task that needs privilege escalation;
  default playbooks run as the current user.
- Use Conventional Commits, e.g. `feat(scope): ...`, `fix(role): ...`,
  `chore(deps): ...`.
- The installed `envmgr` is the only public surface; keep checkout-only helpers
  (`create`, `lint`, `ansible-check`, `typecheck`, `validate`, `smoke-test`) out
  of installed artifacts.
- Long-lived shell exports use envmgr profile drop-ins under
  `~/.config/envmgr/profile.d/`; zsh-only snippets under
  `~/.config/envmgr/zsh/*.zsh`; user-private files stay under
  `~/.config/envmgr/user/` and are not managed by roles.

## Runtime CLI UX Contracts

These are versioned contracts and must stay in sync with the CLI, each other, and
the matching `tests/checks/*` contract tests. When you change any of the
following, update the docs (`README.md`, `docs/runtime.md`) and the contract
tests in the same patch:

- For CLI UX changes, update the `Runtime CLI UX Contracts` section.
- When playbook resolution semantics, built-in scenarios, or `--playbook` behavior changes.
- When `envmgr doctor` dependency classification, warning behavior, JSON status, or exit semantics change.

### Install playbook scenarios

- `envmgr install --playbook <scenario-or-path>` accepts scenario names (`workstation`, `node`) or filesystem paths. Scenario names select the built-in Ansible playbook topology, while path-like values (absolute, containing separators, or `.yml`/`.yaml`) resolve from the caller filesystem.
- `envmgr install --help` explains built-in scenarios and custom playbook paths;
  `envmgr install -l` shows built-in scenario descriptions before role and task
  tags.
- `envmgr install all` uses the default `playbook` from `~/.envmgr/config.toml`
  unless `--playbook` is explicit. Specific tag selections may infer a scenario
  only when they map to exactly one built-in playbook.

### Install dry run

- `envmgr install --dry-run <tag ...>` builds the normal install plan but does not start Ansible; `envmgr install --dry-run --json` emits plain JSON with stable plan keys and no Rich markup.

### Doctor

- `envmgr doctor` and `envmgr doctor --json` exit non-zero only for failing checks; warning-only reports still exit `0`. The hard command check covers Ansible runtime commands, while invalid installer-recorded `uv` paths produce a self-management warning instead of a generic runtime command failure.

### Release notes

- `gh release create` with changelog generated by git-cliff. Release notes prepend fixed install, SHA256 verification, upgrade, uninstall, and clean-reinstall guidance before the git-cliff changelog.

## Where things live

- Implementation: `src/envmgr/{main,commands,services,smoke_checks}`.
- Checkout-only helpers: `dev-helpers/` (run via `uv run ...`).
- Role metadata/tasks: `roles/<role>/meta/envmgr.yml` + `tasks/main.yml`.
- Built-in playbooks: `playbooks/`; shared defaults: `vars/` + `ansible.cfg`.
- Contract tests: `tests/checks/*`.
- Docs: `docs/runtime.md` (paths/inventory/doctor/CLI UX), `docs/development.md`
  (local workflow/helpers/role authoring/CI), `docs/release.md` (release audit,
  verification, artifacts, developer release flow).
- Project skills: `.codex/skills/`.

## Development entry points

- `uv sync` refreshes the local dev environment.
- `uv run validate` runs Ruff, unit tests (excluding `tests.test_smoke`), mypy,
  ansible-lint, and built-in playbook syntax by default; `uv run smoke-test` runs
  metadata, scaffold, CLI contract, setup, and multi-node inventory checks.
- `uv run pre-commit run --all-files` (and the pre-push stage) run the commit- and
  push-time checks via `.pre-commit-config.yaml`.
- CI aligns validation, smoke, package-surface, init-install, and Docker Compose
  master/worker e2e jobs; see `docs/development.md`.

## Release

The `release` skill (`.codex/skills/release`) triggers the automated
`dev`→`master` release; the step-by-step flow is canonical in
`docs/release.md` → "Developer Release Flow". The user handles `git push`; merge
`gh pr merge --rebase` only after required CI is green.
