---
name: saltpilot-recon
description: Run authorized reconnaissance with Saltpilot — set scope, run recon (nmap discovery then httpx web probing), and answer questions grounded strictly in the findings graph. Use for any authorized pentest/bug-bounty/CTF recon on an in-scope target.
platforms: [linux, macos]
---

# Saltpilot — authorized recon

This skill sequences the Saltpilot core loop over its MCP tools. Saltpilot is for **authorized**
offensive-security work only (sanctioned pentest, bug bounty, CTF, lab). Scope is the one control
that must never be bypassed: it fails closed.

The tools come from three Saltpilot MCP servers (`saltpilot-scope`, `saltpilot-graph`,
`saltpilot-recon`). The engagement (target + scope) is fixed by the servers' configuration
(`SALTPILOT_ENGAGEMENT` / `SALTPILOT_DB`); you do not choose the target here — you work the
engagement you were given.

## Workflow

1. **Confirm scope before anything active.** Before discussing or probing any asset, call
   `scope_check(asset)`. Treat anything that is not `in_scope` as off-limits. To turn a hostname
   into targets, call `resolve_and_gate(target)` and use only the returned IPs — never a hostname
   the tool would resolve itself.
2. **Run recon.** Call `run_recon()`. It runs nmap service discovery and then httpx web probing on
   the in-scope target, normalizes and de-duplicates the results, validates any model-asserted
   CVEs, and persists everything to the engagement graph. It returns a coverage summary and a
   finding count. It is idempotent — re-running refreshes, it does not duplicate.
3. **Read the surface from the graph.** Use `graph_query(engagement_id, kind=…)` for assets
   (`host` / `service` / `web_endpoint`) and `graph_findings(engagement_id)` for findings.
4. **Answer only from the graph.** When the operator asks a question, answer strictly from what the
   graph tools return. Never name a host, port, or CVE that is not present in that data. If the
   graph has nothing relevant, say so plainly rather than inventing anything.

## Rules

- **Authorized use only.** Do not probe, or advise probing, anything out of scope.
- **Recon, not exploitation.** This skill maps the surface; it never exploits. Exploitation is the
  operator's decision, made outside this skill.
- **Grounded, never invented.** Every asset/port/CVE you report must trace to a graph tool result.
