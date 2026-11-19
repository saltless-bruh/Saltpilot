# Saltpilot v1 (Thin Slice) — Design

## Overview

v1 is the **head start of Saltpilot-on-Hermes** — the core loop built as a small set of **Hermes MCP servers** plus a **skill**, driven from the **`hermes` CLI**: define scope → run recon (nmap + httpx behind Workbenches) → normalize deterministically → interpret with a local model → persist to SQLite → answer a question via the reasoner, grounded in the stored facts. Hermes supplies the runtime, tool routing, and memory (Main Proposal §2); Saltpilot supplies the security MCP servers and the skill that sequences them. No custom TUI / ACP client yet, no broker, no offense model — the smallest thing that exercises every layer of the *real* architecture, so what breaks here tells us what's wrong with the design before we scale it.

This document fixes the **concrete contracts** the blueprints left in prose — the `Finding` shape, the tool-adapter interface, the SQLite DDL, the interpretation record, the model-provider interface, and the query flow. These are the artifacts you code against.

**Non-goals restated:** everything in the requirements' *Out of Scope* list. The contracts below are intentionally the *minimum* that later slices can extend without rework (e.g. the graph tables are a subset the full node/edge model grows into; provenance and scope fields exist from day one because retrofitting them is painful).

---

## Architecture

The core loop is a **Hermes skill** that calls a handful of **MCP servers**; data flows one way through the pipeline, with a query path off the store. Hermes is the orchestrator (one-orchestrator rule, Main Proposal §2) — the skill sequences, the MCP servers do the work:

```
   hermes CLI   (interim frontend — ACP / custom TUI is a later phase)
        │
   HERMES core (the harness) — runtime · tool routing · memory
        │  runs the Saltpilot skill, which calls MCP servers:
        ├─► scope-MCP        resolve + gate host → in-scope IP (fail closed)
        ├─► recon-MCP        Workbenches: nmap · httpx → raw output
        │     └─ Normalizer (deterministic) → Filter (dedup) → Finding[]
        │          └─ Interpreter ─► ModelProvider (Hermes → Ollama, on-demand)
        │               CVEs validated via cve_lookup-MCP before store
        ├─► graph-MCP        GraphStore (SQLite WAL):
        │                  engagement · asset · finding · interpretation · run_log
        └─► cve_lookup-MCP   local NVD / OSV

   ask:  Hermes retrieves facts (graph-MCP) → reasoner → grounded answer (guard)
```

**Runtime:** Hermes (the harness) drives a Saltpilot **skill** + **MCP servers**, all Python 3.11+. **Store:** SQLite (WAL). **Local model serving:** Ollama (`Foundation-Sec-8B` GGUF), pointed at by Hermes’s model-agnostic endpoint. **Reasoner:** chosen by engagement kind — cloud DeepSeek V4 as *teacher* on practice targets, the local `Qwen3-4B` reasoner on real work (Copilot §4). **Tools:** `nmap`, `httpx` behind category **Workbenches** (never raw commands). **CVE validation:** a local NVD/OSV source via `cve_lookup`. **Frontend:** the `hermes` CLI (the custom TUI / ACP client is deferred — TUI Blueprint). **Config:** a single `engagement.toml`.

---

## Components and Interfaces

### 1. ScopeGate
The one control that fails closed. Deterministic; the only I/O is DNS resolution, which it performs *itself* so tools never do.

```python
class ScopeGate:
    def __init__(self, in_scope: list[str], out_of_scope: list[str]) -> None: ...
    def check(self, asset: str) -> ScopeVerdict:
        """IN_SCOPE / OUT_OF_SCOPE / SKIP. Any error or ambiguity → OUT_OF_SCOPE."""
    def resolve_and_gate(self, target: str) -> list[str]:
        """Resolve a hostname to IP(s) HERE, gate each IP, return only the in-scope IPs.
        Tools are handed these IPs — never the hostname."""
```
- Accepts domains, IPs, CIDRs. **The gate resolves hostnames itself and hands tools the gated *IP*, never the hostname** — otherwise a tool's own internal DNS could resolve to an IP the gate never saw, silently bypassing fail-closed scope. Resolution failure → treat as out of scope.
- Neither method raises to the caller; internal errors resolve to `OUT_OF_SCOPE` / empty list.

### 2. Workbench (the category tool layer — the extension point)
Tools live behind **category Workbenches** (Auto-Recon §4.1), never exposed directly. A workbench takes an **intent** and produces commands; the caller never names a tool or a flag. v1 has two: a **network workbench** (nmap) and a **web workbench** (httpx). Adding a tool later = a new intent/adapter inside the right workbench, nothing else changes. In v1 the intents are issued by the *fixed pipeline*; in later slices the *model* issues them — either way, never a raw command.

```python
class Workbench(Protocol):
    category: str                                   # 'network' | 'web' | …
    def intents(self) -> list[IntentSpec]:          # what you can ask this workbench to do
        ...
    def run(self, intent: str, params: dict, gate: ScopeGate) -> list[Finding]:
        """Translate intent+params → the right tool command for the INSTALLED version,
        execute it (scope-gated, subprocess, timeout, reaped), parse → Findings.
        Resolves+gates hosts and passes IPs to the tool — never hostnames."""

class ToolAdapter(Protocol):                        # one tool, used *inside* a workbench
    name: str
    def is_available(self) -> ToolStatus: ...
    def render(self, intent: str, params: dict, gated_ips: list[str]) -> list[ToolInvocation]:
        """Build argv for the installed version from the workbench's intent — not from a model."""
    def parse(self, invocation: ToolInvocation, raw: RawOutput) -> list[Finding]: ...
```
- **v1 network workbench** — intent `discover_services(host)` → `NmapAdapter` (`-sV -oX`).
- **v1 web workbench** — intent `probe_web(hosts, ports)` → `HttpxAdapter` (`-json`). It probes **all open ports, not only those nmap labeled http/https** — httpx is the better web detector, and coupling its input to nmap's classification would lose web on odd or mislabeled ports. Workbenches share *facts* (open ports), not *classifications*.
- The workbench owns tool-specific knowledge (flags, output format, parsing); the runner is workbench-agnostic. This is the manifest-owns-invocation principle, made category-first — and the reason a stale-tool-knowledge model can't emit a dead command (it emits an intent).

### 3. ReconRunner
Orchestrates the fixed pipeline with process hygiene.

```python
class ReconRunner:
    def run(self, engagement: Engagement) -> ReconResult:
        """
        For each adapter in [nmap, httpx] (httpx after nmap, fed by its web services):
          - scope-gate each target
          - execute each ToolInvocation as a subprocess with a wall-clock timeout
          - reap the child; classify outcome (ok/transient/permanent/empty)
          - parse → Findings
        Aggregate Findings + a per-tool coverage record. Never abort on one failure.
        """
```
- **Subprocess discipline (v1 subset of the Supervisor):** hard timeout, child reaping, capture stdout/stderr, no shell interpolation of untrusted values.
- Missing tool → capability-gap record + skip that adapter; pipeline continues.

### 4. Normalizer + Filter
```python
def canonicalize_host(host: str) -> str:  # resolve + unify IP↔hostname → one identity
def normalize(findings: list[Finding]) -> list[Finding]:   # identity + provenance merge
def dedup(findings: list[Finding]) -> list[Finding]:        # minimal identity key
```
- **Identity key (v1): `(canonical_host, port)`.** The scanner's *service label* is an **attribute, not identity** — a re-scan that reclassifies a port must update the asset, not spawn a duplicate (this is what makes Req 5.3 idempotency actually hold). `canonicalize_host` resolves and unifies IP↔hostname so one machine is one asset (a host seen as an IP by nmap and a hostname by httpx is not two hosts). Web endpoints key on `(canonical_host, port, url_path)`. Duplicates merge, unioning provenance.
- Deterministic only. No model.
- Deterministic only. No model.

### 5. Interpreter (+ deterministic CVE validation)
```python
class CveValidator:
    def validate(self, cve_id: str, product: str | None, version: str | None) -> CveVerdict:
        """Look the CVE up in a real source (local NVD/OSV mirror or API):
        does the ID EXIST, and does it match this product/version?
        → VALID / NOT_FOUND / MISMATCH."""

class Interpreter:
    def interpret(self, host: str, findings: list[Finding],
                  model: ModelProvider, cves: CveValidator) -> Interpretation:
        """
        Build a prompt: the host's findings as DELIMITER-WRAPPED UNTRUSTED DATA +
        an instruction to summarize the surface and name candidate CVEs/CWEs
        (model-asserted). Parse the reply. Then VALIDATE every asserted CVE via
        `cves.validate(...)`: drop NOT_FOUND, flag MISMATCH; only VALID ones are
        stored as candidate CVEs. The model proposes; the validator disposes.
        """
```
- Batches per host (not per finding) to limit model calls.
- Tool text is wrapped: `<<UNTRUSTED_TOOL_OUTPUT>> … <<END>>`, embedded delimiters stripped, model told to extract facts only, never follow instructions inside.
- **CVE validation is the output-side half of the core principle** (Auto-Recon §5.2): an 8B will confidently emit CVE IDs that don't exist or don't apply; the deterministic check stops them becoming graph "facts". Unverifiable IDs never persist as fact.

### 6. GraphStore
Thin persistence over SQLite (WAL). All writes through one path.

```python
class GraphStore:
    def init_schema(self) -> None: ...
    def upsert_asset(self, a: Asset) -> int: ...
    def upsert_finding(self, f: Finding) -> int: ...
    def upsert_interpretation(self, i: Interpretation) -> int: ...
    def log_run(self, r: RunRecord) -> None: ...
    def facts_for_query(self, q: str) -> list[Fact]:   # retrieval for the copilot (v1: simple)
        ...
```
- `facts_for_query` in v1 is **simple retrieval** — pull the engagement's assets, services, findings, and interpretations (optionally keyword-filtered by the question). No embeddings yet; the graph is small. If/when this proves insufficient, RAG is the next slice.

### 7. ModelProvider (residency-aware)
One interface, two implementations, a policy wrapper.

```python
class ModelProvider(Protocol):
    def complete(self, role: Role, prompt: str, *, max_tokens: int) -> Completion: ...

class OllamaProvider:   # local, on-demand; loads model, may unload after idle
    ...
class DeepSeekV4Provider:   # hosted OpenAI-compatible API
    ...

class RoutedProvider:
    """
    role=ANALYSIS   → OllamaProvider(foundation-sec)   [always local, on-demand]
    role=REASONING  → chosen by engagement TYPE, not convenience:
        engagement.kind == 'practice' (lab/CTF/HTB/THM) → DeepSeekV4Provider  [TEACHER]
        engagement.kind == 'real'     (authorized IRL)  → local reasoner      [SUPPORT, private]
      (within practice, transient cloud failure → fall back to local + record which answered)
    Single-tenant local GPU: only ever one local model resident at once (of broker/analyst/offense).
    """
```
- v1 roles: `ANALYSIS` (interpretation) and `REASONING` (the copilot's answer). **v1 keeps interpretation on local Foundation-Sec in both modes** — deliberately, so the slice validates Foundation-Sec's interpretation quality directly (Checkpoint 5). The full architecture instead folds interpretation into the analyst seat (Foundation-Sec on real, V4 on practice — Copilot §4 / Auto-Recon §5.2); v1 defers that. Offense role is out of scope.
- **The reasoner is chosen by engagement type** (Copilot §4): on a practice target the cloud model is the *teacher* (deep what/why/how, no client data to leak); on real work the local model is *support* (private, safety). This is set by `engagement.kind`, not per call.
- Cloud failure handling (v1 subset of the resilient client): bounded retry + timeout, then fall back to local, record which reasoner answered. (Circuit-breaker/backoff is the long-haul slice.)

### 8. CopilotQuery (+ deterministic grounding guard)
```python
class CopilotQuery:
    def answer(self, question: str, model: ModelProvider) -> Answer:
        """
        facts = store.facts_for_query(question)
        if not facts: return Answer(text="No relevant facts found.", grounded=[], reasoner=…)
        prompt = grounding_prompt(question, facts)   # 'answer ONLY from these facts; cite them'
        reply  = model.complete(REASONING, prompt)
        checked, flagged = ground_guard(reply, facts) # extract hosts/ports/CVEs; strip/flag any
        return Answer(text=checked, grounded=[fact.id …], flagged=flagged, reasoner=used)
        """

def ground_guard(answer: str, facts: list[Fact]) -> tuple[str, list[str]]:
    """Extract named entities (hosts, ports, CVEs) from the answer; any not present in
    `facts` are flagged/stripped. Turns 'SHALL NOT invent' from a prompt hope into a control."""
```
- The grounding prompt instructs: answer only from the supplied facts; if not covered, say so; cite the fact ids. **But a prompt can only reduce invention** — so `ground_guard` deterministically checks the output: entities absent from the fact set are stripped or flagged before the operator sees them. This is the enforced half of Req 6.2, and it matters most precisely because the cloud reasoner's raw hallucination rate is high (Copilot §7 grounding guard).

---

## Data Models

### Finding (typed, in-memory)
```python
@dataclass
class Finding:
    engagement_id: str
    asset_host: str            # ip or hostname
    port: int | None
    service: str | None        # e.g. 'http', 'ssh'
    product: str | None        # e.g. 'nginx', 'OpenSSH'
    version: str | None
    kind: str                  # 'service' | 'web_endpoint' | 'tech'
    detail: dict               # tool-specific extras (status, title, tls, etc.)
    source_tool: str           # 'nmap' | 'httpx'
    raw_ref: str               # path/hash of the raw output slice (provenance)
    confidence: float          # 0..1 (parser confidence; banners lie)
    scope_status: str          # 'in_scope' | 'skipped_out_of_scope'
    observed_at: str           # ISO 8601
```

### SQLite schema (the graph, minimal — the full node/edge model grows from this)
```sql
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS engagement (
    id            TEXT PRIMARY KEY,
    target        TEXT NOT NULL,
    in_scope      TEXT NOT NULL,          -- JSON array
    out_of_scope  TEXT,                   -- JSON array
    mode          TEXT NOT NULL DEFAULT 'white',
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset (
    id             INTEGER PRIMARY KEY,
    engagement_id  TEXT NOT NULL REFERENCES engagement(id),
    canonical_host TEXT NOT NULL,         -- unified IP↔hostname identity (Normalizer §4)
    kind           TEXT NOT NULL,         -- 'host' | 'service' | 'web_endpoint'
    port           INTEGER,
    url_path       TEXT,                  -- for web_endpoint only
    service        TEXT,                  -- scanner's guess: an ATTRIBUTE, not identity
    scope_status   TEXT NOT NULL,
    UNIQUE(engagement_id, canonical_host, kind, port, url_path)  -- service excluded on purpose
);
-- aliases table maps observed host strings (ip, hostname) -> canonical_host, so a machine
-- seen two ways is one asset (the mechanism behind idempotent re-run + no IP/hostname dupes).
CREATE TABLE IF NOT EXISTS host_alias (
    engagement_id  TEXT NOT NULL REFERENCES engagement(id),
    observed_host  TEXT NOT NULL,
    canonical_host TEXT NOT NULL,
    UNIQUE(engagement_id, observed_host)
);

CREATE TABLE IF NOT EXISTS finding (
    id            INTEGER PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagement(id),
    asset_id      INTEGER REFERENCES asset(id),
    kind          TEXT NOT NULL,
    product       TEXT, version TEXT, service TEXT, port INTEGER,
    detail        TEXT,                   -- JSON
    source_tool   TEXT NOT NULL,
    raw_ref       TEXT NOT NULL,
    confidence    REAL NOT NULL,
    observed_at   TEXT NOT NULL,
    UNIQUE(engagement_id, asset_id, kind, port)   -- service excluded → reclassify updates, not dupes
);

CREATE TABLE IF NOT EXISTS interpretation (
    id            INTEGER PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagement(id),
    asset_id      INTEGER REFERENCES asset(id),
    summary       TEXT NOT NULL,
    cve_refs      TEXT,                   -- JSON array, model-asserted
    tech_notes    TEXT,
    model         TEXT NOT NULL,
    confidence    REAL,
    provenance    TEXT NOT NULL,          -- JSON: source finding ids
    source        TEXT NOT NULL DEFAULT 'model_asserted',   -- provenance class (quarantine-ready)
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_log (
    id            INTEGER PRIMARY KEY,
    engagement_id TEXT NOT NULL REFERENCES engagement(id),
    kind          TEXT NOT NULL,          -- 'tool' | 'query'
    detail        TEXT NOT NULL,          -- JSON: tool/outcome, or question/facts/reasoner/answer
    created_at    TEXT NOT NULL
);
```
Note: `source='model_asserted'` and `confidence` on `interpretation` exist now so the later **write-back confidence gate / provenance quarantine** (Copilot §4.4) is a policy change, not a schema migration.

---

## Error Handling

| Failure | Behavior |
|---|---|
| Tool missing | Record capability gap + install hint; skip that adapter; continue. |
| Tool timeout / crash | Kill + reap; classify (transient/permanent/empty); record; continue. |
| Malformed tool output | Parse what's parseable; record parse-warning; never crash. |
| Scope check error/ambiguous | Treat as out-of-scope; do not execute (fail closed). |
| Local model unavailable | Interpretation: fail that host's interpret with a recorded error; keep findings (they're already persisted). |
| Cloud reasoner unreachable | Retry (bounded) → fall back to local reasoner → answer; record which was used. |
| Empty retrieval for a query | Answer "no relevant facts found"; never invent. |
| Untrusted tool output w/ injection | Delimiter-wrapped, delimiters stripped, model told to extract-only. |

Principle: **degrade coverage, never correctness.** A partial run still persists and is answerable over what it produced.

---

## Testing Strategy

1. **Unit — parsers (highest value).** Fixture files of real `nmap -oX` and `httpx -json` output → assert exact `Finding` lists. Include a malformed fixture (assert graceful partial parse). This is where correctness lives; test it hardest.
2. **Unit — ScopeGate + resolution.** In-scope / out-of-scope / CIDR / ambiguous / resolver-error → fail-closed on the last two; **assert `resolve_and_gate` returns IPs and that a hostname resolving to an out-of-scope IP is rejected** (the gate-bypass fix).
3. **Unit — host canonicalization + idempotency.** A host seen as IP and as hostname → one asset; a re-scan that reclassifies a port's service → update not duplicate; insert twice → no dupes; restart → state reloads.
4. **Unit — CVE validator.** A real CVE for the right product → VALID; a made-up ID → NOT_FOUND (dropped); a real ID for the wrong product → MISMATCH (flagged).
5. **Unit — ground guard.** An answer naming a host/port/CVE not in the fact set → stripped/flagged; an answer fully grounded → passes clean.
6. **Unit — grounding prompt + injection.** Empty facts → no-facts path; a finding whose banner contains "ignore previous instructions…" → treated as data.
7. **Integration — the loop on a lab target.** Run `engage → recon → ask` against an authorized lab host. Assert findings match known ports/services; an interpretation is produced (with only *validated* CVEs); the answer references stored facts and invents nothing.
8. **Validation — the Validation Goals** (requirements.md), with the objective Checkpoint-5 threshold and the regression set (Copilot §13.5).

---

## Configuration (`engagement.toml`)
```toml
[engagement]
target = "lab.internal"
in_scope = ["lab.internal", "10.10.10.0/24"]
out_of_scope = ["10.10.10.1"]
mode = "white"
kind = "practice"      # 'practice' (lab/CTF/HTB/THM) → cloud TEACHER
                       # 'real' (authorized IRL)      → local SUPPORT, nothing leaves the box

[models]
analysis        = "foundation-sec-8b-reasoning"  # local, on-demand — fdtn-ai/…-Q4_K_M-GGUF (~5 GB)
reasoner_cloud  = "deepseek-v4-flash"            # the TEACHER, used ONLY when kind = 'practice'
reasoner_local  = "qwen3-4b-thinking-2507"       # local reasoner/broker — unsloth GGUF, UD-Q4_K_XL (~2.5–3 GB)
# GGUF sources (Copilot §4): unsloth/Qwen3-4B-Thinking-2507-GGUF · fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF
# offense (DeepHat-V1-7B, mradermacher/DeepHat-V1-7B-GGUF) is out of v1 scope — no exploitation in the slice.
cve_source      = "nvd_local"                  # deterministic CVE validator source

[recon]
tool_timeout_secs = 300
nmap_args = "-sV -T4"
```
The reasoner is selected by `kind`, not a `cloud_enabled` flag — practice teaches with the cloud model; real work stays local. There is no config that sends a `real` engagement to the cloud.

---

## What this design deliberately leaves as a stub for later slices
- **The full model stack** is the target, not v1's shape. Production runs a **broker-fronted three-model stack** (Copilot §4): `Qwen3-4B` as a constant **broker** that reads the graph and hands a *task-scoped brief of pointers* to a deep reasoner — `Foundation-Sec-8B` (analyst) on real work, `DeepSeek V4` (teacher) on practice — plus `DeepHat-7B` for offense. v1 collapses this: one reasoner answers one question directly (no broker — the graph is small), no offense model, interpretation by Foundation-Sec. The broker pattern and offense role arrive with the multi-model / exploitation slices; the clean `ModelProvider` boundary is what lets them slot in without reshaping the rest.
- **Retrieval** is naive (pull-and-filter). RAG + hybrid retriever is the next slice *if* naive retrieval proves too weak — validate first.
- **The graph** is a relational subset; the typed node/edge + precondition model, `credential`/`defense` nodes, and computed exploit-candidate feasibility arrive with the enrichment/candidate slices.
- **Residency management** is "one at a time + on-demand"; the HardwareArbiter's queue/keep-alive tuning and the Custodian's tiering arrive with the long-haul slice.
- **The custom Rust TUI and its ACP client** are a later phase; the head start drives Hermes through the `hermes` CLI. The **MCP servers exist from day one** — v1's tools *are* MCP servers Hermes calls (the clean function boundaries above are those server interfaces), so there is no in-process→MCP rewrite later.
