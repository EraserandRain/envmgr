---
description: Run Python code quality checks only
allowed-tools: ["Bash"]
---

# Run Python-specific code quality checks for the envmgr project

1. Run ruff linting: `uv run lint`
2. Run mypy type checking: `uv run typecheck`

If issues are found, provide specific recommendations to fix Python code quality problems including:

- Code formatting issues
- Import organization
- Type annotation problems
- Code style violations
