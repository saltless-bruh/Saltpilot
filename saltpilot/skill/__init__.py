"""The Saltpilot Hermes skill — sequences the core loop by calling the MCP servers.

Hermes is the orchestrator; this skill only *sequences* (define scope -> recon -> normalize ->
interpret -> persist -> answer), it does not drive its own agent loop (the one-orchestrator rule,
Main Proposal Section 2). The skill itself is `SKILL.md` (Hermes skill format: YAML frontmatter +
markdown body); it installs to `~/.hermes/skills/security/saltpilot-recon/` and `hermes skills
list` shows it enabled. Installation is Task 0.5, reproducible via `scripts/setup_hermes.sh`.
"""
