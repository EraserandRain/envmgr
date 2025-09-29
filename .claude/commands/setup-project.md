---
description: Setup envmgr project dependencies and environment
allowed-tools: ["Bash"]
---

# Setup the envmgr project by installing dependencies and configuring the environment

Execute: `uv run setup`

This will:

1. Sync Python dependencies with uv
2. Initialize the logs directory
3. Install required Ansible Galaxy roles
4. Prepare the project for use

Run this command when:

- First setting up the project
- After cloning the repository
- When dependencies are updated
- If you encounter missing dependency errors
