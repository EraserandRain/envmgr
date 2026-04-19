# Envmgr

`envmgr` is a tool for quick deployment to install and configure tools with ansible.

## Quick Start

### Dependencies

Envmgr requires Python 3.10 or later and the uv package.

Please install `uv` first 【[uv installation](https://docs.astral.sh/uv/getting-started/installation/)】.

### First-Time Setup

`uv run envmgr setup` is the required bootstrap step on a new machine. It initializes
`~/.envmgr/` and installs the Galaxy roles and collections that envmgr
playbooks expect. For contributor workflows, run `uv sync` separately when you
want to install or refresh the local Python environment and dev tools.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Bootstrap envmgr on this machine
uv run envmgr setup

# Verify the bootstrap completed successfully
uv run envmgr doctor
uv run envmgr doctor --json
uv run envmgr ping
uv run envmgr install -l
```

Run `uv run envmgr setup` before `uv run envmgr install`, `uv run envmgr ping`, `uv run validate`,
or `uv run smoke-test` on a fresh machine or a fresh `ENVMGR_HOME`. The command
is safe to re-run and does not overwrite existing runtime config files. `uv run
validate` now checks both `scripts/` and `tests/`, runs the split
`tests/test_*.py` unit modules, and `uv run smoke-test` runs only the
`tests.test_smoke` suite before the playbook `--list-tags` checks.

`uv run envmgr doctor` performs a read-only health check for the current runtime. It is
safe to run before or after setup when you want to inspect what is missing
under `~/.envmgr/`.
Use `uv run envmgr doctor --json` when you want a machine-readable report for scripts
or CI.
Use `uv run envmgr history` to inspect the most recent runtime subprocess records, or
`uv run envmgr history -n 5` to focus on the latest few commands.

### Host Settings

Runtime configuration is saved under `~/.envmgr/`. By default, `uv run envmgr setup`
creates:

- `~/.envmgr/config.toml`
- `~/.envmgr/inventory/default.yaml`
- `~/.envmgr/inventory/remote.yaml`
- `~/.envmgr/inventory/password.yaml`
- `~/.envmgr/log/`
- `~/.envmgr/cache/`

For `uv run envmgr` commands, envmgr now uses these runtime paths consistently:

- Ansible logs are written to `~/.envmgr/log/ansible.log`
- Runtime subprocess records are written to `~/.envmgr/log/runs/*.json`
- Galaxy roles are installed to `~/.envmgr/cache/galaxy/roles`
- Galaxy collections are installed to `~/.envmgr/cache/galaxy/collections`
- Temporary Ansible files use `~/.envmgr/cache/tmp`

Repository-local files still keep their original purpose:

- `roles/` stays the source of first-party envmgr roles in this repo
- `playbooks/` stays the source of scenario playbooks in this repo
- `scripts/commands/` holds the `envmgr` subcommand handlers and shared CLI helpers
- `scripts/services/` holds reusable runtime, install-planning, and doctor logic
- `ansible.cfg` remains repository metadata used by envmgr internals and project checks

`uv run envmgr ...` is the supported runtime command surface for envmgr. Development
helpers stay separate as dedicated commands like `uv run validate` or `uv run lint`. Direct `ansible-playbook` or
`ansible-galaxy` usage from the repository is not a supported interface.

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

> **Note:** `uv run envmgr install <tags>` now resolves the scenario playbook from the selected tags. If the tags are valid in more than one scenario, pass `--playbook playbooks/workstation.yml` or `--playbook playbooks/node.yml` explicitly.
> `uv run envmgr install all` uses the `playbook` value from `~/.envmgr/config.toml` by default.

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

Run `uv run envmgr setup` first on a new machine so the runtime inventory, Galaxy
dependencies, and cache directories already exist.

**Local execution (default):**

```bash
# List all available tags
uv run envmgr install -l

# Install specified tools
uv run envmgr install [tag1 tag2 ...]

# Install all roles in one scenario
uv run envmgr install all

# Examples:
uv run envmgr install init             # Apply the baseline host bootstrap bundle
uv run envmgr install zsh              # Install zsh with oh-my-zsh and aliases
uv run envmgr install kubeadm          # Install kubeadm on node targets
uv run envmgr install golang dotnet    # Install multiple tools (space-separated)
uv run envmgr install kubernetes_tools # Install kubectl, helm, crictl, CNI plugins
uv run envmgr install ai_tools         # Launch the interactive AI Tools Setup wizard in a TTY
uv run envmgr install ai_tools --codex # Install default AI tools and explicitly manage Codex CLI
uv run envmgr install ai_tools --no-rtk # RTK is enabled by default; use this to skip it

# Use an explicit scenario playbook for ambiguous tags or full-scenario runs
uv run envmgr install --playbook playbooks/workstation.yml zsh node ai_tools
uv run envmgr install --playbook playbooks/node.yml docker kubeadm

# Use a scenario-specific playbook for a common preset
uv run envmgr install --playbook playbooks/workstation.yml init zsh java node golang ruby dotnet cloud
uv run envmgr install --playbook playbooks/workstation.yml init docker kubernetes_tools minikube
uv run envmgr install --playbook playbooks/node.yml docker kubeadm monitoring

`playbooks/node.yml` installs shared node prerequisites on every cluster node,
then applies cluster management tools only on the `master` group.
```

**Remote execution:**

```bash
# Using SSH key authentication
uv run envmgr install -i remote zsh

# Use a scenario-specific playbook on remote hosts
uv run envmgr install -i remote --playbook playbooks/node.yml docker kubeadm

# Using password authentication (with vault)
uv run envmgr install -i password --playbook playbooks/node.yml --ask-vault-pass docker kubeadm

# List tags (inventory-independent)
uv run envmgr install -l

# Install multiple components on remote hosts
uv run envmgr install -i remote zsh docker kubernetes_tools
```

**Test connection:**

```bash
# Test local connection
uv run envmgr ping

# Inspect runtime health
uv run envmgr doctor
uv run envmgr doctor --json

# Test remote connection
uv run envmgr ping -i remote

# Test with password authentication
uv run envmgr ping -i password
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

`playbooks/node.yml` runs `docker` and `kubeadm` on all nodes, while
`kubernetes_tools` and `monitoring` are master-only.

##### Task-level Tags

Task-level tags execute specific configuration tasks:

- claude_code (configure Claude Code)
- codex (install or update Codex CLI explicitly)
- rtk (install or update RTK explicitly)
- hashicorp (install HashiCorp repository tooling)
- terraform (install Terraform)
- tf (alias for Terraform tasks)

You can use `uv run envmgr install -l` to see the complete list of available tags.

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

When you run `uv run envmgr install ai_tools` in a TTY without AI-tools flags, envmgr launches an `AI Tools Setup` wizard that:

- lets you choose Claude Code, Codex CLI, and/or RTK
- asks whether to enable Context7 integration
- explains the Context7 connection modes before you choose one
- shows a summary and asks for confirmation before installation starts
- can be cancelled at any time with `Ctrl+C`

You can also skip the wizard and drive the same choices with CLI flags:

```bash
uv run envmgr install ai_tools --codex
uv run envmgr install ai_tools --no-rtk
uv run envmgr install ai_tools --no-context7
uv run envmgr install ai_tools --codex --codex-context7-method remote
uv run envmgr install ai_tools --claude-code --codex --rtk --claude-context7-method local
```

If your Context7 setup needs an API key, export `CONTEXT7_API_KEY` before running `uv run envmgr install ...`.

RTK is enabled by default for `ai_tools` installs and is placed into `~/.local/bin`. When Claude Code is also selected, envmgr runs `rtk init --global --auto-patch`. When Codex CLI is also selected, envmgr runs `rtk init --global --codex`.

**Installation:**

```bash
# Install AI tools (requires node role as prerequisite)
uv run envmgr install node ai_tools

# Or install everything at once
uv run envmgr install init node ai_tools

# Install Claude Code, Codex, and RTK together
uv run envmgr install ai_tools --codex

# Install Codex only, without Context7
uv run envmgr install ai_tools --no-claude-code --codex --no-context7

# Install RTK only
uv run envmgr install rtk
```

### Development Commands

Run `uv sync` when you want to populate or refresh the local development
virtualenv. Run `uv run envmgr setup` before `uv run validate` or `uv run smoke-test`
on a fresh machine; those commands execute playbook checks that rely on the
runtime inventory and Galaxy content installed during bootstrap.

```bash
# Install or refresh the local dev environment
uv sync

# Create a new role
uv run create [role]

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
# drives `uv run envmgr install zsh` and `uv run envmgr install ai_tools --codex` from the
# master node against the full workstation group.

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
