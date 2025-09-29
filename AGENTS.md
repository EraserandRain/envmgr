# Repository Guidelines

This guide helps contributors work effectively on envmgr (Ansible-driven environment setup with a small Python CLI).

## Project Structure & Module Organization
- `entry.yaml` — main playbook (tags map to roles/tasks).
- `roles/` — one folder per tool (`tasks/main.yml`, `vars/`, etc.).
- `inventory/` — inventories (`default.yaml` for local, `*.example` for remote/password).
- `scripts/` — Python CLI entrypoints used by `uv`.
- `vars/` — shared variables; `ansible.cfg` — Ansible defaults; `log/` — runtime logs.

## Build, Test, and Development Commands
- `uv run setup` — sync deps, init logs, install Galaxy roles.
- `uv run install -l` — list tags; `uv run install <tag ...>` — apply tags; add `-i <inventory>` or `--ask-vault-pass` as needed.
- `uv run ping [-i inventory/remote.yaml]` — connectivity check.
- `uv run lint` — Ruff lint + format check for `scripts/`.
- `uv run ansible-check` — `ansible-lint` on `roles/`.
- `uv run typecheck` — mypy type checks.

## Coding Style & Naming Conventions
- Python: 4‑space indent, line length 88, double quotes (Ruff); add type hints (mypy strict settings; no untyped defs).
- Ansible: YAML `.yml/.yaml`; role folders `lower-kebab-case`; tags `snake_case`; vars `lower_snake_case`. Prefer idempotent tasks and clear imperative names.
- Create new roles with `uv run create <role>` and place tasks in `roles/<role>/tasks/main.yml`.

## Testing Guidelines
- Run `uv run lint`, `uv run ansible-check`, and `uv run typecheck` before PRs.
- Validate changes with a dry run: `ansible-playbook -i inventory/default.yaml entry.yaml -C -t <tags>`.
- Ensure tasks are idempotent (second run reports no changes) and scoping via tags works as expected.

## Commit & Pull Request Guidelines
- Use Conventional Commits (seen in history): `feat(scope): ...`, `fix(role): ...`, `chore(deps): ...`.
- PRs should include: purpose, affected roles/tags, sample commands used (e.g., `uv run install zsh`), and relevant logs/screenshots.
- Link issues, keep diffs focused, and pass all lint/type checks.

## Security & Configuration Tips
- Do not commit secrets. Use `inventory/password.yaml.example` + `ansible-vault` for sensitive data.
- Default playbooks run as the current user; only set `become: true` where necessary.
