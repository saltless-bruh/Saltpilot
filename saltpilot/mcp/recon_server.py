"""recon-MCP — run the fixed v1 recon pipeline as a Hermes tool (Auto-Recon Section 4)."""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ..config import Engagement, load_engagement
from ..recon import build_recon
from ..store import GraphStore


def build_recon_server(engagement: Engagement, store: GraphStore, *, httpx_binary: str = "httpx") -> FastMCP:
    server = FastMCP("saltpilot-recon")

    @server.tool()
    def run_recon() -> dict:
        """Run recon (nmap discovery -> httpx web probe) on the engagement target.

        Persists findings and returns a coverage summary + finding count. Scope is enforced inside
        the pipeline (each target resolved+gated before any packet), so this tool cannot touch an
        out-of-scope asset.
        """
        result = build_recon(engagement, store, httpx_binary=httpx_binary).run()
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
    # httpx binary is configurable because the process PATH a launcher (e.g. Hermes) hands the
    # stdio server may not match the operator's shell — and `httpx` the name can be shadowed by the
    # unrelated Python httpx CLI. On the reference box the default `httpx` (PD httpx on PATH) is fine.
    httpx_binary = os.environ.get("SALTPILOT_HTTPX_BIN", "httpx")
    build_recon_server(engagement, store, httpx_binary=httpx_binary).run()


if __name__ == "__main__":  # pragma: no cover
    main()
