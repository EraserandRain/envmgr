---
description: Run all code quality checks (Python + Ansible)
allowed-tools: ["Bash"]
---

# Run complete code quality checks for the envmgr project. This includes

1. Python code linting with ruff
2. Python type checking with mypy
3. Ansible code linting with ansible-lint

Execute: `uv run lint && uv run typecheck && uv run ansible-check`

If any checks fail, analyze the output and provide specific fixes for the issues found.
