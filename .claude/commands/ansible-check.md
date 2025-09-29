---
description: Run Ansible code quality checks and linting
allowed-tools: ["Bash"]
---

# Run Ansible-specific code quality checks for the envmgr project

Execute: `uv run ansible-check`

This will check all Ansible roles and playbooks for:

- YAML syntax and formatting
- Ansible best practices
- Security issues
- Task naming conventions
- File structure compliance

If issues are found, provide specific fixes for:

- YAML formatting problems
- Missing newlines at end of files
- Trailing spaces
- Ansible rule violations
- Role structure improvements
