# Saltpilot — Main Proposal

**Version:** 2.1
**Status:** Source of truth
**v2.1 —** resolved the frontend↔Hermes open question: the TUI attaches via **ACP** (`hermes acp`) as a client, with Hermes's internal `tui_gateway` JSON-RPC as a per-gap fallback (§2, §10).
**v2.0 — architecture-first rewrite.** Restructured from a pitch into an architecture document. **Hermes Agent is now the spine** (§2: what we build on — plugins + skills + MCP, one orchestrator, not a fork); the two features are framed as their **Hermes attachments** (§3: Auto-Recon = subagent, Copilot = interactive loop); the **knowledge layer is promoted to its own section** (§4, connective tissue) and pointed at the new Knowledge-Architecture Blueprint; the eight principles are **demoted from the headline to enforced constraints** (§6); a **whole-system diagram** (§1) replaces the feature-only one. Concrete content (model stack, hardware, long-haul substrate, build sequence, two-language split) is preserved and reframed, not cut.
**Prior history (pre-rewrite):** v1.3–1.8 evolved the model layer to the broker-fronted three-model stack (Qwen3-4B broker · Foundation-Sec-8B analyst · DeepHat-V1-7B offense · DeepSeek V4 practice teacher), added the long-haul endurance substrate, and ran cross-file consistency passes. Section numbers below are post-2.0.

**Role:** This is the authoritative document for Saltpilot as a *program*. It owns the program architecture — **what we build on**, the **integration** between Saltpilot's two features, and the **shared infrastructure** they both rest on. Where it and a feature blueprint disagree, this document wins.

**Companion blueprints (feature detail):**
- **Copilot Blueprint** — the human-driven assistant (depth).
- **Auto-Recon Blueprint** — the autonomous reconnaissance engine (breadth).
- **Knowledge-Architecture Blueprint** — the knowledge layer in depth: stores, scope model, flows, and how each feature reads/writes it.
- **TUI Blueprint** — the frontend: tech stack, screens, and interactions.

---

## 1. What Saltpilot Is

Saltpilot is a single, local-first program for **authorized** offensive-security work — CTF, bug bounty, sanctioned penetration tests, and red-team engagements. It runs on the operator's own hardware, refuses no legitimate task (it uses an uncensored local model for offense), and keeps all data on the box.

It has **two features that form one workflow**:

- **Auto-Recon Engine** — autonomous, exhaustive reconnaissance across every domain (web, cloud, apps, network, OS/AD, hardware). The *breadth* front-end.
- **Copilot** — a human-driven assistant for the deep analysis and exploitation work that follows. The *depth* back-end.

The thesis: **autonomous breadth, then supported depth, in one continuous session.** Recon maps the ground tirelessly; the operator, amplified by the Copilot, does the thinking and the exploitation. Neither half is the product alone — the combination is.

**The shape of the system — four layers.** Everything in this document is one of these four and how they connect:

1. A **harness** — Hermes Agent — that runs the agent loop, memory, skills, and tools (§2).
2. **Two features** attached to it — Auto-Recon (a subagent) and the Copilot (the interactive loop) (§3).
3. A **knowledge layer** both features share — the graph, RAG corpus, experience memory, and the Internet — the connective tissue (§4).
4. **Shared infrastructure** underneath — the model stack, sandbox, scope/audit, storage, hardware (§5).

```text
   OPERATOR
      │   Rust / Ratatui TUI  (a client on Hermes's session plane)
      ▼
 ═══════════════════  HERMES AGENT — the harness  ══════════════════
   the orchestrator:  sessions · memory · skills + learning loop ·
   tool routing · subagents · scheduler · Docker sandbox

   Saltpilot extends it:  plugins + skills + MCP   (a mod, not a fork)

      COPILOT                         AUTO-RECON
      interactive loop   ◀──handoff──  subagent / session opener
      depth · human-driven            breadth · autonomous · terminating
 ═══════════════════════════════════════════════════════════════════
        │  calls (MCP tools)                  │  points at (models)
        ▼                                     ▼
   TOOLS  (MCP servers, Python)         MODEL STACK  (Ollama, 1 at a time)
     Workbenches · scout ·                Qwen3-4B broker  →  deep reasoner
     graph_query / graph_write · cve        (Foundation-Sec | V4) + DeepHat
        │
        ▼  read / write
 ═════════════════  KNOWLEDGE LAYER  (connective tissue · §4)  ══════
   graph:  engagement-scope (target brain)  +  general-scope (wiki)
   · RAG corpus   · Hermes memory (experience)   · scout (the Internet)
 ═══════════════════════════════════════════════════════════════════
```

---

## 2. What We Build On — Hermes Agent (the foundation)

Saltpilot is **not** built from scratch and it is **not** a fork. It is an **extension of Hermes Agent** — the open-source agent harness from Nous Research. This is the core of the whole program, so it is stated first.

**What Hermes provides.** Hermes is a *harness*: it runs one agent core across a CLI, a TUI, and messaging / scheduled entry points, and gives that core the things an agent needs — persistent **memory** (SQLite + FTS5 sessions with cross-session recall), a **skills** system with a learning loop, **tool routing** (including MCP servers), **subagents**, a **scheduler**, **sandboxed execution** (Docker / SSH backends), and **model-agnostic** inference (it points at any OpenAI-compatible `/v1` endpoint). It treats session state as infrastructure, and per-conversation prompt caching as a first-class constraint.

**How Saltpilot builds on it — plugins + skills + MCP, not a fork.** Hermes is explicitly designed to be extended *through plugins and skills, not by modifying its core*. Saltpilot honours that contract: it is a **bundle of MCP servers, skills, and plugins** that turns a generic Hermes install into an offensive-security agent — the same "a mod, not a standalone program" model used for Saltcode on Pi. The consequence matters: Saltpilot builds **far less harness than it appears to**. Memory, the learning loop, subagents, scheduling, and the sandbox are Hermes's, not ours — we add security behaviour and security tools on top.

**One orchestrator.** Hermes owns orchestration. Everything Saltpilot adds is either a **tool** (an MCP server Hermes calls) or a **skill / plugin** (behaviour Hermes runs) — never a second orchestration engine competing with it. In particular, the Python "backend" (§5) is *tools and model-serving*, not a rival brain: Hermes calls it; it does not drive. Keeping one orchestrator is what stops the two features (and their tooling) from fighting over control.

**What maps to what:**

| Saltpilot piece | Hermes mechanism it uses |
|---|---|
| Graph access, scout, cve_lookup, the category Workbenches | MCP servers (tool routing) |
| Recon methodology, exploitation techniques | Skills (+ the learning / self-improvement loop) |
| Experience — "what worked before" | Hermes memory (SQLite + FTS5 sessions) |
| The Auto-Recon Engine | a Hermes subagent |
| Continuous / long-haul operation | Hermes scheduled jobs |
| The execution sandbox | Hermes's Docker terminal backend |
| The broker / analyst / offense model stack | Hermes's model-agnostic endpoint |

**The frontend is the one thing Saltpilot supplies whole.** Hermes ships generic CLI / TUI frontends; they cannot render Saltpilot's two-pane recon + copilot cockpit. So the **Rust / Ratatui TUI (TUI Blueprint) is a Saltpilot-specific client on the Hermes session plane** — the same plane the CLI, messaging gateways, and scheduled jobs already attach to — not a replacement core. **It attaches via ACP (Agent Client Protocol):** `hermes acp` runs Hermes as an ACP server and the TUI is an ACP client — a documented, stable contract, chosen over Hermes's internal `tui_gateway` JSON-RPC (TUI Blueprint §1–2). *(This resolves what was the program's main open question; the one remaining build-time check is in §10.)*

**A constraint Hermes imposes.** Per-conversation prompt caching is *sacred* — do not swap toolsets or rebuild the system prompt mid-conversation, or the cached prefix (and the operator's cost) blows up. Saltpilot's Workbench abstraction fits this well: the model's *intent vocabulary* stays stable even as the underlying tools change (Auto-Recon §4.1), so tool exposure stays cache-stable.

---

## 3. The Two Features, Built on Hermes

Both features run inside the same Hermes runtime and share one knowledge layer (§4). What differs is **how each attaches** and **what it does**.

### 3.1 Auto-Recon — a Hermes subagent (breadth)

The Auto-Recon Engine runs as a **Hermes subagent**, invoked as the **session opener**. It autonomously maps the target's surface across every domain (web, cloud, apps, network, OS/AD, hardware) in progressive waves, and **writes what it finds into the shared graph as engagement-scoped facts**. It is a separable component — it can also run standalone or on a Hermes schedule — but in the unified workflow it is simply the thing that runs first. It **never exploits** (fenced autonomy, §6) and has a definition of done that **stops and hands off**. *(Auto-Recon Blueprint owns the detail.)*

### 3.2 Copilot — the interactive Hermes loop (depth)

The Copilot **is** the interactive Hermes session — the human-driven loop the operator works in. It **reads** the shared graph (what recon found), reasons over it with the model stack (§5), and helps the operator brainstorm and execute the deep analysis and exploitation work. It **writes** back two kinds of thing: operator-confirmed engagement facts, and — after a confirmed success — **distilled general knowledge** (the experience loop, §4). The operator executes and verifies; the Copilot advises, retrieves, remembers, and reasons. *(Copilot Blueprint owns the detail.)*

### 3.3 How they connect — the handoff

The seam between the features is a **typed data contract on shared storage**, not a tangle of shared code — so either feature can evolve independently as long as the contract holds.

- **Unified session.** A session opens with recon. Recon establishes the engagement (the session's "main topic") and hands off to the Copilot, all in one continuous flow — mirroring a chat session, where the opening sets the context for everything after.
- **The handoff payload.** Recon hands over more than a surface map: an **attack-surface map enriched with a vulnerability inventory, a defensive-posture profile, and exploit candidates carrying their conditions** (availability, preconditions, met / unmet / blocked-by-defense status, feasibility) — written as engagement-scoped graph nodes (`target` / `service` / `finding` / `cve` / `technique`) plus the engagement-state **rolling summary**. The Copilot reads that state, opens by presenting the *prioritized* surface, and uses the enrichment to brainstorm viable, defense-aware attack paths (advisory; the operator executes).
- **Progressive (general → specific).** Recon runs in waves — fast / broad first (the Copilot has context within minutes), heavy / deep later. The Copilot activates after the fast waves; it does not wait for exhaustive recon.
- **Streaming.** Deep waves continue in the background and feed new findings into the live session as they land (continuous monitoring).
- **Bidirectional — two channels back from the operator (via the Copilot):**
  - **Steering** (a directive): the operator says *where to look* ("go deep on host X") and the engine retargets its firepower there.
  - **Enrichment** (a fact): the operator discovers something recon could not (a working credential, a confirmed behaviour, a new subdomain) and gives it to the Copilot. The Copilot **confirms** it (reasons it against everything known, then verifies with a targeted active check), writes it into the shared graph, and the fact **re-activates exactly the candidates its missing-info unblocks** — flipping them *blocked → ready* — while the expansion loop maps any new surface it opens. One shared model enriched by one engine, **not** a second parallel recon (which on one box only adds contention and a merge problem).
- **Critical-finding escalation.** A high-severity find (exposed credentials, CVSS ≥ 9) interrupts the operator *immediately* rather than waiting its turn — break-glass that alerts the human, never auto-acts.

---

## 4. The Knowledge Layer (the connective tissue)

The knowledge layer is what the two features share. At the program level it is the **connective tissue**; it is owned in depth by the **Knowledge-Architecture Blueprint**. This section fixes only *what it is and how the features use it*, so the seam is unambiguous.

**Four stores, one rule.** The anti-collision rule is **single source of truth per data type** — each kind of knowledge lives in exactly one store, and the boundary is drawn by *what kind* of knowledge it is, not by who is using it.

| Store | Owns (source of truth for) |
|---|---|
| **The graph** (SQLite) | Structured facts — targets, findings, vulns, CVEs, techniques + preconditions, and how they relate |
| **RAG corpus** (sqlite-vec + FTS5) | Raw reference *text* not yet distilled — CVE descriptions, writeups, PoCs, CVSS, tool docs |
| **Hermes memory** (SQLite + FTS5) | Autobiography — what was done, when, in which session (the experience substrate) |
| **Scout** (live feeds) | The outside world / what's new — NVD, OSV, GHSA, the web |

**One graph, two scopes.** The graph is a *single* store partitioned by scope: **engagement-scope** = the live per-target "brain" (this campaign's surface, findings, hypotheses; archived at end), and **general-scope** = target-independent knowledge (vuln classes, techniques, CVE relationships, distilled lessons; durable, grows across engagements). This scope axis is what lets one store hold both the target's facts and the general wiki without them colliding.

**How the two features use it — the division that prevents a mess:**

- **Auto-Recon** *populates the engagement scope*: it writes findings (hosts, services, vulns) into the target brain via its deterministic pipeline, and **reads** general-scope knowledge + the corpus + scout to interpret findings and generate candidates. It does **not** write general-scope knowledge.
- **Copilot** *reads everything* and writes two things: operator-confirmed engagement facts, and — via distillation — **general-scope experience** (a confirmed success becomes a durable technique + preconditions). It is the **sole writer of general knowledge**.
- Governed by four rules: single-source-per-type (above); **scope** (engagement vs general); **provenance + validation** (`operator > tool > model`; CVEs validated, answers grounded); and **graph-primary retrieval** (hit the graph first, fall to RAG only on miss / undistilled).

**The flows that connect it** (detailed in the Knowledge-Architecture Blueprint): **ingest** (scout → corpus + fresh CVEs), **retrieve** (graph → RAG → scout), **distill** (Hermes experience → general-scope technique — the experience loop), **promote** (engagement lessons → general scope at engagement end), and **new-CVE** (scout ingest → deterministic match against the live engagement graph → surfaced as a candidate, never auto-exploited).

Everything above is exposed to Hermes as **MCP servers** (`graph_query` / `graph_write`, `scout`, `cve_lookup`), so both features reach it through Hermes's tool routing (§2), not bespoke wiring.

---

## 5. Shared Infrastructure (the rest)

Beneath Hermes (§2) and the knowledge layer (§4) sits the rest of the shared substrate. It is owned here so neither blueprint claims it alone.

- **Model stack — broker-fronted, three roles, one deep-reasoner swap.** A constant local **broker** (`Qwen3-4B`) reads the graph and hands down a *task-scoped brief of pointers* (not crammed facts) to a **deep reasoner** — `Foundation-Sec-8B` (analyst / planner) on **real** work, the cloud **teacher** (`DeepSeek V4`) on **practice** (labs / CTF / HTB / THM) — plus a local uncensored **offense** model (`DeepHat-V1-7B`). Two configs: **real = full local sec-stack, no cloud**; **practice = Qwen3 + V4**. Locals are on-demand, one on the GPU at a time; Hermes points at whichever is loaded. Detail: Copilot Blueprint §4.
- **Resource arbitration — the HardwareArbiter.** With scanners GPU-free (CPU / network) and only one local model resident at a time, GPU contention shrinks to *scheduling turns* among the on-demand local models (broker → analyst → offense) — single-tenant, batched with keep-alive, cooperative (never interrupt a running scan or in-flight inference), with a watchdog and priority queue. Scanners run in parallel, never queuing for the GPU. (On practice the cloud teacher is off-box at no GPU cost; on real work the whole stack is local.) Auto-Recon Blueprint §8.1.
- **Guardrails — scope + audit, program-wide.** One AuthorizationManager enforces scope on recon's expansion *and* the Copilot's suggestions; one audit trail records both. Scope **fails closed**: if a scope check errors or is uncertain, the action does not happen.
- **Sandbox — Docker (Hermes's backend).** All tool and PoC execution happens in the sandbox, never on the host. Tool output is treated as hostile input (it comes from adversarial targets).
- **Storage — SQLite-family.** The graph, the vector index, the audit log, Hermes memory, and the engagement state all live in SQLite-family stores — keeping the whole program local-first, file-based, and portable.
- **Hardware — the reference box.** RTX 3060 12GB / Ryzen 7 7700 / 32GB DDR5 / Pop!_OS. The GPU hosts **one local model at a time** (Ollama, on-demand) — broker (`Qwen3-4B`, ~3GB), analyst (`Foundation-Sec-8B`, ~5GB), or offense (`DeepHat-7B`, ~4.5GB); peak ~5GB of 12GB. On **real** work the whole stack is local; only **practice** reaches the cloud teacher (Copilot §4.2).

### 5.1 Implementation stack (the two-language split)

The **backend brains stay in Python** — model serving (Ollama / llama.cpp), the RAG stack (BGE-M3, sqlite-vec, reranker), the autoencoder noise filter, the MCP servers, and recon orchestration (I/O-bound subprocess work). That ecosystem is Python's home; rewriting it in Go / Rust would be large effort for no gain. The **frontend is a separate Rust + Ratatui TUI**, but it does **not** dial the Python side directly: it drives **Hermes over ACP** (§2), and Hermes routes to the Python MCP tools. So the boundary the TUI speaks is *ACP-to-Hermes*; the Python brains sit behind Hermes as tools, not behind a socket the UI opens. The Rust-frontend / Python-backend split (as in Saltnitor and Pi / Saltcode) still holds — Hermes is simply the orchestrator sitting between them.

Two rules from §2 govern this split so it doesn't reintroduce confusion: the Python side is **tools + serving that Hermes calls, not a competing orchestrator**; and the **TUI is a Hermes-session client, not a replacement core**. The backend stays usable **headless** — the TUI is one client of the boundary, so Saltpilot can also be scripted or driven by Hermes's own CLI / schedule without the UI. Frontend design (layout, screens, keybindings) is owned by the **TUI Blueprint**; this proposal fixes only the stack and the boundary.

---

## 6. Design Principles (enforced constraints)

These eight invariants shape the architecture above. Each is stated as a constraint **and where it is enforced** — they are decisions with a home in the system, not slogans.

1. **Local-first and private.** Target data, plans, and findings stay on the box — an OPSEC stance, not a preference. — *Enforced by:* the model configs — **real work is all-local**; the cloud teacher touches only practice / lab targets, where there is no client data, never real engagement intelligence (§5 model stack).
2. **Human-in-control / skill-amplifier.** The operator executes and verifies; Saltpilot advises, retrieves, remembers, and reasons — never lets the operator stop understanding their own engagement. — *Enforced by:* the Copilot being advisory (§3.2) and fenced autonomy (below).
3. **Fenced, terminating autonomy.** Only reconnaissance is autonomous, with a definition of done that **stops and hands off**; Saltpilot never autonomously exploits. — *Enforced by:* the Auto-Recon subagent boundary and the handoff (§3.1, §3.3).
4. **Authorized-use only.** Scope enforcement and an audit trail run program-wide; scope **fails closed**. — *Enforced by:* the AuthorizationManager (§5).
5. **Externalize volatile knowledge.** Tool syntax, CVEs, techniques, and findings live in refreshable stores, never in model weights; the model expresses *intent* and the Workbench renders the command for the installed tool. — *Enforced by:* the knowledge layer (§4) and the category Workbenches (Auto-Recon §4.1).
6. **Cheap-and-deterministic, before *and after* the model.** Parsers, filters, and scope gates run *before* the model so it spends capacity on judgment; deterministic validators run *after* it — wherever the model asserts a checkable fact (a CVE, a named host in an answer), a parser verifies it against a real source before it becomes graph truth. — *Enforced by:* Auto-Recon §5.2 (CVE validation) and Copilot §7 / §4.4 (grounding guard).
7. **Visible, never silent.** Suppressed noise becomes counts; failures become a coverage ledger; gaps are surfaced as decisions. — *Enforced by:* the coverage ledger and operator digests (Auto-Recon; TUI §5.9).
8. **Continuous, steady-state operation.** A **bounded steady state** (live cost never grows with accumulated volume) and **assume-failure self-healing**; a job is one engagement across many long sessions, not a single bounded run. — *Enforced by:* the long-haul substrate (§7).

---

## 7. Continuous / Long-Haul Operation (the endurance substrate)

Principle 8 made concrete. A marathon run — 24h+, and several per job — breaks session software in three ways: **accumulation** (data and process state grow until the box grinds or OOMs), **dependency failure** (a scanner, the store, or the cloud API *will* fail mid-run), and **recovery** (something *will* interrupt a multi-session job). Six subsystems hold the program in a bounded, self-healing steady state. Each is detailed in the blueprint that owns it; this is the spine.

- **The Custodian — steady-state resource governance.** A supervisory task that caps every resource. Its linchpin is **hot / warm / cold graph tiering**: only the active working set (in-scope, live candidates, recent findings) stays *hot* and queryable; settled / aged / out-of-scope subgraphs compact to cold storage (recoverable). Retrieval, RAG, and live feasibility re-derivation only ever touch the hot set, so **query latency is flat at hour 30 as at hour 1** — the one change that decouples live cost from total volume. Around it: sprint-DAG snapshot + compaction, audit / log rotation, evidence-blob GC (keep hashes, expire raw), and a backend heap watermark. *(Auto-Recon §8.2; graph tiering touches the shared knowledge layer.)* → kills Tier-1 accumulation, Tier-2 growth.
- **The Supervisor — assume-failure self-healing.** Every long-running part (recon orchestrator, each scanner, the model runner, the cloud client, the store) is a *supervised* component with a health probe and restart-from-persisted-state. Includes a **process janitor** (hard per-tool timeouts, mandatory child-reaping, an FD / process budget with backpressure) so a leak or hang is survived by restarting *that component*, not the run. *(Auto-Recon §8.2.)* → kills Tier-1 subprocess / FD / zombie accumulation.
- **The resilient cloud client — the practice teacher as a supervised dependency.** On **practice** engagements, DeepSeek V4 sits behind retry + backoff + jitter, a circuit-breaker, request timeouts, self-throttling, and **runtime degrade to a local reasoner on transient failure**. A lab outage becomes a quiet drop to local reasoning that recovers when the breaker closes. *(Real engagements are all-local — no cloud dependency to supervise. Copilot §4.4.)* → kills the Tier-1 cloud-reliability stall on practice. *(Asterisk: a prolonged outage means degraded local reasoning for its duration — resilient ≠ no quality loss.)*
- **Checkpoint / Resume / Multi-Session — continuity as a designed loop.** On a cadence and at safe points, write a compact recovery point (graph snapshot, bounded engagement state, in-flight sprint status, coverage ledger, reasoner re-attach info). Resume is idempotent — reload, re-run incomplete idempotent sprints, reconnect clients. **Pause = checkpoint + graceful quiesce; resume = load checkpoint**, so a job spans many marathons with clean stops, and a **shift-handoff summary** lets a later session pick up cold. *(Auto-Recon §8.2 + TUI §5.9.)* → kills Tier-1 resume-at-depth; makes repeated marathons native.
- **Steady-state data hygiene — the Tier-2 killers.** WAL + single-writer queue + Custodian checkpointing (ends "database is locked" / WAL bloat); a **mode / cost-gated reconciliation pass** — passive timestamp aging always, but *active* re-verification (re-probe "does this credential still work?") only in loud mode, rate-limited, and **suppressed under stealth or saturation-backoff**; **adaptive noise-filter recalibration** on a rolling window; a **fact-precedence rule** (`operator-confirmed > tool-observed > model-asserted`; a lower-authority writer flags, never overrides) with **snapshot reads** for feasibility re-derivation; and a **write-back gate keyed on verification / corroboration — not self-reported confidence** — so a possibly-hallucinated fact is quarantined, down-weighted, and re-verified-or-expired rather than silently becoming ground truth — paired with **bounded, re-grounded copilot context**. *(Auto-Recon §8.2; Copilot §4.4 / §6.3.)* → kills Tier-2. *(Asterisk: contains hallucination propagation to near-none; can't lower the model's source rate.)*
- **Saturation, backpressure & sustainability — Tier-3, as low as it goes.** A recon **saturation state** (when deep waves stop yielding, back off to low-frequency monitoring, ramp up only on enrichment / change) ends "20 hours burning the GPU for noise"; re-recon **trigger coalescing** (debounce / merge) bounds the backlog; **VRAM-swap hygiene** (cleanup between swaps + CUDA-context health check) keeps hundreds of model swaps clean; and the human layer gets **digests over firehose** (periodic "what changed / newly actionable / needs you" rollups, alert batching that *widens* over a long run, a "since you were away" summary) plus **sustainable-pace pacing** (cap sustained GPU / CPU so a consumer box isn't pinned at 100% for 24h). *(Auto-Recon §8.2; TUI §5.9.)* → drives Tier-3 low; protects the machine and the operator.

**Honest bottom line.** Tier 1 and 2 go to near-none (bounded steady state + supervised self-healing are exactly what that requires), with two irreducible asterisks: cloud reasoning *degrades rather than stalls* under a long outage, and hallucination is *contained, not eliminated*. Tier 3 is minimized but not zero — sustained load wears hardware and fatigue wears the operator; software reduces both as far as it can, the rest is physics and biology.

---

## 8. The Blueprints (scope boundaries)

| Owned by | Document |
|---|---|
| Program architecture, the Hermes build model, integration, shared infrastructure, principles | **This Main Proposal** (source of truth) |
| Retrieval / reasoning loop, memory, graph schema, anti-laziness, skills, RAG stack, datasets, copilot self-security | **Copilot Blueprint** |
| Modular recon domains, the recon pipeline (normalize → filter → interpret → correlate), wave workflow, the Workbenches / tool management, failure handling, hostile-output defense, the HardwareArbiter's recon side | **Auto-Recon Blueprint** |
| The knowledge layer in depth — the four stores, the scope model, the five flows, and how each feature reads / writes it | **Knowledge-Architecture Blueprint** *(new)* |
| The TUI: frontend tech stack, layout, screens / mockups, interactions, keybindings, state transitions | **TUI Blueprint** |

When a blueprint describes the *seam* (the handoff, shared models, shared scope / audit, the arbiter, the knowledge layer), this Main Proposal is the authority; the blueprint defers to it.

---

## 9. Program-Level Build Sequencing

Build the shared substrate first, then the features, then the seam.

1. **S0 — Hermes + shared substrate.** Stand up Hermes; wire the broker-fronted model stack to its endpoint (§5); SQLite-family stores; scope + audit; the Docker sandbox backend; the HardwareArbiter. Saltpilot-as-a-Hermes-extension starts here (the first plugins / MCP servers register).
2. **S1 — Knowledge layer.** The graph schema + MCP servers (`graph_query` / `graph_write`, `scout`, `cve_lookup`) + hybrid RAG; seed it (bootstrapping). *(Knowledge-Architecture Blueprint.)*
3. **S2 — Copilot core.** The retrieval / reasoning loop and engagement state (Copilot Blueprint P0–P2) — usable standalone first.
4. **S3 — Auto-Recon core.** Modular domains, the pipeline, the wave workflow, the Workbenches, failure handling (Auto-Recon Blueprint P0–P3) — usable standalone first.
5. **S4 — The seam.** Wire recon's handoff into the Copilot session: recon as the session opener, the streaming / continuous model, bidirectional steering, enrichment, critical-finding escalation.
6. **S5 — Hardening & polish.** Red-stealth recon mode; curation, evaluation, skills, and the rest of each blueprint's later phases.
7. **S6 — Long-haul layer (§7).** The endurance substrate, staged *after* a bounded session works end-to-end: first the **Custodian** (graph tiering + compaction + GC) and **WAL / write-queue**, then the **Supervisor** (process janitor + component restart) and the **resilient cloud client**, then **checkpoint / resume + pause / handoff**, then **reconciliation + adaptive recalibration + write-back gate**, and finally **saturation / backpressure + digests / pacing**. Ordered by severity — Tier-1 first, Tier-3 last.

Rationale: each feature is independently useful before the seam exists, so the program delivers value early and the integration is the last (not the first) thing built. The long-haul layer comes last because you can only harden endurance once there's a working session to run long — but it is a *planned* stage, not an afterthought (Principle 8).

---

## 10. Open Questions (program-level)

- **Hermes client surface for the TUI — resolved (ACP).** Hermes exposes `hermes acp` (an ACP server for external clients) and an internal `tui_gateway` JSON-RPC; the TUI attaches as an **ACP client** (§2, TUI Blueprint §1–2). *Remaining build-time check, not a design risk:* pin a Hermes version and confirm (`hermes acp --help`) that ACP carries the cockpit-specific events (recon progress, candidate updates, `arbiter_state`) and the streaming/handoff signals — falling back to `tui_gateway` only for any specific gap.
- **Naming.** "Saltpilot" is the working program name; the two features are "Auto-Recon Engine" and "Copilot." Finalize.
- **Standalone vs unified packaging.** Whether the Auto-Recon Engine ships as a separately-runnable binary as well as the session opener.
- **Multi-engagement program state.** How Saltpilot manages several concurrent engagements / programs above the single-engagement state (scope isolation is defined; orchestration above it is open).
