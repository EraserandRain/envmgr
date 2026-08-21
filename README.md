# Envmgr

`envmgr` is a small Ansible-powered environment manager for repeatable
workstations and Kubernetes nodes. It ships one public runtime CLI,
`envmgr`, with packaged playbooks, roles, and Rich-friendly command output.

Use this README as the human landing page. Maintainers and coding agents should
use [AGENTS.md](AGENTS.md) for detailed contribution, CLI UX, testing,
docs-sync, and release contracts.

## Quick Start

Install from a GitHub Release with `uv` already on `PATH`:

```bash
curl -fsSL https://github.com/EraserandRain/envmgr/releases/latest/download/install.sh | bash
```

`envmgr setup` creates the runtime home, default inventories, log/cache
folders, Galaxy role and collection cache, and the setup-complete marker. It is
safe to rerun.

## Common Commands

| Command | Purpose |
| --- | --- |
| `envmgr setup` | Initialize runtime files and install Galaxy dependencies. |
| `envmgr install [tag ...]` | Apply role or task tags through a scenario playbook. |
| `envmgr install --dry-run [--json] [tag ...]` | Inspect the install plan without running Ansible. |
| `envmgr install -l` / `envmgr install --list-tags` | List built-in scenarios, role tags, and task tags. |
| `envmgr ping [-i alias]` | Run Ansible ping against an inventory alias. |
| `envmgr doctor [--json]` | Check runtime health without changing runtime files. |
| `envmgr history [--limit N] [--json]` | Show recent runtime subprocess records. |
| `envmgr self update [--version VERSION]` | Update an installer-managed GitHub Release install (latest if omitted). |
| `envmgr self uninstall [--yes]` | Remove the installer-managed tool and keep runtime data. |

Useful public options include `--playbook`, `--inventory`, `--ask-vault-pass`,
`--dry-run`, `--json`, `--limit`, `--version`, and `--yes`. Public help is
available with `-h` and `--help` at the root and subcommand levels.

Common examples:

```bash
# Local workstation tags
envmgr install init zsh
envmgr install golang dotnet
envmgr install docker kubernetes_tools minikube

# Remote or vault-backed inventory aliases
envmgr ping --inventory remote
envmgr install --inventory remote zsh
envmgr install -i password --ask-vault-pass zsh

# Install planning
envmgr install --dry-run zsh
envmgr install --dry-run --json zsh

# Health and history
envmgr doctor --json
envmgr history --limit 20
envmgr history --json

# Installer-managed lifecycle
envmgr self update
envmgr self update --version 0.1.0
envmgr self uninstall --yes
```

`envmgr self update` resolves the latest GitHub Release by default; pass
`--version` to pin a specific release. `envmgr self uninstall` prompts unless
`--yes` or `-y` is provided. Both commands are limited to `install.sh`-managed
GitHub Release installs recorded in `~/.envmgr/install.toml`.

## Shell Environment

Workstation roles write default shell environment snippets under
`~/.config/envmgr/profile.d/`. The `init_core` and `zsh` roles install thin
loaders in common shell profiles so these snippets are sourced without keeping
large `export` blocks in `~/.zshrc`.

User-owned environment files go under `~/.config/envmgr/user/profile.d/*.sh`.
User-owned zsh-only files, such as private aliases or prompt overrides, go under
`~/.config/envmgr/user/zsh.d/*.zsh`. envmgr creates these directories but does
not manage their contents.

## Scenarios And Tags

### Built-in Scenarios

The `--playbook` option chooses the scenario before tags select features inside
that scenario. The scenario defines the Ansible playbook topology: target
inventory groups, play order, role order, and scenario-level vars.

| Scenario | Use it for |
| --- | --- |
| `workstation` | Local workstation setup: shell, runtimes, Docker/minikube, Kubernetes tools, cloud tools, and AI tools. |
| `node` | Kubernetes node/master setup: shared node prerequisites plus master-only Kubernetes tooling and monitoring. |

Playbook resolution essentials:

- `workstation` and `node` select packaged built-in playbooks.
- Path-like values are absolute paths, values containing path separators, or
  values ending in `.yml` or `.yaml`.
- Path-like `--playbook` values resolve as caller filesystem paths and do not
  fall back to packaged playbooks.
- `envmgr install all` uses the default `playbook` from
  `~/.envmgr/config.toml` unless `--playbook` is explicit.
- Specific tags may infer a built-in scenario only when they match exactly one
  scenario.

```bash
envmgr install --playbook workstation init zsh node
envmgr install --playbook node docker kubeadm monitoring
envmgr install --playbook node all
envmgr install --playbook ./custom-playbook.yml zsh
```

Role-level tags include `ai_tools`, `cloud`, `docker`, `dotnet`, `golang`,
`init`, `java`, `kubeadm`, `kubernetes_tools`, `minikube`, `monitoring`, `node`,
`ruby`, and `zsh`. Task-level tags include `claude_code`, `codex`, `rtk`,
`github_cli`, `hashicorp`, `terraform`, and `tf`.

## AI Tools

The `ai_tools` role depends on `node`. It installs Claude Code plus RTK by
default; Codex CLI is opt-in through the `codex` task tag or `all`. AI tools are
selected by task tags, and the durable choices (which tools to manage plus the
Context7 connection) live in `~/.envmgr/config.toml` under `[ai_tools]`.

The first interactive `envmgr install ai_tools` (or `envmgr install all`) run
launches an AI Tools Setup wizard once and writes your choices into `[ai_tools]`.
Later runs use that configuration as the source of truth without prompting. Use
the `envmgr config` command to review or change the saved configuration:

```bash
envmgr install ai_tools            # first run: wizard + persist; later runs reuse config
envmgr install codex               # install only Codex CLI via the codex task tag
envmgr config show                 # print the saved AI tools config
envmgr config set ai_tools.manage_codex true
envmgr config set ai_tools.enable_context7 false
```

Export `CONTEXT7_API_KEY` first if your Context7 setup needs an API key.

## Reference

- [uv](https://docs.astral.sh/uv/)
- [Runtime details](docs/runtime.md)
- [Development guide](docs/development.md)
- [Release guide](docs/release.md)
- [AGENTS.md](AGENTS.md)
- [GitHub Releases](https://github.com/EraserandRain/envmgr/releases)
