# Development Guide

This guide is for contributors working from an envmgr checkout. Use installed
`envmgr ...` for runtime work from any directory, use `uv run envmgr ...` only
as a repo-root fallback, and use checkout-only helpers through `uv run ...`.

## Source Map

- `playbooks/` - built-in scenario playbooks: `workstation.yml` and `node.yml`.
- `roles/` - first-party envmgr roles and `meta/envmgr.yml` metadata.
- `vars/` and `ansible.cfg` - shared Ansible defaults bundled into wheels.
- `src/envmgr/main.py` - public Typer runtime CLI with Rich help.
- `src/envmgr/commands/` - runtime runners and helper CLI glue.
- `src/envmgr/services/` - asset resolution, install planning, doctor,
  history, runtime config, and self-management logic.
- `src/envmgr/smoke_checks/` - smoke-test-only check implementations.
- `tests/` - Python `unittest` modules and reusable check helpers.
- `dev-helpers/` - checkout-only helper package.
- `scaffolds/role/` - templates used by `uv run create <role>`.

Runtime state belongs under `ENVMGR_HOME` or `~/.envmgr/`, never in the
repository checkout.

## Bootstrap

```bash
uv sync
envmgr setup
uv run envmgr setup
```

Run `uv sync` when development tooling needs refresh. Run `envmgr setup` when
runtime inventory, Galaxy content, or the setup marker is missing. Use
`uv run envmgr setup` only as the checkout fallback before the public command is
installed.

## Pre-commit First

```bash
uv run pre-commit install
uv run pre-commit run --all-files
uv run pre-commit run --hook-stage pre-push --all-files
uv run pre-commit run --hook-stage manual validate --all-files
uv run pre-commit run --hook-stage manual smoke-test --all-files
```

The commit-time hook runs file hygiene and Ruff checks. The pre-push hook runs
`typecheck` and `ansible-check` when relevant files changed. The manual stage
exposes full validation and smoke suites through the same pre-commit interface.

## Direct Helpers

Use direct helpers for focused debugging or CI reproduction:

```bash
uv run create <role>
uv run lint
uv run typecheck
uv run ansible-check
uv run validate
uv run smoke-test
uv run python -m unittest discover tests -p 'test_*.py'
uv run python -m unittest tests.test_smoke
```

`uv run validate` checks Ruff, unit tests excluding `tests.test_smoke`, mypy,
ansible-lint, and built-in playbook syntax checks by default. `uv run
smoke-test` checks role metadata, scaffolds, CLI contracts, setup behavior,
multi-node inventory topology, and built-in playbook `--list-tags` output.

Both helpers accept repeated `--playbook <path>` values for targeted scenario
checks, and `-i <alias>` selects a configured runtime inventory alias.

## Role Checklist

When adding or changing a role:

- Create new roles with `uv run create <role>`.
- Keep role folders `lower-kebab-case`; keep tags `snake_case`.
- Update `roles/<role>/tasks/main.yml` and any imported task files.
- Update `roles/<role>/meta/envmgr.yml` for tags, dependencies, targets,
  vars files, Galaxy role dependencies, and playbook role names.
- Update the relevant built-in scenario playbook.
- Keep tasks idempotent when practical and verify scoped tag runs select only
  the intended role/task closure.
- Update README, docs, AGENTS, and docs contract tests when public behavior or
  examples change.

## Docs Checklist

- Keep README as a short human landing page.
- Put runtime paths, inventory behavior, doctor details, and CLI UX contracts in
  `docs/runtime.md`.
- Put development workflows and CI job notes in this file.
- Put release audit, artifact, installer, and release-note guidance in
  `docs/release.md`.
- Keep `AGENTS.md` as the maintainer and coding-agent source of truth.
- Keep `CLAUDE.md` as a thin pointer to `AGENTS.md`.
- If public commands, options, defaults, exit semantics, or playbook resolution
  change, update `tests/checks/docs_contracts.py` expectations as needed.

## CI Jobs

GitHub Actions should keep these paths aligned:

- Validation: locked sync, lint, unit tests, mypy, ansible-lint, and playbook
  syntax checks.
- Smoke: metadata checks, scaffolds, CLI contracts, setup behavior, inventory
  topology, and `--list-tags` checks.
- Package surface: wheel/sdist inspection and runtime command exposure checks.
- Init install: installer and first-run bootstrap coverage.
- Docker Compose e2e: one master plus two workers for representative runtime
  flows such as `envmgr install zsh` and `envmgr install ai_tools --codex`.

Before opening a PR, run the smallest relevant local check first, then the full
`uv run validate` or `uv run smoke-test` path when the change affects shared
runtime behavior.
