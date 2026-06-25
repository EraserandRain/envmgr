# Runtime Guide

This page keeps runtime details out of the README landing page. Use it when you
need exact paths, inventory behavior, CLI UX contracts, or role/tag reference
details for installed `envmgr ...` commands.

## Runtime Home

Runtime configuration defaults to `~/.envmgr/`. Set `ENVMGR_HOME` to point at a
different runtime home for isolated testing or alternate host profiles.

`envmgr setup` creates these default files and directories:

- `~/.envmgr/config.toml`
- `~/.envmgr/inventory/default.yaml`
- `~/.envmgr/inventory/remote.yaml`
- `~/.envmgr/inventory/password.yaml`
- `~/.envmgr/log/`
- `~/.envmgr/cache/`

Runtime commands use these paths consistently:

- Ansible logs: `~/.envmgr/log/ansible.log`
- Runtime subprocess records: `~/.envmgr/log/runs/*.json`
- Galaxy roles: `~/.envmgr/cache/galaxy/roles`
- Galaxy collections: `~/.envmgr/cache/galaxy/collections`
- Temporary Ansible files: `~/.envmgr/cache/tmp`
- Installer state for self-management: `~/.envmgr/install.toml`

Repository-local files keep their source-control purpose. `roles/` and
`playbooks/` are the first-party source assets, `ansible.cfg` is repository
metadata used by envmgr internals and checks, and Python modules under
`src/envmgr/` are implementation details.

## Shell Environment Drop-ins

Workstation roles use XDG-style shell environment drop-ins instead of appending
large tool-specific blocks directly to `~/.zshrc`, `~/.bashrc`, or `~/.profile`.
Unless `XDG_CONFIG_HOME` is set, envmgr uses these paths:

- envmgr-managed profile snippets: `~/.config/envmgr/profile.d/*.sh`
- envmgr-managed zsh snippets: `~/.config/envmgr/zsh/*.zsh`
- user-owned profile snippets: `~/.config/envmgr/user/profile.d/*.sh`
- user-owned zsh snippets: `~/.config/envmgr/user/zsh.d/*.zsh`

The `init_core` role installs a guarded profile loader in `~/.profile`,
`~/.bashrc`, `~/.zprofile`, and `~/.zshrc`. The `zsh` role installs a zsh-only
loader for `~/.config/envmgr/zsh/*.zsh` and
`~/.config/envmgr/user/zsh.d/*.zsh` after oh-my-zsh writes its base
configuration.

Runtime roles write only envmgr-managed files under `profile.d`. Users can add
or remove private files under `user/profile.d` and `user/zsh.d`; envmgr creates
those directories but does not manage their contents. Do not store secrets in
managed envmgr files or committed role templates. Use semantic file names such
as `java.sh` or `node-volta.sh`; add numeric prefixes only when files in the
same directory need a strict order.

## Default Config

The default `~/.envmgr/config.toml` points runtime commands at an inventory
alias and a default scenario:

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

Commands that accept `-i` or `--inventory` use aliases from this config. Alias
targets must stay under the runtime inventory directory; envmgr does not fall
back to repository-local inventory files or `./.ansible` caches.

Store sensitive values in `~/.envmgr/inventory/group_vars/all/vault.yml` and
encrypt them with `ansible-vault`.

## Default Inventory

The default local inventory supports both workstation and node scenario groups:

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

For remote hosts, edit `remote.yaml` for SSH key authentication or
`password.yaml` for password-backed access with vault-protected secrets.

## Scenario Resolution

Use `--playbook` when tags are available in more than one built-in scenario or
when you want to run every role in one scenario. Scenario names such as
`workstation` and `node` select packaged playbooks. Path-like values, including
absolute paths, values with path separators, and `.yml` or `.yaml` values, are
caller filesystem paths and do not fall back to packaged playbooks.

`envmgr install all` uses the default `playbook` from `~/.envmgr/config.toml`
unless `--playbook` is explicit. Specific tags may infer a built-in scenario
only when they map to exactly one built-in playbook.

## Install Dry Run

Use `envmgr install --dry-run <tag ...>` to inspect the resolved install plan
without starting Ansible. The dry run still builds the same execution playbook
plan, including temporary scoped playbooks, then cleans temporary files before
exiting. Human output uses Rich and shows the source playbook, execution
playbook when different, inventory alias and path, selected tags or all-tags
status, effective `--ask-vault-pass`, AI tools choices when applicable, and the
final `ansible-playbook` command.

Use `envmgr install --dry-run --json <tag ...>` for plain machine-readable JSON.
The JSON report includes selected tags, source and execution playbook paths,
whether the execution playbook was temporary, inventory label and path,
effective `ask_vault_pass`, AI tools options and extra-vars when applicable,
and `command_argv`.

## Doctor And History

`envmgr doctor` is read-only. Its hard command check covers the Ansible runtime commands:
`ansible`, `ansible-playbook`, and `ansible-galaxy`; `uv` is checked only for
installer-managed self-management. If installer state records a missing or
non-executable `uv`, doctor reports a self-management warning and still exits
0 unless another check fails. Failing checks make `envmgr doctor` and
`envmgr doctor --json` exit non-zero.

Use `envmgr doctor --json` for machine-readable reports. Use `envmgr history`
for recent runtime subprocess records, `envmgr history --limit 5` or
`envmgr history -n 5` for a shorter window, and `envmgr history --json` for
plain JSON output.

## CLI UX Contracts

- Public `envmgr` supports `-h` and `--help` at root and subcommand levels.
- `envmgr --version` prints `envmgr <version>`.
- Shell completion stays disabled; generated completion install options are
  rejected unless the project changes that decision intentionally.
- Runtime human output uses Rich for help, headings, warnings, summaries,
  prompts, and the human `envmgr history` table.
- JSON output and live external subprocess stdout/stderr stay plain.
- Expected runtime failures should print actionable guidance to stderr and use
  shell-friendly exit codes such as `0`, `1`, `2`, and `130`.
- Installed artifacts expose only `envmgr`; checkout-only helpers run through
  `uv run ...` from the repository.

Direct `ansible-playbook` or `ansible-galaxy` usage from the repository is not
a public interface.

## Role And Tag Reference

Role-level tags install complete modules:

- `ai_tools` - Claude Code, optional Codex CLI, RTK, and Context7 wiring.
- `cloud` - HashiCorp repository tooling and Terraform tasks.
- `docker`
- `dotnet` - default .NET version `8.0`.
- `golang` - default Go version `1.20.4`.
- `init` - baseline workstation bootstrap.
- `java` - default Java version `8`.
- `kubeadm` - Kubernetes packages, auto-discovered latest stable via `dl.k8s.io/release/stable.txt`.
- `kubernetes_tools` - kubectl, cri-tools, kubernetes-cni (auto-discovered latest stable), Helm, and conntrack.
- `minikube` - latest package from the configured source.
- `monitoring`
- `node` - latest Node.js LTS through Volta.
- `ruby` - default Ruby version `3.0.5`.
- `zsh`

Task-level tags include `claude_code`, `codex`, `rtk`, `github_cli`,
`hashicorp`, `terraform`, and `tf`.

Use `envmgr install -l` or `envmgr install --list-tags` for the generated,
current list of scenarios, role tags, and task tags.
