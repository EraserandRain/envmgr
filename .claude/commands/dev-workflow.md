---
description: Run quick development workflow for envmgr
allowed-tools: ["Bash"]
---

# Execute a complete development workflow for envmgr

1. **Setup check**: Ensure project dependencies are ready
2. **Connection test**: Verify host connectivity
3. **Code quality**: Run all quality checks
4. **List available tools**: Show what can be installed

Execute workflow:

```bash
echo "=== Envmgr Development Workflow ==="
echo "1. Testing connection..."
uv run ping

echo "2. Running quality checks..."
uv run lint && uv run typecheck && uv run ansible-check

echo "3. Available installation tags:"
uv run install -l

echo "=== Workflow Complete ==="
```

Use this for:

- Daily development startup
- Pre-commit validation
- Project health check
- New team member onboarding
