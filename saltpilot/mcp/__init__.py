"""Hermes MCP servers — the tool surface Hermes routes to (Main Proposal Section 2).

v1's tools *are* MCP servers Hermes calls; the clean class boundaries in the core modules are
these servers' interfaces, so there is no in-process -> MCP rewrite later (design.md: MCP servers
exist from day one, they are explicitly NOT a deferred stub).

Servers and the core they wrap:

    scope-MCP   -> saltpilot.scope.ScopeGate       scope_check · resolve_and_gate  (fail closed)
    recon-MCP   -> saltpilot.recon.ReconRunner      run_recon (nmap -> normalize -> persist)
    graph-MCP   -> saltpilot.store.GraphStore       graph_query · graph_findings
    copilot-MCP -> saltpilot.query.CopilotQuery     ask (grounded, guarded answer)

Each `build_*_server(...)` returns a FastMCP instance bound to an engagement/store; each module's
`main()` reads SALTPILOT_ENGAGEMENT / SALTPILOT_DB from the environment and runs the server over
stdio (how Hermes launches an MCP server). These are exposed as console entrypoints
(`saltpilot-{scope,graph,recon}-mcp`). Registration WITH Hermes (`hermes mcp add`, then
`hermes mcp list`) is Task 0.5 — done and reproducible via `scripts/setup_hermes.sh`.

`cve_lookup`-MCP arrives with Milestone 5; `scout` is out of v1 scope (Knowledge blueprint Section 9).
"""

from .copilot_server import build_copilot_server
from .graph_server import build_graph_server
from .recon_server import build_recon_server
from .scope_server import build_scope_server

__all__ = ["build_copilot_server", "build_graph_server", "build_recon_server", "build_scope_server"]
