"""Saltpilot v1 thin slice — the Saltpilot-on-Hermes core loop.

This package is the Saltpilot *extension*: the security MCP servers and the skill logic that
Hermes loads and drives. Hermes owns orchestration; nothing here is a competing orchestrator
(Main Proposal Section 2, the one-orchestrator rule). The clean class boundaries in this package
are the MCP server interfaces, so there is no in-process -> MCP rewrite later.
"""

__version__ = "0.1.0"
