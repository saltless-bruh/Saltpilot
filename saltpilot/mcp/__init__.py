"""Hermes MCP servers — the tool surface Hermes routes to (Main Proposal Section 2).

v1's tools *are* MCP servers Hermes calls; the clean class boundaries in the core modules are
these servers' interfaces, so there is no in-process -> MCP rewrite later. Planned servers and the
core they wrap:

    scope-MCP        -> saltpilot.scope.ScopeGate       resolve + gate host -> in-scope IP
    recon-MCP        -> saltpilot.recon.ReconRunner      Workbenches: nmap, httpx -> Finding[]
    graph-MCP        -> saltpilot.store.GraphStore       SQLite (WAL) persistence + retrieval
    cve_lookup-MCP   -> saltpilot.interpret.CveValidator local NVD/OSV validation

Registration with Hermes (`hermes` CLI lists the Saltpilot MCP servers) is Task 0.5 and is
verified live on the reference box — it needs a running Hermes install, so it is not exercised in
this container. The server wrappers land here as their underlying core lands.
"""
