"""recon-MCP — run the fixed v1 recon pipeline as a Hermes tool (Auto-Recon Section 4)."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ..config import Engagement, load_engagement
from ..recon import build_network_recon
from ..store import GraphStore


def build_recon_server(engagement: Engagement, store: GraphStore) -> FastMCP:
    server = FastMCP("saltpilot-recon")

    @server.tool()
    def run_recon() -> dict:
        """Run network recon (nmap) on the engagement target, persist findings, return coverage.

        Scope is enforced inside the pipeline (each target resolved+gated before any packet), so
        this tool cannot touch an out-of-scope asset. Returns a coverage summary + finding count.
        """
        result = build_network_recon(engagement, store).run()
        return {
            "coverage": result.coverage_summary(),
            "findings": len(result.findings),
            "persisted": result.persisted,
        }

    return server


def main() -> None:  # entrypoint Hermes launches over stdio
    engagement = load_engagement(os.environ.get("SALTPILOT_ENGAGEMENT", "engagement.toml"))
    store = GraphStore(os.environ.get("SALTPILOT_DB", "engagement.sqlite"))
    store.init_schema()
    build_recon_server(engagement, store).run()


if __name__ == "__main__":  # pragma: no cover
    main()
