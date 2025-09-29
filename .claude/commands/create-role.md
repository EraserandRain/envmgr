---
description: Create a new Ansible role for envmgr
argument-hint: [role_name] (e.g., my_tool, custom_app)
allowed-tools: ["Bash"]
---

# Create a new Ansible role using the envmgr template system

Arguments: $ARGUMENTS

Execute: `uv run create $ARGUMENTS`

This will:

1. Generate a new role directory structure from template
2. Create the necessary files (tasks, vars, etc.)
3. Set up the role for development

After creation, you'll need to:

1. Implement the role logic in `roles/$ARGUMENTS/tasks/`
2. Configure variables in `roles/$ARGUMENTS/vars/main.yml`
3. Add the role to `entry.yaml` with appropriate tags
4. Test the role with `/install-test`
