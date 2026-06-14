# Repository Guidelines

This guide is the contributor and coding-agent source of truth for envmgr. Keep
the README short for users, put detailed runtime/development/release material
under `docs/`, and use these checklists to avoid drifting CLI, Ansible, docs,
and release contracts.

## Project Map Checklist

- [ ] `playbooks/` contains built-in scenario playbooks: `workstation.yml` and
  `node.yml`.
- [ ] `roles/` contains first-party envmgr roles; each enabled role keeps
  `tasks/main.yml` and `meta/envmgr.yml` aligned with tags, dependencies,
  targets, and playbook role names.
- [ ] `vars/` and `ansible.cfg` contain shared Ansible defaults bundled into
  release wheels as runtime assets.
- [ ] `src/envmgr/main.py` defines the public Typer runtime CLI for installed
  `envmgr ...`, including Rich-enhanced help and `--version`.
- [ ] `src/envmgr/commands/` contains runtime runners plus checkout-only helper
  entrypoints and CLI glue.
- [ ] `src/envmgr/services/` contains runtime config, asset resolution,
  install planning, doctor, history, and self-management logic.
- [ ] `src/envmgr/smoke_checks/` contains smoke-test-only checks used by
  `uv run smoke-test` and `tests/test_smoke.py`.
- [ ] `tests/` contains Python `unittest` modules; `tests/checks/` contains
  reusable check implementations.
- [ ] `dev-helpers/` exposes checkout-only scripts: `create`, `lint`,
  `ansible-check`, `typecheck`, `validate`, and `smoke-test`.
- [ ] `scaffolds/role/` contains templates used by `uv run create <role>`.
- [ ] `.github/` contains CI, release automation, and the Docker Compose
  master/worker e2e harness.
- [ ] Runtime state stays user-local under `ENVMGR_HOME` or `~/.envmgr/`; do
  not treat repository-local files as mutable runtime state.

## Command Surface Checklist

- [ ] Installed artifacts expose only `envmgr`.
- [ ] Use installed `envmgr ...` for supported runtime work from any cwd,
  whether installed from the GitHub Release installer or another package manager.
- [ ] Use `uv run envmgr ...` only as the repo-root fallback when working
  directly from a checkout.
- [ ] Run contributor-only helpers via `uv run ...` from an envmgr checkout.
- [ ] Treat Python import paths under `src/envmgr/` as implementation details
  except for retained compatibility shims.

## Build, Test, And Development Checklist

- [ ] `uv sync` installs or refreshes the local development environment.
- [ ] `envmgr setup` initializes `~/.envmgr/`, installs Galaxy
  roles/collections, and writes the setup-complete marker; `uv run envmgr setup`
  is the checkout fallback.
- [ ] `envmgr install -l` / `envmgr install --list-tags` lists built-in
  scenarios, role tags, and task tags.
- [ ] `envmgr install <tag ...>` applies selected tags; add
  `--playbook <scenario-or-path>` when tags are ambiguous or when overriding the
  default scenario for `all`, and add `-i <alias>` / `--ask-vault-pass` as
  needed.
- [ ] `envmgr install --dry-run <tag ...>` shows the resolved install plan
  without starting Ansible; add `--json` for plain machine-readable plan JSON.
- [ ] `envmgr ping [-i remote]` checks inventory connectivity with Ansible ping.
- [ ] `envmgr doctor [--json]` inspects runtime health; `envmgr history
  [--limit N] [--json]` inspects runtime subprocess records.
- [ ] `envmgr self update --version <version>` updates an `install.sh`-managed
  GitHub Release install; automatic latest-resolution is not implemented.
- [ ] `envmgr self uninstall [--yes]` uninstalls an `install.sh`-managed tool
  while preserving runtime data under `~/.envmgr/`.
- [ ] `uv run pre-commit install` installs `pre-commit` and `pre-push` hooks.
- [ ] `uv run pre-commit run --all-files` runs commit-time file hygiene and
  Ruff checks.
- [ ] `uv run pre-commit run --hook-stage pre-push --all-files` runs push-time
  `typecheck` and `ansible-check` when relevant files changed.
- [ ] `uv run pre-commit run --hook-stage manual validate --all-files` and
  `uv run pre-commit run --hook-stage manual smoke-test --all-files` run full
  validation and smoke suites through pre-commit.
- [ ] `uv run lint`, `uv run typecheck`, `uv run ansible-check`,
  `uv run validate`, and `uv run smoke-test` are checkout-only direct helpers.
- [ ] `uv run python -m unittest discover tests -p 'test_*.py'` runs the full
  Python test matrix; `uv run python -m unittest tests.test_smoke` runs only
  smoke tests.
- [ ] `uv build --no-sources` builds release-style wheel and sdist artifacts.

## Runtime CLI UX Contracts

- [ ] Public `envmgr` supports `-h`/`--help` at the root and subcommand levels,
  and `envmgr --version` prints `envmgr <version>`.
- [ ] Public shell completion stays disabled intentionally with
  `add_completion=False`; keep generated completion options rejected unless the
  decision, docs, and tests change together.
- [ ] Public `envmgr install --playbook` accepts scenario names (`workstation`,
  `node`) or filesystem paths. Scenario names select the built-in Ansible playbook topology, while path-like values (absolute, containing separators, or `.yml`/`.yaml`) resolve from the caller filesystem.
- [ ] Public `envmgr install --help` explains built-in scenarios and custom
  playbook paths; `envmgr install -l` shows built-in scenario descriptions
  before role and task tags.
- [ ] `envmgr install all` uses the default `playbook` from
  `~/.envmgr/config.toml` unless `--playbook` is explicit. Specific tag
  selections may infer a scenario only when they map to exactly one built-in
  playbook.
- [ ] Public `envmgr install --dry-run` builds the normal install plan but
  does not start Ansible. Human output uses Rich and includes source/execution
  playbooks, inventory, selected tags, effective ask-vault status, AI tools
  choices when applicable, and final command argv/readable command.
  `envmgr install --dry-run --json` emits plain JSON with stable plan keys and
  no Rich markup.
- [ ] Public `envmgr doctor` and `envmgr doctor --json` exit non-zero only for failing checks; warning-only reports still exit `0`. The hard command check covers Ansible runtime commands (`ansible`, `ansible-playbook`, `ansible-galaxy`), while invalid installer-recorded `uv` paths produce a self-management warning instead of a generic runtime command failure.
- [ ] Public `envmgr self update` and `envmgr self uninstall` are limited to
  installer-managed GitHub Release installs with `~/.envmgr/install.toml`;
  unsupported install methods fail with actionable guidance instead of mutating
  the user's tool environment.
- [ ] Public `envmgr self update --version VERSION` is required because
  automatic latest-release resolution is not implemented. `envmgr self
  uninstall` prompts through the shared Rich confirm helper unless `--yes` or
  `-y` is provided, removes only installer state and the uv tool install, and
  keeps the rest of `~/.envmgr/` runtime data by default.
- [ ] Use Rich for runtime human help, status, warnings, summaries, prompts,
  and the human `envmgr history` table. Keep JSON output and live external
  subprocess stdout/stderr plain.
- [ ] Checkout-only developer helpers keep plain tool-style logs even though
  their entrypoints use Typer-based help.
- [ ] Expected runtime exits use `typer.Exit` inside command paths, send
  actionable user guidance to stderr, and preserve shell-friendly exit codes
  (`0`, `1`, `2`, `130`).

## Code And Role Checklist

- [ ] Python uses 4-space indent, line length 88, double quotes, Ruff
  formatting/import ordering, and strict mypy-compatible type hints
  (`disallow_untyped_defs`, `no_implicit_optional`, strict equality, etc.).
- [ ] Ansible uses YAML `.yml`/`.yaml`; role folders are `lower-kebab-case`;
  tags are `snake_case`; vars are `lower_snake_case`.
- [ ] Tasks are idempotent when practical and use clear imperative task names.
- [ ] Role metadata in `roles/<role>/meta/envmgr.yml` drives tag discovery,
  dependency closure, generated execution playbooks, and docs.
- [ ] Long-lived shell environment exports use envmgr profile drop-ins under
  `~/.config/envmgr/profile.d/`; zsh-only aliases, prompt, and UX snippets live
  under `~/.config/envmgr/zsh/*.zsh`, while user-private files stay under
  `~/.config/envmgr/user/` and are not managed by roles.
- [ ] New roles are created with `uv run create <role>`, then
  `roles/<role>/meta/envmgr.yml`, `tasks/main.yml`, and the appropriate
  scenario playbook are updated together.

## Testing Checklist

- [ ] Treat pre-commit as the primary local workflow; use direct helper commands
  only when rerunning one tool or reproducing CI more directly.
- [ ] Run `uv sync` when development tooling needs refresh.
- [ ] Run `envmgr setup` when runtime inventory, Galaxy content, or the setup
  marker is missing; use `uv run envmgr setup` as the checkout fallback.
- [ ] `uv run validate` checks Ruff, unit tests excluding `tests.test_smoke`,
  mypy, ansible-lint, and built-in playbook syntax checks by default.
- [ ] `uv run smoke-test` checks metadata, scaffolds, CLI contracts, setup
  behavior, multi-node inventory topology, and built-in playbook `--list-tags`.
- [ ] Use `uv run validate --playbook <path>` and
  `uv run smoke-test --playbook <path>` for targeted scenario checks;
  `--playbook` can be repeated and `-i <alias>` selects a configured runtime
  inventory.

## Documentation Checklist

- [ ] Treat documentation updates as part of the code change, not follow-up
  cleanup.
- [ ] Keep `README.md` as the concise user landing page with quickstart, common
  commands, scenarios/tags, AI tools, and development entry points.
- [ ] Put runtime paths, inventory behavior, doctor details, role versions, and
  CLI UX contracts in `docs/runtime.md`.
- [ ] Put local workflow, helper commands, role authoring, and CI jobs in
  `docs/development.md`.
- [ ] Put release audit, installer verification, artifact rules, and release
  notes in `docs/release.md`.
- [ ] Always review `AGENTS.md`, `README.md`, and any user-facing command
  examples affected by a change.
- [ ] When public `envmgr` commands, options, arguments, defaults, or exit
  semantics change, update user-facing docs and docs contract tests so
  `tests/test_docs_contracts.py` continues to prove the public CLI surface is
  documented.
- [ ] For CLI UX changes, update the `Runtime CLI UX Contracts` section
  alongside README examples so the Typer/Rich contract stays current.
- [ ] When playbook resolution semantics, built-in scenarios, or `--playbook` behavior changes, update `README.md`, `AGENTS.md`, CLI help/list output, and docs/CLI contract tests in the same patch.
- [ ] When `envmgr doctor` dependency classification, warning behavior, JSON
  status, or exit semantics change, update `README.md`, `AGENTS.md`, and docs
  contract tests in the same patch.
- [ ] Keep `CLAUDE.md` as a thin pointer to `AGENTS.md`.
- [ ] During reviews or automated maintenance passes, explicitly check whether
  the code diff should trigger docs updates and make them proactively.

## Release Checklist

- [ ] CI keeps separate validation, smoke, package-surface, init-install, and
  Docker Compose master/worker e2e jobs aligned with the supported runtime and
  helper split.
- [ ] `.github/workflows/release.yml` publishes immutable version tags matching
  `vX.Y.Z` only after locked sync, setup, validation, smoke tests,
  release-style build, artifact inspection, installer preparation, SHA256
  checksum generation, isolated wheel-install smoke testing, and
  `gh release create` with GitHub-generated release notes.
- [ ] Release artifacts include only the envmgr wheel, sdist, generated
  `install.sh`, and `SHA256SUMS`; never publish an `envmgr-dev-helpers`
  artifact.
- [ ] User-facing release docs explain how to inspect `install.sh`, verify
  SHA256 checksums, install, upgrade with
  `envmgr self update --version <version>`, uninstall with
  `envmgr self uninstall [--yes]`, and clean-reinstall stale shims with
  `uv tool uninstall envmgr`, the GitHub Release installer, and `hash -r`.
- [ ] Release notes prepend fixed install, SHA256 verification, upgrade,
  uninstall, and clean-reinstall guidance before GitHub-generated notes.

## PR And Security Checklist

- [ ] Use Conventional Commits seen in history, such as `feat(scope): ...`,
  `fix(role): ...`, or `chore(deps): ...`.
- [ ] Keep diffs focused. PRs include purpose, affected roles/tags,
  user-facing command examples, and relevant logs or screenshots.
- [ ] Link issues when applicable and pass relevant lint, type, validation,
  smoke, or release-surface checks before review.
- [ ] Do not commit secrets. Store sensitive runtime values under
  `~/.envmgr/inventory/group_vars/all/vault.yml` and encrypt them with
  `ansible-vault`.
- [ ] For AI tools, prefer install-time CLI flags or the interactive wizard, and
  pass `CONTEXT7_API_KEY` through the environment when needed.
- [ ] Default playbooks run as the current user; set `become: true` only where a
  role/task needs privilege escalation.
