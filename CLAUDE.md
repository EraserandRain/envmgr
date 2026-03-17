## Project Overview

Envmgr is an Ansible-based environment management tool for quick deployment and configuration of development tools and environments. The project uses Python with uv for dependency management and provides a CLI interface for managing Ansible playbooks.

## Common Commands

### Setup and Dependencies
```bash
# Setup envmgr and install dependencies
uv run setup

# Sync dependencies
uv sync
```

### Installation and Configuration
```bash
# List all available tags
uv run install -l

# Install specific tools (local, auto-resolves scenario when unambiguous)
uv run install [tag1 tag2 ...]
uv run install zsh              # Zsh with oh-my-zsh
uv run install kubeadm          # Node scenario
uv run install kubernetes_tools # Requires --playbook when target is ambiguous

# Install all roles in a specific scenario
uv run install --playbook playbooks/workstation.yml all

# Remote installation
uv run install -i inventory/remote.yaml [tags]
uv run install -i inventory/password.yaml --ask-vault-pass [tags]

# Test connections
uv run ping
uv run ping -i inventory/remote.yaml
```

### Development Commands
```bash
# Code quality checks
uv run lint          # Python linting with ruff
uv run typecheck     # Type checking with mypy
uv run ansible-check # Ansible linting
uv run validate      # Combined validation suite
uv run smoke-test    # Lightweight integration checks

# Create new role
uv run create [role_name]
```

## Code Architecture

### Core Structure
- **`scripts/main.py`**: Main CLI implementation with all command handlers
- **`playbooks/`**: Scenario playbooks defining workstation and node role order
- **`roles/`**: Ansible roles for different tools and configurations
- **`inventory/`**: Host configuration files (local and remote)
- **`vars/global.yml`**: Global variables shared across roles

### Python CLI Architecture
The project uses a unified CLI approach in `scripts/main.py` with separate functions for each command:
- `install()`: Main installation command with tag support
- `create()`: Role generation from templates
- `ping()`: Connection testing
- `setup()`: Project initialization
- `lint()`, `ansible_lint()`, `typecheck()`: Code quality tools

### Ansible Architecture
- **Tag System**: Two-level tagging (role-level and task-level tags)
  - Role tags: Complete functional modules (zsh, docker, kubernetes_tools)
  - Task tags: Specific configuration tasks (github_cli, git, sync_time)
- **Inventory Management**: Supports local, remote SSH key, and password authentication
- **Role Structure**: Standard Ansible role layout with tasks, handlers, vars, and templates

### Key Configuration Files
- **`pyproject.toml`**: Python project configuration, dependencies, and tool settings
- **`ansible.cfg`**: Ansible configuration with optimized settings
- **`requirements.yaml`**: External Ansible Galaxy roles

### Role Organization
Roles are organized by technology:
- **init**: Base environment setup
- **zsh**: Shell configuration with aliases and oh-my-zsh
- **docker/minikube**: Container platforms
- **kubeadm/kubernetes_tools**: Kubernetes ecosystem
- **cloud**: AWS CLI and cloud tools
- **monitoring**: Observability stack
- **node/golang/java/ruby/dotnet**: Language runtimes

## Development Notes

### Adding New Roles
1. Use `uv run create [role_name]` to generate from template
2. Update the appropriate playbook under `playbooks/` to include the new role with appropriate tags
3. Configure role-specific variables in `roles/[role_name]/vars/main.yml`

### Tag Management
Tags are automatically discovered from role metadata in `roles/*/meta/envmgr.yml`.

### Inventory Configuration
- Local execution: `inventory/default.yaml` (default)
- Remote SSH: `inventory/remote.yaml` (copy from example)
- Password auth: `inventory/password.yaml` with ansible-vault encryption
