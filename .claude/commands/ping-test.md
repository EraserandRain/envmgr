---
description: Test connection to envmgr hosts
argument-hint: [inventory_file] (optional, defaults to default.yaml)
allowed-tools: ["Bash"]
---

# Test connection to envmgr hosts using Ansible ping

Arguments (optional): $ARGUMENTS

Execute connection test:

- If no arguments: `uv run ping` (uses default inventory)
- If inventory specified: `uv run ping -i inventory/$ARGUMENTS`

This will:

1. Test connectivity to all configured hosts
2. Verify Ansible can reach the targets
3. Confirm authentication is working
4. Provide troubleshooting if connection fails

Available inventory files:

- default.yaml (local execution)
- remote.yaml (SSH key auth)
- password.yaml (password auth with vault)
