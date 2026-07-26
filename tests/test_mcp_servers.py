"""Milestone 0/2 — the Saltpilot MCP servers exist and wrap the tested core (design.md: MCP
servers exist from day one). Registration WITH Hermes is Task 0.5 (reference box); here we prove
the servers construct, expose the right tools, and round-trip real data."""

from __future__ import annotations

import asyncio

from saltpilot.findings import Finding
from saltpilot.mcp import build_graph_server, build_recon_server, build_scope_server
from saltpilot.mcp.graph_server import query_assets, query_findings
from saltpilot.store import GraphStore


def _tool_names(server) -> set[str]:
    return {t.name for t in asyncio.run(server.list_tools())}


def _service_finding(engagement_id: str, host="10.10.10.7", port=80, product="nginx") -> Finding:
    return Finding(
        engagement_id=engagement_id,
        asset_host=host,
        port=port,
        service="http",
        product=product,
        version="1.25",
        kind="service",
        detail={"protocol": "tcp"},
        source_tool="nmap",
        raw_ref="sha1:deadbeef#10.10.10.7:80",
        confidence=0.9,
        scope_status="in_scope",
        observed_at="2026-07-24T00:00:00+00:00",
    )


def test_scope_server_exposes_tools(make_engagement, tmp_path):
    server = build_scope_server(make_engagement(tmp_path))
    assert server.name == "saltpilot-scope"
    assert _tool_names(server) == {"scope_check", "resolve_and_gate"}


def test_recon_server_exposes_tool(make_engagement, tmp_path):
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    server = build_recon_server(eng, store)
    assert server.name == "saltpilot-recon"
    assert _tool_names(server) == {"run_recon"}


def test_recon_server_accepts_httpx_binary(make_engagement, tmp_path):
    # The httpx binary is configurable so a launcher's sanitized PATH (or a shadowed `httpx` name)
    # cannot break web probing — the recon server reads SALTPILOT_HTTPX_BIN.
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    server = build_recon_server(eng, store, httpx_binary="/opt/pd-bin/httpx")
    assert _tool_names(server) == {"run_recon"}


def test_graph_server_exposes_tools_and_round_trips(make_engagement, tmp_path):
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    store.persist_findings(eng, [_service_finding(eng.id)])

    server = build_graph_server(store)
    assert server.name == "saltpilot-graph"
    assert _tool_names(server) == {"graph_query", "graph_findings"}

    services = query_assets(store, eng.id, kind="service")
    assert any(a["canonical_host"] == "10.10.10.7" and a["port"] == 80 for a in services)
    findings = query_findings(store, eng.id)
    assert findings and findings[0]["product"] == "nginx"


def test_graph_query_filters_by_kind(make_engagement, tmp_path):
    eng = make_engagement(tmp_path)
    store = GraphStore(str(tmp_path / "e.sqlite"))
    store.init_schema()
    store.persist_findings(eng, [_service_finding(eng.id)])
    assert len(query_assets(store, eng.id, kind="host")) == 1
    assert len(query_assets(store, eng.id, kind="service")) == 1
