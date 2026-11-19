"""graph-MCP — engagement-scoped reads over the SQLite graph (Knowledge blueprint Section 9).

v1 exposes simple reads (graph-primary retrieval is graph-first by design); the copilot's
`facts_for_query` retrieval arrives with Milestone 6, and `graph_write` for model-asserted facts
gains its verification gate in later slices. Recon's writes go through the pipeline (ReconRunner),
not a free-write tool, so nothing here lets a caller inject unvalidated facts.
"""

from __future__ import annotations

import os

from mcp.server.fastmcp import FastMCP

from ..store import GraphStore


def query_assets(store: GraphStore, engagement_id: str, kind: str | None = None) -> list[dict]:
    with store.connect() as con:
        if kind:
            rows = con.execute(
                "SELECT id, canonical_host, kind, port, url_path, service, scope_status "
                "FROM asset WHERE engagement_id = ? AND kind = ? ORDER BY canonical_host, port",
                (engagement_id, kind),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id, canonical_host, kind, port, url_path, service, scope_status "
                "FROM asset WHERE engagement_id = ? ORDER BY canonical_host, port",
                (engagement_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def query_findings(store: GraphStore, engagement_id: str) -> list[dict]:
    with store.connect() as con:
        rows = con.execute(
            "SELECT id, asset_id, kind, product, version, service, port, source_tool, "
            "confidence, observed_at FROM finding WHERE engagement_id = ? ORDER BY port",
            (engagement_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def build_graph_server(store: GraphStore) -> FastMCP:
    server = FastMCP("saltpilot-graph")

    @server.tool()
    def graph_query(engagement_id: str, kind: str | None = None) -> list[dict]:
        """Read engagement-scoped assets, optionally filtered by kind (host/service/web_endpoint)."""
        return query_assets(store, engagement_id, kind)

    @server.tool()
    def graph_findings(engagement_id: str) -> list[dict]:
        """List engagement-scoped findings (services, web endpoints, tech)."""
        return query_findings(store, engagement_id)

    return server


def main() -> None:  # entrypoint Hermes launches over stdio
    store = GraphStore(os.environ.get("SALTPILOT_DB", "engagement.sqlite"))
    store.init_schema()
    build_graph_server(store).run()


if __name__ == "__main__":  # pragma: no cover
    main()
