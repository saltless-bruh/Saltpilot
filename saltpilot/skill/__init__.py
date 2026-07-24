"""The Saltpilot Hermes skill — sequences the core loop by calling the MCP servers.

Hermes is the orchestrator; this skill only *sequences* (define scope -> recon -> normalize ->
interpret -> persist -> answer), it does not drive its own agent loop (the one-orchestrator rule,
Main Proposal Section 2). The skill manifest + registration are Task 0.5, verified live on the
reference box against a running Hermes.
"""
