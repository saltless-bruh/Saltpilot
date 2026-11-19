# Saltpilot — v1 thin slice

Saltpilot is a local-first program for **authorized** offensive-security work. It pairs an
autonomous **Auto-Recon** engine (breadth) with a human-driven **Copilot** (depth), built as an
extension of the [Hermes](https://github.com/NousResearch) agent harness — *a mod, not a fork*.
The full design lives in the five blueprints (Main Proposal, Auto-Recon, Copilot,
Knowledge-Architecture, TUI).

This repository is the **v1 thin slice**: the smallest thing that exercises every layer of the
real architecture end-to-end, so what breaks here tells us what is wrong with the design before
we scale it.

## The core loop v1 proves

```
scoped target -> recon (nmap + httpx behind Workbenches) -> deterministic normalize
             -> local-model interpretation (CVE-validated) -> SQLite graph
             -> grounded answer from the reasoner (guarded)
```

Built as a set of **Hermes MCP servers + a skill**, driven from the `hermes` CLI. No custom TUI,
no broker, no offense model, no exploitation — those are later slices (see `specs/tasks.md`).

## Layout

```
saltpilot/            the Python package (the MCP servers + skill logic live here)
  config.py           engagement.toml -> typed Engagement            [Milestone 0]
  scope.py            ScopeGate — the one fail-closed control         [Milestone 1]
  store.py            GraphStore — SQLite (WAL) graph                 [Milestone 0/2]
  mcp/                Hermes MCP-server wrappers over the core         (wired in 0.5)
  skill/              the Hermes skill that sequences the loop         (wired in 0.5)
tests/                unit + integration tests; fixtures/ holds real tool output
engagement.example.toml
```

## Build discipline

The build follows `tasks.md` in order; **each milestone ends in a checkpoint and we do not pass a
checkpoint until it is green.** That is the point — build-then-learn, not build-on-faith. Five
"slice-blocking" correctness fixes are called out in the task list (CVE fabrication, host
identity/idempotency, the scope-resolution hole, httpx/nmap coupling, the grounding guard); each
lands in the task that introduces its component.

## Running the tests

```
python -m pip install -e '.[dev]'
python -m pytest
```

The deterministic spine (scope gate, parsers, normalize/dedup, CVE validator, ground guard) is
pure Python and fully unit-tested with no network, model, or GPU. The live checkpoints (Hermes
wiring, Ollama interpretation, VRAM budget, recon against a lab host) run on the reference box:
RTX 3060 12GB / Ryzen 7 7700 / 32GB / Pop!_OS.

## Reference hardware

RTX 3060 12GB · Ryzen 7 7700 · 32GB DDR5 · Pop!_OS. One local model resident at a time
(single-tenant GPU); scanners run on CPU/network and never touch the GPU.
