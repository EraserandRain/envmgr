# Envmgr

`envmgr` is a tool for quick deployment to install and configure tools with Ansible.

## Quick Start

### Dependencies

Envmgr requires Python 3.10 or later and the uv package.

Please install `uv` first 【[uv installation](https://docs.astral.sh/uv/getting-started/installation/)】.

### Install envmgr

After installing `uv`, choose one runtime install mode so `envmgr ...` is
available directly in your shell from any working directory.

**Editable install from a checkout:**

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install envmgr from this repo checkout as an editable global tool
uv tool install --editable /home/eraserrain/envmgr

# Show the directory that contains uv-managed tool shims
uv tool dir --bin

# Add the uv tool bin directory to your shell startup if needed
uv tool update-shell
```

To refresh the editable tool after pulling changes in this checkout, run
`uv tool install --editable --force /home/eraserrain/envmgr`.

**Wheel install from a built artifact:**

```bash
# Build wheel + sdist artifacts
uv build

# Install the built wheel as a global tool
uv tool install dist/envmgr-*.whl
```

Wheel builds bundle the runtime assets that `envmgr` needs at execution time,
including `playbooks/`, `roles/`, `vars/`, `ansible.cfg`, and
`requirements.yaml`, under the installed Python package. Editable installs keep
using the checkout copy of those same assets. In both cases, the installed
`envmgr ...` command is the supported runtime surface and works outside the
repo root.

Installed artifacts expose only the `envmgr ...` runtime command.
Contributor-only helpers such as `create`, `lint`, `ansible-check`,
`typecheck`, `validate`, and `smoke-test` are checkout-local workflows run via
`uv run ...` from this repository. When you are working directly from this
checkout without installing a tool shim, `uv run envmgr ...` remains the
repo-root fallback.

To remove the global tool shim entirely, run `uv tool uninstall envmgr`. If
your shell still reports `envmgr: command not found`, check the uv-managed bin
directory with `uv tool dir --bin`, then run `uv tool update-shell` and start a
new shell session so that directory is added to your `PATH`.

### First-Time Setup

`envmgr setup` is the required bootstrap step on a new machine. It initializes
`~/.envmgr/` and installs the Galaxy roles and collections that envmgr
playbooks expect. For contributor workflows, run `uv sync` separately when you
want to install or refresh the local Python environment and dev tools.

```bash
# Bootstrap envmgr on this machine
envmgr setup

# Verify the bootstrap completed successfully
envmgr doctor
envmgr doctor --json
envmgr ping
envmgr install -l
```

Run `envmgr setup` before `envmgr install` or `envmgr ping` on a fresh machine
or a fresh `ENVMGR_HOME`. Contributors should also run it before checkout-local
helpers such as `uv run validate` and `uv run smoke-test`. Inside the repo
root, `uv run envmgr setup` is the fallback form of the same runtime command.
The bootstrap step is safe to re-run and does not overwrite existing runtime
config files. `uv run validate` now checks both `scripts/` and `tests/`, runs
the split
`tests/test_*.py` unit modules automatically while excluding `tests.test_smoke`,
and `uv run smoke-test` runs only the
`tests.test_smoke` suite before the playbook `--list-tags` checks.

`envmgr doctor` performs a read-only health check for the current runtime. It is
safe to run before or after setup when you want to inspect what is missing
under `~/.envmgr/`.
Use `envmgr doctor --json` when you want a machine-readable report for scripts
or CI.
Use `envmgr history` to inspect the most recent runtime subprocess records, or
`envmgr history -n 5` to focus on the latest few commands.
The public runtime CLI uses Typer with Rich help plus shared Rich headings,
summary lines, and prompts for `setup`, `install`, and `ping`. Development
helpers such as `uv run validate` and `uv run smoke-test` also use dedicated
Typer-based help, but they remain separate entrypoints rather than runtime
subcommands.

### Host Settings

Runtime configuration is saved under `~/.envmgr/`. By default, `envmgr setup`
creates:

- `~/.envmgr/config.toml`
- `~/.envmgr/inventory/default.yaml`
- `~/.envmgr/inventory/remote.yaml`
- `~/.envmgr/inventory/password.yaml`
- `~/.envmgr/log/`
- `~/.envmgr/cache/`

For `envmgr` runtime commands, envmgr now uses these runtime paths consistently:

- Ansible logs are written to `~/.envmgr/log/ansible.log`
- Runtime subprocess records are written to `~/.envmgr/log/runs/*.json`
- Galaxy roles are installed to `~/.envmgr/cache/galaxy/roles`
- Galaxy collections are installed to `~/.envmgr/cache/galaxy/collections`
- Temporary Ansible files use `~/.envmgr/cache/tmp`

Repository-local files still keep their original purpose:

- `roles/` stays the source of first-party envmgr roles in this repo
- `playbooks/` stays the source of scenario playbooks in this repo
- `scripts/main.py` defines the Typer-based public `envmgr` CLI used by the
  installed `envmgr ...` command plus the checkout-local fallback
  `uv run envmgr ...`, with Rich help plus shared Rich runtime summaries/prompts
- `scripts/commands/` holds command runners plus the dedicated helper entrypoints and CLI glue shared by the public CLI and helper commands
- `scripts/services/` holds reusable runtime, install-planning, and doctor logic
- `scripts/smoke_checks/` stays reserved for smoke-test-only checks
- `tests/checks/` holds the finer-grained unit-check implementations used by `validate`
- `ansible.cfg` remains repository metadata used by envmgr internals and project checks

The installed `envmgr ...` command is the supported runtime command surface for
envmgr. Editable installs from a checkout and wheel installs from built
artifacts both support running `envmgr ...` outside the repo root because the
runtime assets are resolved from the installed package or the live checkout.
Development helpers stay separate as checkout-only commands such as
`uv run create`, `uv run lint`, `uv run ansible-check`, `uv run typecheck`,
`uv run validate`, and `uv run smoke-test`. Those helpers are contributor-only
and not part of the installed runtime surface. `uv run envmgr ...` remains the
explicit fallback when you are already inside the repo root and want to run the
checkout directly.
Direct `ansible-playbook` or `ansible-galaxy` usage from the repository is not
a supported interface.
Repository-internal Python import paths under `scripts/` are implementation
details; any conservative compatibility re-exports or root-command shims are
not a supported public API.

The public runtime CLI now uses Typer with Rich-enhanced help plus shared Rich
runtime summaries, status lines, and interactive prompts where applicable, and
the dedicated developer helper commands also use Typer-based help. The
supported command surfaces stay intentionally split: run installed runtime
commands as `envmgr ...`, use `uv run envmgr ...` only as the repo-root
fallback for a checkout, and run contributor-only helpers from a checkout via
`uv run ...`. Installed artifacts expose only `envmgr`.

Commands that accept `-i/--inventory` only accept inventory aliases defined in `~/.envmgr/config.toml`. envmgr no longer falls back to repository-local inventory files or `./.ansible` caches.
Inventory alias targets must stay under `~/.envmgr/inventory/`.

**Default Configuration (`~/.envmgr/config.toml`):**

```toml
[default]
inventory = "default"
playbook = "workstation"
ask_vault_pass = false

[inventory]
default = "inventory/default.yaml"
remote = "inventory/remote.yaml"
password = "inventory/password.yaml"
```

**Default Local Inventory (`~/.envmgr/inventory/default.yaml`):**

```yaml
all:
  children:
    workstation:
      hosts:
        localhost:
          ansible_connection: local
          ansible_python_interpreter: "{{ ansible_playbook_python }}"
    node:
      children:
        master:
          hosts:
            localhost:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
```

> **Note:** `envmgr install <tags>` now resolves the scenario playbook from the selected tags. If the tags are valid in more than one scenario, pass `--playbook workstation` or `--playbook node` explicitly.
> `envmgr install all` uses the `playbook` value from `~/.envmgr/config.toml` by default.

**For Remote Hosts:**

1. **SSH Key Authentication (Recommended):**
   - Edit `~/.envmgr/inventory/remote.yaml`
   - Modify the host IPs, usernames, and SSH key paths accordingly
   - Ensure SSH keys are properly configured

2. **Password Authentication (If necessary):**
   - Edit `~/.envmgr/inventory/password.yaml`
   - Put sensitive variables in `~/.envmgr/inventory/group_vars/all/vault.yml`
   - Use `ansible-vault` to encrypt sensitive information
   - Requires `sshpass` package (already installed)

Example remote configuration:

```yaml
all:
  children:
    node:
      children:
        master:
          hosts:
            remote-host:
              ansible_host: 192.168.1.100
              ansible_user: your_username
              ansible_ssh_private_key_file: ~/.ssh/id_rsa
        worker:
          hosts:
            worker1:
              ansible_host: 192.168.1.101
            worker2:
              ansible_host: 192.168.1.102
```

### Setup Tools

Setup specified tools using role-level or task-level tags:

Run `envmgr setup` first on a new machine so the runtime inventory, Galaxy
dependencies, and cache directories already exist.

**Local execution (default):**

```bash
# List all available tags
envmgr install -l

# Install specified tools
envmgr install [tag1 tag2 ...]

# Install all roles in one scenario
envmgr install all

# Examples:
envmgr install init              # Apply the baseline host bootstrap bundle
envmgr install zsh               # Install zsh with oh-my-zsh and aliases
envmgr install kubeadm           # Install kubeadm on node targets
envmgr install golang dotnet     # Install multiple tools (space-separated)
envmgr install kubernetes_tools  # Install kubectl, helm, crictl, CNI plugins
envmgr install ai_tools          # Launch the interactive AI Tools Setup wizard in a TTY
envmgr install ai_tools --codex  # Install default AI tools and explicitly manage Codex CLI
envmgr install ai_tools --no-rtk # RTK is enabled by default; use this to skip it

# Use an explicit scenario token for ambiguous tags or full-scenario runs
envmgr install --playbook workstation zsh node ai_tools
envmgr install --playbook node docker kubeadm

# Use a scenario-specific token for a common preset
envmgr install --playbook workstation init zsh java node golang ruby dotnet cloud
envmgr install --playbook workstation init docker kubernetes_tools minikube
envmgr install --playbook node docker kubeadm monitoring

The `node` scenario installs shared node prerequisites on every cluster node,
then applies cluster management tools only on the `master` group.
```

**Remote execution:**

```bash
# Using SSH key authentication
envmgr install -i remote zsh

# Use a scenario-specific token on remote hosts
envmgr install -i remote --playbook node docker kubeadm

# Using password authentication (with vault)
envmgr install -i password --playbook node --ask-vault-pass docker kubeadm

# List tags (inventory-independent)
envmgr install -l

# Install multiple components on remote hosts
envmgr install -i remote zsh docker kubernetes_tools
```

**Test connection:**

```bash
# Test local connection
envmgr ping

# Inspect runtime health
envmgr doctor
envmgr doctor --json

# Test remote connection
envmgr ping -i remote

# Test with password authentication
envmgr ping -i password
```

#### Available Tags

##### Role-level Tags

Role-level tags install complete functional modules:

- ai_tools
- cloud
- docker
- dotnet
- golang
- init   (workstation baseline bundle)
- java
- kubeadm
- kubernetes_tools
- minikube
- monitoring
- node
- ruby   (default version: 3.0.5)
- zsh

The `node` scenario runs `docker` and `kubeadm` on all nodes, while
`kubernetes_tools` and `monitoring` stay master-only.

##### Task-level Tags

Task-level tags execute specific configuration tasks:

- claude_code (configure Claude Code)
- codex (install or update Codex CLI explicitly)
- rtk (install or update RTK explicitly)
- hashicorp (install HashiCorp repository tooling)
- terraform (install Terraform)
- tf (alias for Terraform tasks)

You can use `envmgr install -l` to see the complete list of available tags. From
the repo root, `uv run envmgr install -l` remains the fallback form.

Supported Setup Items:

- ai_tools:
  - Claude Code (Anthropic's AI development CLI)
  - Context7 MCP integration for Claude Code
- codex:
  - Codex (OpenAI's coding assistant CLI)
  - Context7 MCP integration for Codex
- rtk:
  - RTK CLI proxy
  - `rtk init --global --auto-patch` for Claude Code when both tools are managed
  - `rtk init --global --codex` for Codex CLI when both tools are managed
- cloud
  - terraform
- zsh
- node   (latest version)
- golang (default version: 1.20.4)
- ruby   (default version: 3.0.5)
- docker
- dotnet (default version: 8.0)
- java (default version: 8)
- init:
  - system time synchronization and timezone setup
  - git installation and global defaults
  - GitHub CLI installation
- minikube (latest)
- kubeadm (1.31.9-1.1)
- kubernetes_tools:
  - kubectl (default version: 1.31)
  - helm
- monitoring

#### AI Tools Configuration

The AI tools role installs Claude Code plus RTK by default, with optional Codex CLI support. Context7 remains available for Claude Code and Codex CLI.

**Prerequisites:**

- Node.js (will be installed via the `node` role if not present)
- Volta package manager (will be installed via the `node` role)

When you run `envmgr install ai_tools` in a TTY without AI-tools flags, envmgr
launches an `AI Tools Setup` wizard that:

- lets you choose Claude Code, Codex CLI, and/or RTK
- asks whether to enable Context7 integration
- explains the Context7 connection modes before you choose one
- shows a shared Rich summary and asks for confirmation before installation starts
- can be cancelled at any time with `Ctrl+C`

You can also skip the wizard and drive the same choices with CLI flags:

```bash
envmgr install ai_tools --codex
envmgr install ai_tools --no-rtk
envmgr install ai_tools --no-context7
envmgr install ai_tools --codex --codex-context7-method remote
envmgr install ai_tools --claude-code --codex --rtk --claude-context7-method local
```

If your Context7 setup needs an API key, export `CONTEXT7_API_KEY` before
running `envmgr install ...`.

RTK is enabled by default for `ai_tools` installs and is placed into `~/.local/bin`. When Claude Code is also selected, envmgr runs `rtk init --global --auto-patch`. When Codex CLI is also selected, envmgr runs `rtk init --global --codex`. envmgr resolves RTK releases through GitHub release redirects instead of the REST API, so anonymous GitHub API rate limits do not block the default install path.

**Installation:**

```bash
# Install AI tools (requires node role as prerequisite)
envmgr install node ai_tools

# Or install everything at once
envmgr install init node ai_tools

# Install Claude Code, Codex, and RTK together
envmgr install ai_tools --codex

# Install Codex only, without Context7
envmgr install ai_tools --no-claude-code --codex --no-context7

# Install RTK only
envmgr install rtk
```

### Development Commands

Run `uv sync` when you want to populate or refresh the local development
virtualenv. Run `envmgr setup` before `uv run validate` or `uv run smoke-test`
on a fresh machine; `uv run envmgr setup` remains the repo-root fallback when
you are running directly from the checkout. Those commands execute playbook
checks that rely on the runtime inventory and Galaxy content installed during
bootstrap. The helper commands in this section are contributor-only checkout
entry points: run them via `uv run ...` from this checkout and keep
`envmgr ...` as the installed runtime surface.

```bash
# Install or refresh the local dev environment
uv sync

# Create a new role
uv run create <role>

# Generated role scaffold includes:
# - tasks/main.yml
# - tasks/<role>.yml
# - defaults/main.yml
# - vars/main.yml
# - meta/main.yml
# - meta/envmgr.yml
# - README.md

# Install local Git hooks for commit-time and push-time checks
uv run pre-commit install

# Run the commit-time hook suite across the whole repository
uv run pre-commit run --all-files

# Run the push-time hook suite manually
uv run pre-commit run --hook-stage pre-push --all-files

# Run the full validation flows through pre-commit
uv run pre-commit run --hook-stage manual validate --all-files
uv run pre-commit run --hook-stage manual smoke-test --all-files

# Run the full Python test matrix directly
uv run python -m unittest discover tests -p 'test_*.py'

# Run only the Python smoke suite directly
uv run python -m unittest tests.test_smoke

# GitHub Actions also runs a containerized 1 master + 2 workers e2e that
# covers the same `envmgr install zsh` and `envmgr install ai_tools --codex`
# runtime flows from the master node against the full workstation group.

# Rare direct entrypoints for debugging one tool in isolation
# Most day-to-day local checks should go through pre-commit instead.
uv run lint
uv run ansible-check
uv run typecheck
uv run validate
uv run smoke-test

# Validate specific playbooks directly
uv run validate --playbook playbooks/workstation.yml
uv run validate --playbook playbooks/node.yml -i remote

# Smoke-test a specific playbook inventory combination directly
uv run smoke-test --playbook playbooks/workstation.yml
```

The intended local workflow is `pre-commit`-first: the `pre-commit` hook
auto-runs Ruff plus basic file hygiene checks, the `pre-push` hook runs
`uv run typecheck` and `uv run ansible-check` when relevant files changed, and
the manual stage exposes `validate` and `smoke-test` through the same
`pre-commit` interface. Treat the direct `uv run lint`, `uv run typecheck`,
and `uv run ansible-check` commands as debugging fallbacks for cases where you
want to rerun one tool by itself or reproduce a CI failure more directly.

## Reference

【[uv](https://docs.astral.sh/uv/)】

【 [gantsign.oh-my-zsh](https://github.com/gantsign/ansible-role-oh-my-zsh) 】

【 [rvm.ruby](https://github.com/rvm/rvm1-ansible) 】
