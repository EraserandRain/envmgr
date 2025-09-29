# Envmgr

`envmgr` is a tool for quick deployment to install and configure tools with ansible.

## Quick Start

### Dependencies

Envmgr requires Python 3.10 or later and the uv package.

Please install `uv` first 【[uv installation](https://docs.astral.sh/uv/getting-started/installation/)】.

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Setup envmgr
uv run setup            
```

### Host Settings

Host configuration is saved in `inventory/default.yaml`. By default, it's configured for local execution.

**Default Configuration (Local):**

```yaml
all:
  children:
    node:
      children:
        master:
          hosts:
            localhost:
              ansible_connection: local
              ansible_python_interpreter: "{{ ansible_playbook_python }}"
```

> **Note:** The default configuration now installs tools under the current user instead of requiring root privileges for better security and user experience.

**For Remote Hosts:**

1. **SSH Key Authentication (Recommended):**
   - Copy `inventory/remote.yaml.example` to `inventory/remote.yaml`
   - Modify the host IPs and usernames accordingly
   - Ensure SSH keys are properly configured

2. **Password Authentication (If necessary):**
   - Copy `inventory/password.yaml.example` to `inventory/password.yaml`
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

**Local execution (default):**

```bash
# List all available tags (both role-level and task-level)
uv run install -l

# Install specified tools
uv run install [tag1 tag2 ...] 

# Install all roles
uv run install all    

# Examples:
uv run install init             # Setup base environment and directories
uv run install zsh              # Install zsh with oh-my-zsh and aliases
uv run install github_cli       # Install GitHub CLI (task-level)
uv run install golang dotnet    # Install multiple tools (space-separated)
uv run install kubernetes_tools # Install kubectl, helm, crictl, CNI plugins
uv run install ai_tools         # Install AI development tools (Claude Code, Codex)
```

**Remote execution:**

```bash
# Using SSH key authentication
uv run install -i inventory/remote.yaml init

# Using password authentication (with vault)
uv run install -i inventory/password.yaml --ask-vault-pass init

# List tags with specific inventory
uv run install -i inventory/remote.yaml -l

# Install multiple components on remote hosts
uv run install -i inventory/remote.yaml zsh,docker,kubernetes_tools
```

**Test connection:**

```bash
# Test local connection
uv run ping

# Test remote connection
uv run ping -i inventory/remote.yaml

# Test with password authentication
uv run ping -i inventory/password.yaml
```

#### Available Tags

##### Role-level Tags

Role-level tags install complete functional modules:

- zsh
- node   (latest version)
- golang (default version: 1.20.4)
- ruby   (default version: 3.0.5)
- docker
- minikube (latest)
- kubeadm,kubelet (1.31.9-1.1)
- kubernetes_tools
- cloud
- init
- monitoring
- ai_tools

##### Task-level Tags

Task-level tags execute specific configuration tasks:

- github_cli (install GitHub CLI)
- git (configure git)
- sync_time (synchronize system time)

You can use `uv run install -l` to see the complete list of available tags.

Supported Setup Items:

- zsh
- node   (latest version)
- golang (default version: 1.20.4)
- ruby   (default version: 3.0.5)
- docker
- minikube (latest)
- kubeadm,kubelet (1.31.9-1.1)
- kubernetes_tools:
  - kubectl (default version: 1.31)
  - helm
- cloud
  - awscli
- ai_tools:
  - Claude Code (Anthropic's AI development CLI)
  - Codex (OpenAI's coding assistant CLI)
  - Context7 MCP integration for both tools

#### AI Tools Configuration

The AI tools role installs Claude Code and Codex CLI tools with optional Context7 MCP integration for enhanced functionality.

**Prerequisites:**

- Node.js (will be installed via the `node` role if not present)
- Volta package manager (will be installed via the `node` role)

**Optional Configuration:**
Create a `config.local.yml` file in the project root to customize AI tools settings:

```yaml
# config.local.yml (optional)
ai_tools_local_config:
  claude_code:
    install_context7_mcp: true
  codex:
    install_context7_mcp: true
  context7_api_key: "your-context7-api-key-here"  # Optional, for enhanced features
```

**Installation:**

```bash
# Install AI tools (requires node role as prerequisite)
uv run install node ai_tools

# Or install everything at once
uv run install init node ai_tools
```

### Development Commands

```bash
# Create a new role
uv run create [role]

# Run Python code linting (ruff)
uv run lint

# Run Ansible linting
uv run ansible-check

# Run type checking
uv run typecheck
```

## Reference

【[uv](https://docs.astral.sh/uv/)】

【 [gantsign.oh-my-zsh](https://github.com/gantsign/ansible-role-oh-my-zsh) 】

【 [rvm.ruby](https://github.com/rvm/rvm1-ansible) 】
