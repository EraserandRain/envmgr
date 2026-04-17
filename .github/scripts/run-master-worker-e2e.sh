#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
compose_file="$repo_root/.github/e2e/docker-compose.yml"
workspace_dir="/home/envmgr/envmgr"
inventory_alias="ci_cluster"
envmgr_home="/home/envmgr/.envmgr"
inventory_file="$envmgr_home/inventory/ci-cluster.yaml"
master_path="/home/envmgr/.local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
tmp_dir=$(mktemp -d)

cleanup() {
  docker compose -f "$compose_file" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

dc() {
  docker compose -f "$compose_file" "$@"
}

run_in_master() {
  local command=$1
  # Mirror envmgr's runtime Ansible environment so direct ansible invocations
  # resolve repository roles plus galaxy-installed content inside ~/.envmgr.
  dc exec -T master sudo -u envmgr -H bash -lc "
    export PATH='$master_path'
    export ANSIBLE_CONFIG='$workspace_dir/ansible.cfg'
    export ANSIBLE_FORCE_COLOR=true
    export ANSIBLE_LOG_PATH='$envmgr_home/log/ansible.log'
    export ANSIBLE_LOCAL_TEMP='$envmgr_home/cache/tmp'
    export ANSIBLE_ROLES_PATH='$workspace_dir/roles:$envmgr_home/cache/galaxy/roles'
    export ANSIBLE_COLLECTIONS_PATH='$envmgr_home/cache/galaxy/collections'
    cd '$workspace_dir'
    $command
  "
}

quote_master_args() {
  local arg
  local quoted_arg
  local quoted_args=()

  for arg in "$@"; do
    printf -v quoted_arg '%q' "$arg"
    quoted_args+=("$quoted_arg")
  done

  printf '%s' "${quoted_args[*]}"
}

build_uv_ansible_command() {
  quote_master_args "uv" "run" "$@"
}

run_uv_ansible_in_master() {
  run_in_master "$(build_uv_ansible_command "$@")"
}

printf 'Generating SSH key for the test cluster...\n'
ssh-keygen -t ed25519 -N '' -f "$tmp_dir/id_ed25519" >/dev/null
export E2E_AUTHORIZED_KEYS
E2E_AUTHORIZED_KEYS=$(tr -d '\n' < "$tmp_dir/id_ed25519.pub")

printf 'Sanity-checking Docker Compose configuration...\n'
bash "$repo_root/.github/scripts/check-e2e-compose.sh"

printf 'Starting master and worker containers...\n'
dc up -d --build

printf 'Copying repository into the master container...\n'
tar \
  --exclude=.git \
  --exclude=.codex \
  --exclude=.mypy_cache \
  --exclude=.pytest_cache \
  --exclude=.ruff_cache \
  --exclude=.venv \
  -C "$repo_root" \
  -cf - . | dc exec -T master bash -lc "rm -rf '$workspace_dir' && mkdir -p '$workspace_dir' && tar -xf - -C '$workspace_dir' && chown -R envmgr:envmgr '$workspace_dir'"

printf 'Installing the cluster SSH key into the master container...\n'
dc exec -T master bash -lc 'install -d -m 0700 -o envmgr -g envmgr /home/envmgr/.ssh'
docker cp "$tmp_dir/id_ed25519" "$(dc ps -q master):/home/envmgr/.ssh/id_ed25519"
dc exec -T master bash -lc 'chown envmgr:envmgr /home/envmgr/.ssh/id_ed25519 && chmod 0600 /home/envmgr/.ssh/id_ed25519'

printf 'Installing uv inside the master container...\n'
run_in_master "curl -LsSf https://astral.sh/uv/install.sh | sh"

printf 'Waiting for worker SSH endpoints to come online...\n'
for target in worker1 worker2; do
  for attempt in $(seq 1 30); do
    if run_in_master "ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -i ~/.ssh/id_ed25519 envmgr@${target} true" >/dev/null 2>&1; then
      break
    fi
    if [[ "$attempt" -eq 30 ]]; then
      printf 'Timed out waiting for %s SSH readiness.\n' "$target" >&2
      exit 1
    fi
    sleep 2
  done
done

printf 'Bootstrapping envmgr on the master container...\n'
run_in_master "uv run setup"

printf 'Writing the CI inventory and config...\n'
run_in_master "cat > ~/.envmgr/config.toml <<'CONFIG'
[default]
inventory = \"${inventory_alias}\"
playbook = \"workstation\"
ask_vault_pass = false

[inventory]
default = \"inventory/default.yaml\"
remote = \"inventory/remote.yaml\"
password = \"inventory/password.yaml\"
${inventory_alias} = \"inventory/ci-cluster.yaml\"
CONFIG"

run_in_master "cat > ~/.envmgr/inventory/ci-cluster.yaml <<'INVENTORY'
all:
  children:
    workstation:
      hosts:
        master-ci:
          ansible_connection: local
          ansible_python_interpreter: /usr/bin/python3
        worker-ci-1:
          ansible_host: worker1
          ansible_user: envmgr
          ansible_ssh_private_key_file: /home/envmgr/.ssh/id_ed25519
          ansible_ssh_common_args: \"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null\"
          ansible_python_interpreter: /usr/bin/python3
        worker-ci-2:
          ansible_host: worker2
          ansible_user: envmgr
          ansible_ssh_private_key_file: /home/envmgr/.ssh/id_ed25519
          ansible_ssh_common_args: \"-o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null\"
          ansible_python_interpreter: /usr/bin/python3
    node:
      children:
        master:
          hosts:
            master-ci:
        worker:
          hosts:
            worker-ci-1:
            worker-ci-2:
INVENTORY"

printf 'Checking reachability from the master to all cluster nodes...\n'
run_in_master "uv run ping -i ${inventory_alias}"

printf 'Confirming the workstation playbook sees every target node...\n'
workstation_list_hosts_command=$(build_uv_ansible_command ansible-playbook -i "$inventory_file" playbooks/workstation.yml --list-hosts)
run_in_master "$workstation_list_hosts_command | tee /tmp/workstation-hosts.txt"
run_in_master "grep -q 'master-ci' /tmp/workstation-hosts.txt && grep -q 'worker-ci-1' /tmp/workstation-hosts.txt && grep -q 'worker-ci-2' /tmp/workstation-hosts.txt"

printf 'Installing AI tools from the master across the workstation group...\n'
run_in_master "uv run install -i ${inventory_alias} ai_tools --codex --no-context7"

printf 'Verifying Node.js, Claude Code, and Codex CLI on every workstation node...\n'
run_uv_ansible_in_master ansible -i "$inventory_file" workstation -m shell -a 'test -x "$HOME/.volta/bin/node" && test -x "$HOME/.volta/bin/claude" && test -x "$HOME/.volta/bin/codex" && "$HOME/.volta/bin/node" --version >/dev/null 2>&1 && "$HOME/.volta/bin/claude" --version >/dev/null 2>&1 && "$HOME/.volta/bin/codex" --version >/dev/null 2>&1 && test ! -e "$HOME/.local/bin/context7-codex"'

printf 'Installing zsh from the master across the workstation group...\n'
run_in_master "uv run install -i ${inventory_alias} zsh"

printf 'Verifying zsh and oh-my-zsh assets on every workstation node...\n'
run_uv_ansible_in_master ansible -i "$inventory_file" workstation -m shell -a 'test -d "$HOME/.oh-my-zsh" && test -d "$HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions" && test -f "$HOME/.zshrc" && grep -q "ANSIBLE MANAGED CUSTOM BLOCK" "$HOME/.zshrc"'

printf 'Multi-node master-to-workers e2e completed successfully.\n'
