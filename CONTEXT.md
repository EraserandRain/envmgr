# Envmgr domain glossary

Domain terms used by architecture reviews and design work. Keep this file
current when a new concept is named or a fuzzy term is sharpened.

- **Install** — one `envmgr install` operation: apply role/task tags through a
  scenario playbook, optionally with AI-tools choices and vault prompting.
- **Install plan** — the full resolution for one Install: selected tags,
  source/execution playbooks, inventory alias and path, default ask-vault
  state, and AI-tools defaults.
- **Scenario playbook** — a built-in playbook topology (`workstation`, `node`)
  that Install selects or generates an execution playbook from.
- **Execution playbook** — the playbook actually run by Install; for scoped
  (non-`all`) installs it is a temporary generated file that Install cleans up.
- **Role tags / task tags** — the two-level tag vocabulary discovered from role
  metadata; Install validates selections against it.
- **AI-tools choices** — the resolution of whether Claude Code, Codex CLI, and
  RTK are installed, from defaults or interactive prompts.
