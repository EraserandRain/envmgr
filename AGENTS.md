# Repository Guidelines

This guide helps contributors work effectively on envmgr (Ansible-driven environment setup with a small Python CLI).

## Project Structure & Module Organization

- `playbooks/` — scenario playbooks (`workstation.yml`, `node.yml`).
- `roles/` — one folder per tool (`tasks/main.yml`, `vars/`, etc.).
- `scripts/` — Python CLI entrypoints plus `commands/` and `services/` modules used by `uv`.
- `tests/` — Python `unittest` modules split by domain plus a dedicated smoke suite exercised by `uv run smoke-test`.
- `vars/` — shared variables; `ansible.cfg` — repository Ansible defaults; runtime state lives under `~/.envmgr/`.

## Build, Test, and Development Commands

- `uv sync` — install or refresh the local Python environment for development work.
- `uv run envmgr setup` — initialize `~/.envmgr/` and install Galaxy roles/collections for runtime use.
- `uv run envmgr install -l` — list tags; `uv run envmgr install <tag ...>` — apply tags; add `--playbook <path>` when tags are ambiguous, plus `-i <alias>` or `--ask-vault-pass` as needed.
- `uv run envmgr ping [-i remote]` — connectivity check.
- `uv run pre-commit install` — install `pre-commit` and `pre-push` Git hooks.
- `uv run pre-commit run --all-files` — run the standard commit-time checks (YAML hygiene + Ruff).
- `uv run pre-commit run --hook-stage pre-push --all-files` — run the push-time checks (`typecheck` + `ansible-check`).
- `uv run pre-commit run --hook-stage manual validate --all-files` — run the full validation suite through `pre-commit`.
- `uv run pre-commit run --hook-stage manual smoke-test --all-files` — run the smoke suite through `pre-commit`.
- `uv run lint`, `uv run ansible-check`, and `uv run typecheck` are rare direct entrypoints for debugging one tool in isolation.
- `uv run validate` and `uv run smoke-test` remain the direct full-suite entrypoints for CI or more targeted troubleshooting; `validate` runs the split unit modules while `smoke-test` runs the smoke suite.

## Coding Style & Naming Conventions

- Python: 4‑space indent, line length 88, double quotes (Ruff); add type hints (mypy strict settings; no untyped defs).
- Ansible: YAML `.yml/.yaml`; role folders `lower-kebab-case`; tags `snake_case`; vars `lower_snake_case`. Prefer idempotent tasks and clear imperative names.
- Create new roles with `uv run create <role>` and place tasks in `roles/<role>/tasks/main.yml`.

## Testing Guidelines

- Treat `pre-commit` as the primary local workflow; direct commands are mostly for rerunning one tool by itself or reproducing a CI failure more directly.
- Run `uv sync` when you need the local development environment or tooling refreshed; run `uv run envmgr setup` when you need the user runtime inventory and Galaxy content bootstrapped.
- Use `uv run validate --playbook <path>` and `uv run smoke-test --playbook <path>` for scenario-level checks against the runtime inventory managed under `~/.envmgr/`.
- Run `uv run python -m unittest discover tests -p 'test_*.py'` when you want the full Python test matrix, or `uv run python -m unittest tests.test_smoke` when you want just the Python smoke suite without the CLI wrapper.
- Ensure tasks are idempotent (second run reports no changes) and scoping via tags works as expected.

## Documentation Sync

- Treat documentation updates as part of the code change, not as follow-up cleanup.
- When behavior, commands, flags, defaults, test layout, project structure, or developer workflow changes, update the relevant docs in the same patch.
- Always review `AGENTS.md`, `README.md`, and any user-facing command examples affected by the change; stale examples or outdated command descriptions should be fixed before finishing.
- Use `AGENTS.md` as the repository instruction source of truth and keep `CLAUDE.md` as a thin pointer to `AGENTS.md` rather than maintaining duplicated guidance.
- During reviews or automated maintenance passes, explicitly check whether the code diff should trigger doc updates and make them proactively.

## Commit & Pull Request Guidelines

- Use Conventional Commits (seen in history): `feat(scope): ...`, `fix(role): ...`, `chore(deps): ...`.
- PRs should include: purpose, affected roles/tags, sample commands used (e.g., `uv run envmgr install zsh`), and relevant logs/screenshots.
- Link issues, keep diffs focused, and pass all lint/type checks.

## Security & Configuration Tips

- Do not commit secrets. Use `~/.envmgr/inventory/group_vars/all/vault.yml` + `ansible-vault` for sensitive data.
- For AI tools, prefer install-time CLI choices and pass `CONTEXT7_API_KEY` via the environment when needed.
- Default playbooks run as the current user; only set `become: true` where necessary.
