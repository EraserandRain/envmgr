---
description: Test envmgr installation with specific tags
argument-hint: [tags] (e.g., ai_tools, claude_code, node)
allowed-tools: ["Bash"]
---

# Test envmgr installation functionality with the specified tags

Arguments: $ARGUMENTS

Execute installation test: `uv run install $ARGUMENTS`

This will:

1. Run the installation with the specified tags
2. Verify the installation completed successfully
3. Check if the installed tools are accessible
4. Provide troubleshooting if installation fails

Available tags:

- Role tags: ai_tools, node, zsh, docker, kubernetes_tools, etc.
- Task tags: claude_code, codex, github_cli, git, etc.

Example usage:

- `/install-test ai_tools` - Test AI tools installation
- `/install-test claude_code` - Test only Claude Code installation
