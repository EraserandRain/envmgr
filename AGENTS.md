# Repository Guidelines

This guide helps contributors work effectively on envmgr (Ansible-driven environment setup with a small Python CLI).

## Project Structure & Module Organization

- `playbooks/` — scenario playbooks (`workstation.yml`, `node.yml`).
- `roles/` — one folder per tool (`tasks/main.yml`, `vars/`, etc.).
- `scripts/` — Python CLI entrypoints used by `uv`.
- `vars/` — shared variables; `ansible.cfg` — repository Ansible defaults; runtime state lives under `~/.envmgr/`.

## Build, Test, and Development Commands

- `uv run setup` — sync deps, initialize `~/.envmgr/`, install Galaxy roles.
- `uv run install -l` — list tags; `uv run install <tag ...>` — apply tags; add `--playbook <path>` when tags are ambiguous, plus `-i <alias>` or `--ask-vault-pass` as needed.
- `uv run ping [-i remote]` — connectivity check.
- `uv run lint` — Ruff lint + format check for `scripts/`.
- `uv run ansible-check` — `ansible-lint` on `roles/`.
- `uv run typecheck` — mypy type checks.
- `uv run validate` / `uv run smoke-test` — combined checks and lightweight integration coverage.

## Coding Style & Naming Conventions

- Python: 4‑space indent, line length 88, double quotes (Ruff); add type hints (mypy strict settings; no untyped defs).
- Ansible: YAML `.yml/.yaml`; role folders `lower-kebab-case`; tags `snake_case`; vars `lower_snake_case`. Prefer idempotent tasks and clear imperative names.
- Create new roles with `uv run create <role>` and place tasks in `roles/<role>/tasks/main.yml`.

## Testing Guidelines

- Run `uv run validate` and `uv run smoke-test` before PRs.
- Use `uv run validate --playbook <path>` and `uv run smoke-test --playbook <path>` for scenario-level checks against the runtime inventory managed under `~/.envmgr/`.
- Ensure tasks are idempotent (second run reports no changes) and scoping via tags works as expected.

## Commit & Pull Request Guidelines

- Use Conventional Commits (seen in history): `feat(scope): ...`, `fix(role): ...`, `chore(deps): ...`.
- PRs should include: purpose, affected roles/tags, sample commands used (e.g., `uv run install zsh`), and relevant logs/screenshots.
- Link issues, keep diffs focused, and pass all lint/type checks.

## Security & Configuration Tips

- Do not commit secrets. Use `~/.envmgr/inventory/group_vars/all/vault.yml` + `ansible-vault` for sensitive data.
- For AI tools, prefer install-time CLI choices and pass `CONTEXT7_API_KEY` via the environment when needed.
- Default playbooks run as the current user; only set `become: true` where necessary.
