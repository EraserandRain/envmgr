# Envmgr

`envmgr` is a tool for quick deployment to install and configure tools with ansible.

## Quick Start

### Dependencies

Envmgr requires Python 3.10 or later and the uv package.

Please install `uv` first 【[uv installation](https://docs.astral.sh/uv/getting-started/installation/)】.

### First-Time Setup

`uv run setup` is the required bootstrap step on a new machine. It syncs Python
dependencies, initializes `~/.envmgr/`, and installs the Galaxy roles and
collections that envmgr playbooks expect.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Bootstrap envmgr on this machine
uv run setup

# Verify the bootstrap completed successfully
uv run ping
uv run install -l
```

Run `uv run setup` before `uv run install`, `uv run ping`, `uv run validate`,
or `uv run smoke-test` on a fresh machine or a fresh `ENVMGR_HOME`. The command
is safe to re-run and does not overwrite existing runtime config files.

### Host Settings

Runtime configuration is saved under `~/.envmgr/`. By default, `uv run setup`
creates:

- `~/.envmgr/config.toml`
- `~/.envmgr/inventory/default.yaml`
- `~/.envmgr/inventory/remote.yaml`
- `~/.envmgr/inventory/password.yaml`
- `~/.envmgr/log/`
- `~/.envmgr/cache/`

For `uv run` commands, envmgr now uses these runtime paths consistently:

- Ansible logs are written to `~/.envmgr/log/ansible.log`
- Galaxy roles are installed to `~/.envmgr/cache/galaxy/roles`
- Galaxy collections are installed to `~/.envmgr/cache/galaxy/collections`
- Temporary Ansible files use `~/.envmgr/cache/tmp`

Repository-local files still keep their original purpose:

- `roles/` stays the source of first-party envmgr roles in this repo
- `playbooks/` stays the source of scenario playbooks in this repo
- `ansible.cfg` remains repository metadata used by envmgr internals and project checks

`uv run ...` is the supported command surface for envmgr. Direct `ansible-playbook` or `ansible-galaxy` usage from the repository is not a supported interface.

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

> **Note:** `uv run install <tags>` now resolves the scenario playbook from the selected tags. If the tags are valid in more than one scenario, pass `--playbook playbooks/workstation.yml` or `--playbook playbooks/node.yml` explicitly.
> `uv run install all` uses the `playbook` value from `~/.envmgr/config.toml` by default.

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

Run `uv run setup` first on a new machine so the runtime inventory, Galaxy
dependencies, and cache directories already exist.

**Local execution (default):**

```bash
# List all available tags
uv run install -l

# Install specified tools
uv run install [tag1 tag2 ...] 

# Install all roles in one scenario
uv run install all

# Examples:
uv run install zsh              # Install zsh with oh-my-zsh and aliases
uv run install kubeadm          # Install kubeadm on node targets
uv run install github_cli       # Install GitHub CLI (task-level)
uv run install golang dotnet    # Install multiple tools (space-separated)
uv run install kubernetes_tools # Install kubectl, helm, crictl, CNI plugins
uv run install ai_tools         # Launch the interactive AI Tools Setup wizard in a TTY
uv run install ai_tools --codex # Install default AI tools and explicitly manage Codex CLI

# Use an explicit scenario playbook for ambiguous tags or full-scenario runs
uv run install --playbook playbooks/workstation.yml zsh node ai_tools
uv run install --playbook playbooks/node.yml init docker kubeadm

# Use a scenario-specific playbook for a common preset
uv run install --playbook playbooks/workstation.yml init zsh java node golang ruby dotnet cloud
uv run install --playbook playbooks/workstation.yml init docker kubernetes_tools minikube
```

**Remote execution:**

```bash
# Using SSH key authentication
uv run install -i remote zsh

# Use a scenario-specific playbook on remote hosts
uv run install -i remote --playbook playbooks/node.yml init docker kubeadm

# Using password authentication (with vault)
uv run install -i password --playbook playbooks/node.yml --ask-vault-pass init docker kubeadm

# List tags (inventory-independent)
uv run install -l

# Install multiple components on remote hosts
uv run install -i remote zsh docker kubernetes_tools
```

**Test connection:**

```bash
# Test local connection
uv run ping

# Test remote connection
uv run ping -i remote

# Test with password authentication
uv run ping -i password
```

#### Available Tags

##### Role-level Tags

Role-level tags install complete functional modules:

- ai_tools
- cloud
- docker
- dotnet
- golang
- init
- java
- kubeadm
- kubernetes_tools
- minikube
- monitoring
- node
- ruby   (default version: 3.0.5)
- zsh

##### Task-level Tags

Task-level tags execute specific configuration tasks:

- claude_code (configure Claude Code)
- codex (install or update Codex CLI explicitly)
- git (configure git)
- github_cli (install GitHub CLI)
- hashicorp (install HashiCorp repository tooling)
- sync_time (synchronize system time)
- terraform (install Terraform)
- tf (alias for Terraform tasks)

You can use `uv run install -l` to see the complete list of available tags.

Supported Setup Items:

- ai_tools:
  - Claude Code (Anthropic's AI development CLI)
  - Context7 MCP integration for Claude Code
- codex:
  - Codex (OpenAI's coding assistant CLI)
  - Context7 MCP integration for Codex
- cloud
  - terraform
- zsh
- node   (latest version)
- golang (default version: 1.20.4)
- ruby   (default version: 3.0.5)
- docker
- dotnet (default version: 8.0)
- java (default version: 8)
- init
- minikube (latest)
- kubeadm (1.31.9-1.1)
- kubernetes_tools:
  - kubectl (default version: 1.31)
  - helm
- monitoring

#### AI Tools Configuration

The AI tools role installs Claude Code and Codex CLI tools with optional Context7 MCP integration for enhanced functionality.

**Prerequisites:**

- Node.js (will be installed via the `node` role if not present)
- Volta package manager (will be installed via the `node` role)

When you run `uv run install ai_tools` in a TTY without AI-tools flags, envmgr launches an `AI Tools Setup` wizard that:

- lets you choose Claude Code and/or Codex CLI
- asks whether to enable Context7 integration
- explains the Context7 connection modes before you choose one
- shows a summary and asks for confirmation before installation starts
- can be cancelled at any time with `Ctrl+C`

You can also skip the wizard and drive the same choices with CLI flags:

```bash
uv run install ai_tools --codex
uv run install ai_tools --no-context7
uv run install ai_tools --codex --codex-context7-method remote
uv run install ai_tools --claude-code --codex --claude-context7-method local
```

If your Context7 setup needs an API key, export `CONTEXT7_API_KEY` before running `uv run install ...`.

**Installation:**

```bash
# Install AI tools (requires node role as prerequisite)
uv run install node ai_tools

# Or install everything at once
uv run install init node ai_tools

# Install Claude Code and Codex together
uv run install ai_tools --codex

# Install Codex only, without Context7
uv run install ai_tools --no-claude-code --codex --no-context7
```

### Development Commands

Run `uv run setup` before `uv run validate` or `uv run smoke-test` on a fresh
machine. Those commands execute playbook checks that rely on the runtime
inventory and Galaxy content installed during bootstrap.

```bash
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

# Run Python code linting (ruff)
uv run lint

# Run Ansible linting
uv run ansible-check

# Run type checking
uv run typecheck

# Run the combined validation suite
uv run validate

# Run the lightweight smoke test suite
# (includes a CI-safe multi-node topology check with 1 master + 2 workers)
uv run smoke-test

# GitHub Actions also runs a containerized 1 master + 2 workers e2e that
# drives `uv run install zsh` and `uv run install ai_tools --codex` from the
# master node against the full workstation group.

# Validate specific playbooks
uv run validate --playbook playbooks/workstation.yml
uv run validate --playbook playbooks/node.yml -i remote

# Smoke-test a specific playbook inventory combination
uv run smoke-test --playbook playbooks/workstation.yml
```

## Reference

【[uv](https://docs.astral.sh/uv/)】

【 [gantsign.oh-my-zsh](https://github.com/gantsign/ansible-role-oh-my-zsh) 】

【 [rvm.ruby](https://github.com/rvm/rvm1-ansible) 】
