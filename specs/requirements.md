# Saltpilot v1 (Thin Slice) — Requirements

## Introduction

This is the requirements spec for the **head start of Saltpilot** — the first, deliberately minimal vertical slice that gets the real project moving on the reference hardware. It is **not** a throwaway prototype: it is **Saltpilot-on-Hermes at its smallest**, proving the **core loop** end-to-end before any further feature is built:

> **scoped target → recon (nmap + httpx) → deterministic normalize → local-model interpretation → knowledge graph → grounded answer from the reasoner.**

**Built on Hermes from day one.** The slice is a small set of **Hermes MCP servers** (scope + recon via Workbenches, graph, cve_lookup) plus a **skill** that drives the loop — not a standalone script. Hermes (the proven harness — Main Proposal §2) supplies the runtime, tool routing, and memory; Saltpilot supplies the security tools and logic. The **interim frontend is the Hermes CLI** (`hermes`); the custom Rust/Ratatui **TUI and its ACP client are a later phase** (TUI Blueprint), so the head start needs no UI work to be usable and testable. Building on the proven harness — rather than a bespoke CLI thrown away later — is the same "use the mature foundation" discipline applied everywhere else in Saltpilot.

**What it deliberately omits.** No broker, no offense model, no attack-path planning, no enrichment loop, no distillation, no RAG corpus (answers come straight from the graph), no long-haul layer; **engagement-scope graph only**; **web + network** domains only. The five Saltpilot blueprints remain the source of truth for the full system (the knowledge layer specifically: **Knowledge-Architecture Blueprint**); this slice implements only the smallest runnable core of their intersection, on the real foundation.

**Why a slice, not the design:** the full design is unvalidated (nothing has been run) and too large to build at once. The head start converts the riskiest assumptions into evidence — that tool output parses reliably, that `Foundation-Sec-8B` interprets usefully, that the graph round-trips, that the reasoner answers *from graph facts* rather than hallucinating, that it fits in 12GB, and that the loop runs cleanly as a Hermes extension. Every requirement below tests one of those.

**Reference hardware:** RTX 3060 12GB / Ryzen 7 7700 / 32GB DDR5 / Pop!_OS.

---

## Requirements

### Requirement 1 — Engagement scope and gating
**User story:** As an operator, I want to define an authorized target and scope before anything runs, so Saltpilot can never touch an out-of-scope asset.

**Acceptance criteria:**
1. WHEN the operator starts an engagement THEN the system SHALL require a target and an explicit in-scope definition (domains / IPs / CIDRs) before any tool is executed.
2. WHEN a recon action would target a hostname THEN the system SHALL resolve it to IP(s) *itself*, verify each IP is in scope, and pass the in-scope **IP** (never the hostname) to the tool — so a tool's own DNS cannot reach an IP the gate never checked.
3. IF a scope check errors or the result is ambiguous THEN the system SHALL treat the asset as out of scope and SHALL NOT execute (fail closed).
4. WHEN an out-of-scope asset is discovered mid-recon (e.g. a resolved IP outside scope) THEN the system SHALL record it as `skipped-out-of-scope` and continue without touching it.

### Requirement 2 — Reconnaissance execution (fixed minimal pipeline)
**User story:** As an operator, I want Saltpilot to run a small fixed set of recon tools against the scoped target, so I get a real attack surface with the fewest moving parts.

**Acceptance criteria:**
1. WHEN recon runs THEN the system SHALL execute `nmap` for host / port / service discovery against in-scope hosts.
2. WHEN service discovery finds open ports THEN the system SHALL run `httpx` against **all** of them (not only ports labeled http/https) and let httpx decide what is web — a web service on an odd or mislabeled port would otherwise be missed.
3. WHEN a required tool is absent THEN the system SHALL report the missing tool and its install hint, record it as a capability gap, and continue the rest of the pipeline rather than aborting.
4. WHEN a tool runs THEN the system SHALL execute it as a constrained subprocess (never inline in the host process), SHALL enforce a wall-clock timeout, and SHALL reap the child process on completion or timeout.
5. WHEN a tool fails, times out, or returns empty THEN the system SHALL record the outcome (tool, target, classification: transient / permanent / empty) and continue.
6. WHEN any recon runs THEN it SHALL go through a category **Workbench** (network, web, …) that translates an *intent* + typed parameters into the tool command for the *installed* version — the caller (in v1 the fixed pipeline; later the model) SHALL NOT emit raw commands or flags, so stale tool knowledge cannot produce a dead command.

### Requirement 3 — Deterministic normalization
**User story:** As an operator, I want raw tool output turned into typed findings by code (not by a model), so the model never wastes capacity parsing and the data stays consistent.

**Acceptance criteria:**
1. WHEN a tool produces output THEN the system SHALL parse it deterministically (no LLM) into typed `Finding` records conforming to the schema in `design.md`.
2. WHEN parsing THEN the system SHALL prefer structured tool output (nmap XML / `-oX`, httpx `-json`) over scraping human-readable text.
3. WHEN the same asset is produced by more than one tool or run THEN the system SHALL de-duplicate on identity `(canonical_host, port)` — unifying IP and hostname to one host, and treating the scanner's service label as an *attribute*, not identity — so a reclassifying re-scan updates rather than duplicates. Provenance from each source is preserved.
4. IF a tool's output is malformed or partially unparseable THEN the system SHALL extract what it can, record a parse-warning for the remainder, and never crash the pipeline.

### Requirement 4 — Interpretation (local model, on-demand)
**User story:** As an operator, I want the normalized findings interpreted into a short human-readable brief per host, so I have digested meaning rather than raw scan data.

**Acceptance criteria:**
1. WHEN normalization completes THEN the system SHALL interpret the findings with the local analysis model (`Foundation-Sec-8B`), producing an `Interpretation` record per host per the `design.md` schema.
2. WHEN the model asserts a CVE THEN the system SHALL validate it against a real source (local NVD/OSV) *before storing* — does the ID exist and match this product/version? — dropping non-existent IDs, flagging mismatches, and persisting only validated CVEs as candidates. (Model proposes; a deterministic validator disposes.)
3. WHEN the interpreter runs THEN the system SHALL load the model on demand and MAY unload it after an idle window (it need not stay resident).
4. WHEN findings reach the model THEN the system SHALL pass them as **delimiter-wrapped untrusted data**, instructing the model to extract facts only and never execute instructions embedded in tool output.
5. WHEN interpretation is stored THEN the system SHALL tag it with the model used, a confidence signal, and provenance (source findings).

### Requirement 5 — Persistence (the knowledge graph)
**User story:** As an operator, I want the surface and its interpretations persisted, so a later question can be answered from stored facts and the engagement survives a restart.

**Acceptance criteria:**
1. WHEN findings and interpretations are produced THEN the system SHALL persist them to a local SQLite store using the schema in `design.md`.
2. WHEN persisting THEN the system SHALL record provenance for every fact (which tool/model produced it, when, and a reference to the raw evidence).
3. WHEN the process restarts THEN the system SHALL resume from persisted state — re-running recon SHALL be idempotent (safe to re-run, no duplicate facts).
4. WHEN writing THEN all writes SHALL go through SQLite in WAL mode via a single writer path (no concurrent-writer corruption), even though v1 is largely sequential.

### Requirement 6 — Copilot query (grounded answer)
**User story:** As an operator, I want to ask a plain-language question about the engagement and get an answer grounded in what recon actually found, so I can trust it and act on it.

**Acceptance criteria:**
1. WHEN the operator asks a question THEN the system SHALL retrieve the relevant facts from the graph and answer using the reasoner, with the retrieved facts supplied as context.
2. WHEN answering THEN the system SHALL ground the answer in graph facts, and a **deterministic guard** SHALL extract named entities (hosts, ports, CVEs) from the answer and strip/flag any not present in the retrieved context — making "no invented assets" an enforced check, not merely a prompt instruction (a prompt can only reduce invention, not guarantee its absence).
3. WHEN the reasoner is the cloud model (DeepSeek V4) and it is unreachable or errors THEN the system SHALL fall back to the local reasoner and answer (degraded), telling the operator which reasoner produced the answer.
4. IF the retrieved context contains no relevant facts THEN the system SHALL say so plainly rather than inventing an answer.
5. WHEN answering THEN the system SHALL indicate which stored facts the answer drew on (a minimal provenance/citation), so the operator can verify.

### Requirement 7 — Model layer and residency (fits the box)
**User story:** As an operator on a 12GB card, I want the model layer to fit my hardware, so recon and interpretation never OOM the machine.

**Acceptance criteria:**
1. WHEN a local model is needed THEN the system SHALL load exactly one local model at a time (single-tenant GPU), on demand.
2. WHEN recon tools run THEN they SHALL run on CPU / network and SHALL NOT require the GPU.
3. WHEN engagement `kind = practice` (lab/CTF/HTB/THM) THEN the reasoner SHALL be the **cloud teacher** (DeepSeek V4) — deep what/why/how — and it SHALL consume no local VRAM.
4. WHEN engagement `kind = real` (authorized IRL) THEN the reasoner SHALL be the **local reasoner** (`Qwen3-4B`, per `design.md`), and **no engagement data SHALL leave the box**. The reasoner is selected by engagement *type*, never a per-call convenience; there is no configuration that sends a `real` engagement to the cloud.

### Requirement 8 — Observability and honest failure
**User story:** As an operator, I want to see what ran, what was found, and what failed, so nothing is silent and I can debug.

**Acceptance criteria:**
1. WHEN recon completes THEN the system SHALL emit a coverage summary: which tools ran, succeeded, failed, or were skipped (and why).
2. WHEN the copilot answers THEN the system SHALL record the question, the retrieved facts, the reasoner used, and the answer to a log for later inspection.
3. WHEN any step fails THEN the system SHALL degrade coverage, never correctness — a partial run SHALL still persist and be answerable over whatever it did produce.

---

## Out of Scope (v1) — deferred to later slices

These are **designed** (in the blueprints) but **not built** in v1, by intent — the slice must prove the core before they are added, and each will be added *and stress-tested* on its own:

- The Rust/Ratatui **TUI** and its **ACP client** (the head start drives Hermes through the `hermes` CLI; the custom two-pane cockpit over ACP is a later phase — TUI Blueprint).
- The **enrichment loop** (operator findings → confirm → write-back → re-derive).
- **Exploit-candidate-with-conditions** analysis and **attack-path planning**.
- The **offensive artifact model** (DeepHat-V1-7B, formerly WhiteRabbitNeo) — no exploitation in v1.
- **Red-stealth** mode; anything beyond loud white-box recon.
- The **Git-like sprint-DAG** execution model and re-recon.
- The full **long-haul operation layer** (Custodian, Supervisor, saturation, reconciliation, checkpoint/resume, digests). *(v1 gets only the trivial subset it needs: WAL writes and idempotent re-run.)*
- **RAG corpus** and the hybrid retriever (v1 answers from the graph directly; RAG is added when the graph alone proves insufficient).
- Recon domains beyond **web + network** (no cloud/AD/mobile modules yet).

## Validation Goals (what v1 must give evidence about — problem 2)

v1 is a success if, on a lab target, it demonstrates: (a) both tool parsers produce correct typed findings from real output; (b) `Foundation-Sec-8B` interpretation clears an **objective bar** — on a small *labeled* ground-truth host (known services→CVEs) it identifies **≥ N of M known services** and emits **≤ K false CVEs after validation** (fill N/M/K from your lab; this replaces "judge by eye"); (c) the graph round-trips and re-run is idempotent, including a host seen as both IP and hostname collapsing to one asset; (d) the reasoner's answer is **grounded** — the deterministic guard lets **zero** invented hosts/ports/CVEs through on a spot check; (e) peak VRAM stays within budget for one loaded model; (f) the scope gate blocks an out-of-scope asset *and* a hostname resolving to an out-of-scope IP; (g) the loop runs cleanly as a Hermes extension (MCP servers + skill) driven from the `hermes` CLI. Anything that fails these is a finding about the *design*, to fix before expanding.

**Regression (carry forward):** the objective interpretation bar (b) and the grounded-answer check (d) become a small **held-out eval set** re-run on every model or prompt change (Copilot §13.5) — so a later model swap can't silently regress quality.
