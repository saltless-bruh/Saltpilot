"""scope-MCP — the fail-closed scope gate as a Hermes tool (Knowledge blueprint Section 9)."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ..config import Engagement, load_engagement
from ..scope import ScopeGate


def build_scope_server(engagement: Engagement) -> FastMCP:
    gate = ScopeGate(engagement.in_scope, engagement.out_of_scope)
    server = FastMCP("saltpilot-scope")

    @server.tool()
    def scope_check(asset: str) -> str:
        """Classify one asset against engagement scope.

        Returns 'in_scope', 'out_of_scope', or 'skip' (a deliberate carve-out). Any error or
        ambiguity resolves to 'out_of_scope' — the gate fails closed.
        """
        return gate.check(asset).value

    @server.tool()
    def resolve_and_gate(target: str) -> list[str]:
        """Resolve a target HERE and return only its in-scope IPs.

        Tools must be handed these IPs, never the hostname, so a tool's own DNS cannot reach an IP
        the gate never checked. Returns [] when nothing is authorized (fail closed).
        """
        return gate.resolve_and_gate(target)

    return server


def main() -> None:  # entrypoint Hermes launches over stdio
    engagement = load_engagement(os.environ.get("SALTPILOT_ENGAGEMENT", "engagement.toml"))
    build_scope_server(engagement).run()


if __name__ == "__main__":  # pragma: no cover
    main()
