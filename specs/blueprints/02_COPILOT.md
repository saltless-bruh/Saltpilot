# Saltpilot — Copilot Blueprint

**Part of:** Saltpilot. The **Main Proposal** is the source of truth for the program-level view, the integration with the Auto-Recon Engine, and shared infrastructure; the **Knowledge-Architecture Blueprint** owns the knowledge layer (stores, scope model, retrieval, the five flows). This blueprint details one of Saltpilot's two features — the human-driven Copilot (depth).

**Version:** 1.14
**Status:** Design baseline
**v1.14 — knowledge-layer wiring:** §5, §12.3, and §6 now defer to the new **Knowledge-Architecture Blueprint** for the store/scope model, retrieval, and the five flows (the Copilot keeps the node schema §6 and its own retrieval loop §7); dropped a stale “v2.5.0 proposal” cross-reference.
**v1.1 added:** negative-knowledge capture (§6, §7), graph curation (§13), copilot self-security (§13), engagement scope isolation (§11), bootstrapping / durability / evaluation (§13), and a concrete reference deployment (§4.2).
**v1.2 added:** anti-laziness mechanisms for small models (§4.3), long-engagement state continuity (§5.1), and realistic limits (§13.7).
**v1.3 added (lessons from the AI-Driven Coding framework):** an advisor-style attack-chain planner / executor split (§7.8), context-discipline rules — one-task-per-window, frozen minimal context, cheap-gate-before-model-judge (§4.3) — a local reasoning planner role and concrete hybrid GPU+CPU run config (§4, §4.2).
**v1.4 added:** the skill-amplifier design principle (§1), and related-work positioning against PentAGI (§2.1).
**v1.5 adds:** the concrete hybrid RAG stack (§12.3), IRL pentest skill grounding (§9), concrete corpus sources for bootstrapping (§13.3), named evaluation benchmarks (§13.5), and fine-tuning dataset references (§14).
**v1.6 added:** Stage-4 attack-path brainstorming that consumes recon's exploit-candidates via a graph-enumerated + LLM-reasoned + playbook-backed planner (§7.8), and the operator-finding confirm-and-enrich feedback loop (§7.9).
**v1.7 adds:** graph-schema sync with the newest recon — `credential` and `defense` node types, the `satisfies` edge, and live-computed (never stored) exploit-candidate feasibility (§6).
**v1.8 reworks the model layer (§4):** split by role + residency — cloud reasoner (DeepSeek V4 Flash/Pro) for planning/reasoning/orchestration, two local **on-demand** models (Foundation-Sec analysis [batched], WhiteRabbitNeo offense [bursty]) time-sharing the GPU, engagement-gated with a local fallback. Reference deployment (§4.2) updated: no resident model, ~5GB single-tenant peak, comfortable on the 3060.
**v1.9 adds the copilot-side long-haul layer (§4.4):** resilient cloud client (retry/backoff, circuit-breaker, self-throttle, runtime degrade to local), bounded re-grounded context (regenerate engagement state from the graph, not a bloating blob), and a write-back confidence gate + provenance quarantine (LLM-asserted facts tagged, down-weighted, re-verified-or-expired). Native marathon support (Main Proposal §4.2).
**v1.10 — review fixes + model-purpose split:** the reasoner is chosen by engagement *type* — cloud frontier model = **teacher** on labs/CTF/HTB/THM (deep what/why/how), local reasoner = **support** on real IRL work (safety, private); this also dissolves the cumulative-cloud-exposure risk (§4). Mode-aware delivery + a deterministic grounding guard on answers (§7). Write-back gate keys on **verification/corroboration, not self-confidence** (§4.4); provenance authority order operator>tool>model as the precedence rule (§6.3). Model/prompt **regression harness** (§13.5).
**v1.11 — concrete three-model stack + broker pattern (§4):** named models — **Qwen3-4B** as the constant **broker/organizer** (both modes; reads the graph, emits a task-scoped brief of *pointers* not crammed facts), **Foundation-Sec-8B** as analyst/planner on real work, **DeepHat-V1-7B** as offense, **DeepSeek V4** as the cloud teacher on practice only. Two configs by engagement type: real = full local sec-stack (no cloud); practice = Qwen3 + V4. The broker is the constant; only the deep reasoner swaps (§7.8).
**v1.12 — model sources + broker variant pinned (§4):** added GGUF download sources/quants — broker `unsloth/Qwen3-4B-Thinking-2507-GGUF` (UD-Q4_K_XL, ~2.5-3 GB), analyst `fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF`, offense `mradermacher/DeepHat-V1-7B-GGUF`. Broker pinned to Qwen3-4B-Thinking-2507 (text-only, mature tooling) with Qwen3.5-4B-MTP as the benchmarked upgrade path and Qwen3-VL only if vision is wanted; note that 256K/1M context is KV-cache-bound to ~32-64K on the 3060. The Architecture-at-a-Glance stack diagram now reflects the broker stack.
**v1.13 — full-read consistency pass:** fixed downstream sections the §4 rewrite missed — §4.2 "Net" summary, §8 graph_write gate (verification not confidence-threshold), §12.7 hardware, §13.6 observability (Foundation-Sec is primary on real work, not a "fallback"), §13.7 ceiling note, and a duplicated changelog sentence.
**Lineage:** descends from the Auto-Pentest Framework / *Orchbiter* (see §2). **Program context & integration with the Auto-Recon Engine:** see the Saltpilot Main Proposal (source of truth).

---

## Architecture at a Glance

### The stack

```text
+-----------------------------------------------------------------+
|                          OPERATOR (you)                         |
|             drives engagement * executes * confirms             |
+-------------------------------+---------------------------------+
                                | chat (interactive)
+-------------------------------v---------------------------------+
|                       HERMES AGENT RUNTIME                      |
|     working/session memory * learning loop * skill engine       |
|                                                                 |
|  MODEL LAYER — locals load on-demand, ONE on the GPU at once    |
|                                                                 |
|   [BROKER]  Qwen3-4B-Thinking-2507   (local, the constant)      |
|      reads the graph -> task-scoped brief of POINTERS           |
|      (fact IDs / graph refs), never crammed facts               |
|                  |  brief                                       |
|                  v                                              |
|   [DEEP REASONER]  swaps by engagement type:                    |
|      real     -> Foundation-Sec-8B       (local, analyst)       |
|      practice -> DeepSeek V4             (CLOUD, teacher)       |
|      -> pulls the pointed-to facts; plans / interprets          |
|                                                                 |
|   [OFFENSE]  DeepHat-V1-7B   (local, on-demand, uncensored)     |
|      writes the exploit / payload when you build one            |
|                                                                 |
|   SKILLS (agentskills.io): SQLi enum * heap pwn * BOLA ...      |
+-------------------------------+---------------------------------+
                                | MCP
+-------------------------------v---------------------------------+
|                   KNOWLEDGE LAYER (MCP servers)                 |
|  graph_query   graph_write*   retrieve(RAG)   cve_lookup  scout |
+-----+-----------+--------------+---------------+----------+------+
      |           |              |               |          |
+-----v-----------v----+  +------v--------+  +---v----------v----+
| INFINITE-BRAIN GRAPH |  |   RAG CORPUS  |  |    THE INTERNET   |
| typed nodes + edges  |  | writeups, CVE |  |   search / fetch  |
| (domain knowledge)   |  | text, PoCs    |  |                   |
+----------------------+  +---------------+  +-------------------+

  * graph_write is human-gated (write-on-confirm, verification gate)

  ENGAGEMENT CONFIGS:  real     = full local sec-stack (no cloud);
                       practice = Qwen3 broker + DeepSeek V4 teacher.
  MODEL RESIDENCY:     one local model on the GPU at a time
                       (peak ~5 GB / 12 GB); cloud on practice only.
  CROSS-CUTTING:       scope enforcement * audit trail.
  SEPARATE STORE:      Hermes memory owns "what you did";
                       the graph owns "what works, and when".
```

### The retrieval + reasoning loop (§7)

```text
   working memory  (this target * goal * constraints * what failed)
                              |
                              v
                   query the infinite-brain
                   (match on PRECONDITIONS)
                              |
        +---------------------+----------------------+
        v                     v                      v
    [ MATCH ]            [ MISMATCH ]            [ NOT FOUND ]
  preconditions       technique exists,        no technique
  hold on target      preconditions differ     for this vuln
        |                     |                      |
        |        ADAPT-FIRST ("think"): twist the    |
        |        known technique using CVE / CVSS /   |
        |        related nodes to swap the bad step   |
        |                     |                       |
        |          viable? --no--> falls through -----+
        |                     | yes                    |
        |                     |                        v
        |                     |                  SCOUT THE WEB
        +---------------------+------------------------+
                              v
                   DELIVER THE SOLUTION     <- actionable, terse
                   (no explanation yet)
                              |
                       operator executes
                              |
                       confirm success? --no--> (revise / re-scout)
                              | yes
                              v
            EXPLAIN  +  DISTILL -> write back to the graph
            new technique node, own preconditions,
            variant_of / found_on / derived_from edges;
            never overwrite * human-gated write
```

---

## 1. Purpose and Scope

The Pentest Copilot is a **human-driven** security assistant for authorized offensive work — CTF events, bug-bounty programs, and sanctioned penetration tests. The operator (you) drives the engagement. The copilot advises, remembers, retrieves, and reasons; it does not execute attacks on its own.

This is a deliberate inversion of the auto-pentest design center. The auto-pentest framework answered "how does the AI drive safely without a human?" The Copilot answers a different question: "how does the AI make *me* faster and sharper while I drive?"

**In scope**
- Recalling what has worked before, and *under what conditions* it worked.
- Reasoning from known techniques toward a new solution when conditions differ.
- Scouting the internet for techniques the operator's knowledge base does not yet contain.
- Accumulating durable, structured domain knowledge across engagements.

**Out of scope (belongs to the sibling auto-pentest project)**
- Autonomous multi-step execution loops.
- Self-directed replanning, loop detection, emergency-intervention protocols.
- Acting on a target without an explicit operator action.

**Authorized use only.** The Copilot uses a local model that does not refuse legitimate offensive-security work, but it retains operational guardrails — scope enforcement and an audit trail (§11). Removing corporate-policy refusals is not the same as removing scope discipline; the Copilot keeps the latter.

**Design principle — the copilot must leave the operator *more* skilled, not less.** The goal is an amplifier for a practitioner who stays the expert, not a substitute that deskills them. A red-team operator has to be able to do — and explain — the work themselves; "I mostly ran the tool" is not a credible answer. This principle is load-bearing: it is why the operator executes (not the AI), why every output is verified (§13.7), and why the copilot explains *on confirmed success* (§7, Step 6) so each win teaches the reasoning behind it. Any feature that would let the operator stop understanding their own engagement is a regression, however convenient.

---

## 2. Relationship to Prior Work

The auto-pentest framework (v2.5.0) and this Copilot are now **two separate projects** with two separate foundations. Keeping them apart is the cleanest way to avoid the confusion of one codebase trying to be both an autonomous agent and a support tool.

| | Auto-Pentest (→ Orchbiter) | Pentest Copilot |
|---|---|---|
| Operator | The agent | You |
| Foundation | Your own framework | Hermes Agent runtime |
| Core problem | Autonomous-execution safety | Operator augmentation |
| Repository | Separate | Separate |

**Salvaged from v2.5.0 into the Copilot:**
- The CVE Lookup MCP server (re-exposed as a Copilot tool, §8).
- The AuthorizationManager scope-checking and audit trail (§11).
- Any tool-integration MCP servers (recon, scanners) worth reusing.
- The "single source of truth per data type" principle from §4.4 of the v2.5.0 proposal — applied here to the memory boundary (§5).

**Retired (not carried into the Copilot):**
- The autonomous orchestration loop, ReflectionEngine auto-replanning, loop guards, and the Emergency Intervention Protocol. These solve "agent drives safely," which is no longer the Copilot's problem.

### 2.1 Related work and positioning (PentAGI)

PentAGI (`vxcontrol/pentagi`) is the dominant open-source AI-pentest project and the obvious "why not just use this" question. It is a mature, autonomous-first system: a Go/GraphQL backend, React UI, PostgreSQL+pgvector, a Graphiti/Neo4j knowledge graph, a full observability stack, and 20+ sandboxed tools, deployed via Docker Compose. It is the convergent, production-grade form of the *auto-pentest* line — and it independently implements several ideas in this spec (a knowledge graph, layered memory, chain summarization, a planner plus an execution-monitoring "mentor"). It should be treated as a reference to learn from, not a competitor to out-build.

**How the Copilot is deliberately different (the positioning):**

| Axis | PentAGI | Pentest Copilot |
|---|---|---|
| Control | Autonomous-first (runs a target) | Human-driven; operator executes |
| Deployment | Heavy stack; cloud-default LLMs | Lean, single-user; local-first, private |
| Footprint | Postgres + Neo4j + observability + web UI | Rides Hermes; SQLite-family stores |
| Knowledge | General temporal KG (Graphiti) | Precondition-indexed graph for adapt-first reasoning + negative knowledge |
| Goal | Throughput / automation | **Sharpening the operator** (§1 principle) |

The Copilot is not competing on surface area — staying small *is* the strategy. Attempting to match PentAGI's breadth (rebuilding Graphiti, observability, a web UI) forfeits the Copilot's only advantage.

**What to borrow (validated prior art):**
- **Chain summarization** — PentAGI's `ChainAST` + QA-pair summarization with configurable byte budgets is a production-tested version of the §5.1 rolling summary. Study it before implementing §5.1; it is the same problem already solved.
- **Empirical validation of the small-model strategy** — PentAGI reports that models < 32B essentially *require* both a task planner and an execution monitor (≈2× quality at 2–3× cost). This is external confirmation of §4.3 (anti-laziness) and §7.8 (planner/executor).
- **Memory tiering** — their long-term / working / episodic split maps onto this spec's Hermes-memory + graph + engagement-state (§5).
- **Entity model** — `Flow → Task → SubTask → Action → Artifact/Memory` is a useful reference when fleshing out the engagement-state schema (§5.1).
- **Graph backend comparison** — Graphiti/Neo4j is the heavyweight alternative to the SQLite/KuzuDB choice in §12.3; worth a look if the local graph outgrows SQLite.
- **Sandboxing / worker-node isolation** — reinforces the self-security stance in §13.2.

**Complementary use.** The two are not mutually exclusive: PentAGI can run autonomous recon *breadth* when wanted, while the Copilot drives human-led *depth*. They occupy different niches by design.

---

## 3. Foundation: Hermes Agent as the Runtime

The Copilot does not rebuild an agent harness. It rides Hermes Agent (Nous Research) and extends it. Hermes already ships the pieces that would otherwise be the bulk of the build:

- A built-in learning loop that creates and refines skills from experience.
- A multi-level persistent memory across sessions.
- Full-text search (SQLite FTS5) over past sessions.
- Native MCP server connection for extended tools.
- Model-agnostic backends (local endpoint, OpenRouter, Nous Portal, etc.).
- Subagents and sandboxing (local, Docker, SSH).

**Caveats, treated as engineering constraints:**
- The Hermes *agent product* is young (public release early 2026). Treat the runtime as new software: pin versions, expect churn, isolate dependence behind the MCP boundary so a Hermes change does not ripple into the knowledge layer.
- Hermes is itself capable of autonomous, unattended operation (cron, self-nudging, subagent pipelines). The Copilot deliberately leans on the *knowledge* half (memory, skills, learning) and **not** the unattended-execution half. Configure it as an interactive copilot. Do not schedule engagements to run on their own.

---

## 4. Model Layer

The model layer is a **three-role local stack fronted by a broker**, with exactly one role's occupant swapped by engagement type. The local models are **loaded on demand, one on the GPU at a time** (tools run beside them on CPU/RAM), which is what keeps a 12GB card stable under continuous recon (§4.2; HardwareArbiter, Auto-Recon Blueprint §8.1). **The broker is the constant; only the deep reasoner swaps.**

| Role | Model | Residency | Notes |
|---|---|---|---|
| **Broker / organizer** (the constant) | **Qwen3-4B-Thinking-2507** | **Local, on-demand — both modes** | The stack's front door. Big context + strong tool-calling: reads broadly across the graph and, for a given task, produces a **task-scoped brief** — *what matters now* + **pointers** (fact IDs / graph refs) to the exact context — for the deep reasoner to fetch. A *general* model, which is safe here because it organizes **retrieved, validated facts** (§6, Auto-Recon §5.7), not security knowledge from its weights. Grounded to this one job; never replaced. See *The broker pattern* below. |
| **Analyst / planner** (deep reasoning) | real → **`Foundation-Sec-8B`** (`-Reasoning` for depth) · practice → **DeepSeek V4** (cloud teacher) | analyst **local, on-demand**; teacher **cloud** | Consumes the broker's brief, dereferences the pointed-to slice, and does the cyber reasoning: interpretation + attack-path brainstorming (§7.8). *Which* model fills this seat is set by engagement type (below) — the **only** role that swaps. |
| **Offense** (artifact generation) | **DeepHat-V1-7B** (formerly WhiteRabbitNeo; Qwen2.5-Coder-7B base) | **Local, on-demand (bursty)** | Uncensored: writes the actual exploit code / payloads when you're building one. **Cannot be cloud or aligned** — they refuse, and the rawest target-specific content stays local. Primary on real work; loadable on a practice box too if you want to build an exploit hands-on (V4 teaches the reasoning, DeepHat writes the artifact). |

**Two configurations, by engagement type:**
- **Real (IRL) — full local sec-stack, no cloud.** Qwen3 (broker) → **Foundation-Sec-8B** (analyst/planner) → **DeepHat-7B** (offense). Everything about the client stays on the box — the fail-closed default for data a contract or NDA governs. Foundation-Sec is the *support* reasoner: it helps you **do the work**, not lecture.
- **Practice (labs / CTF / HTB / THM) — learning stack.** Qwen3 (broker) → **DeepSeek V4** (the *teacher*). On a practice target the job is skill, so V4's near-frontier reasoning explains the *what / why / how* in depth. A practice target has no client data, so the OPSEC objection doesn't apply — and this is what dissolves the cumulative-cloud-exposure risk (§4.4): the only thing ever reaching the cloud is a deliberately-vulnerable lab, never real engagement intelligence.

**Why Qwen3 is the constant — and why that's the right shape.** Keeping the broker fixed across both modes means the graph-reading / brief-making interface never changes; switching modes swaps **only** the deep reasoner behind it (Foundation-Sec ⇄ V4), not the whole pipeline. Qwen3 stays grounded to one job (scope the graph, emit a brief of pointers) and can be tuned/prompted for exactly that. Practice ⇒ cloud teacher behind the broker; real ⇒ local analyst behind the broker. The powerful outside model is reserved for the one context where there is nothing to protect and everything to learn (Main Proposal §2).

**The broker pattern — briefs of pointers, not crammed facts.** The graph stays the single source of truth (facts + your docs + Qwen's docs, all with provenance). Qwen3, with its large context, does the expensive *wide read once* and hands down a **cheap, precise map**: not the facts re-stated (that would re-introduce a hallucination surface and a copy that drifts from the graph), but **references** — *"the plan hinges on finding #F-217 (exposed .git) and candidate #C-9 (IDOR, blocked by WAF); pull those and their neighbours."* The deep reasoner (Foundation-Sec or V4) dereferences the real, validated facts straight from the graph and spends its smaller context on **reasoning**, not on wading through everything. This plays to each model's strength — Qwen for breadth, the specialist for depth — and keeps the validation gate and provenance intact across the hand-off. It is the retrieval-scoping front-end to §7's atomic-retrieval loop, and it is exactly what a small-context expert model wants sitting in front of it.

> **Quantization ≠ uncensored.** "Uncensored" is a property of *training* (DeepHat/WhiteRabbitNeo were tuned not to refuse legitimate security work), not a quant — compressing an aligned model (Foundation-Sec, Qwen3) preserves its refusals. Only an uncensored base model can fill the offense role.

> **Models chosen by benchmark, not datasheet.** These are the current picks (mid-2026, open-weight); whether a given Qwen3-4B clears the bar for brokering, or Foundation-Sec for interpretation, is a Checkpoint-5-style empirical question (v1 `tasks.md`). One consolidation to test: a strong Qwen3-4B *might* also cover interpretation, collapsing the real-work stack to two locals (broker+analyst merged, plus offense) — validate against Foundation-Sec on a labeled host before retiring it.

Routing is a fixed model-per-role assignment with a residency + engagement-type dimension: **broker → Qwen3 local (always); deep reasoner → Foundation-Sec local (real) / DeepSeek V4 cloud (practice); offense → DeepHat local.**

**Local model sources & quants (GGUF, sized for the 3060).** All three run one-at-a-time, on-demand; peak is the analyst at ~5 GB against 12 GB — comfortable, with the rest of VRAM free for KV cache/context.

| Role | Model (GGUF) | Quant | ~Size |
|---|---|---|---|
| Broker | [`unsloth/Qwen3-4B-Thinking-2507-GGUF`](https://huggingface.co/unsloth/Qwen3-4B-Thinking-2507-GGUF) | UD-Q4_K_XL | ~2.5–3 GB |
| Analyst | [`fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF`](https://huggingface.co/fdtn-ai/Foundation-Sec-8B-Reasoning-Q4_K_M-GGUF) | Q4_K_M | ~5 GB |
| Offense | [`mradermacher/DeepHat-V1-7B-GGUF`](https://huggingface.co/mradermacher/DeepHat-V1-7B-GGUF) | Q4_K_M | ~4.5 GB |

Practice adds the cloud teacher (`DeepSeek V4`, hosted — prefer a US/EU endpoint). Unsloth's **Dynamic 2.0 ("UD")** quants keep the important layers at higher precision, so `UD-Q4_K_XL` retains more quality than a flat Q4 at nearly the same size — a good pick for the always-on broker.

**Broker model choice — `Qwen3-4B-Thinking-2507`, with an upgrade path.** Among the 4B thinking options, the broker's job (read the *text* graph, query it via tools) decides it:
- **`Qwen3-4B-Thinking-2507` (the pick)** — text-only (no vision capacity wasted on a role that never sees an image), benchmarked tool-calling (~71% BFCL-v3), 256K native context, thinking mode, and — a plain dense model — the most mature, stable local-runtime support. For the *always-on constant*, reliability and no-wasted-capacity win.
- **`Qwen3.5-4B-MTP` (upgrade path, [Unsloth GGUF](https://huggingface.co/unsloth/Qwen3.5-4B-MTP-GGUF))** — newer and faster (MTP = multi-token prediction), more capable, 262K context, but natively multimodal (vision unused here), drops Qwen3's `/think` soft-switch, and its hybrid GDN+MoE architecture is newer/less battle-tested in local GGUF runtimes. Benchmark it as a drop-in later; because the broker is a stable interface, swapping it is a cheap change.
- **`Qwen3-VL-4B-Thinking-1M` (only if you want vision, [Unsloth GGUF](https://huggingface.co/unsloth/Qwen3-VL-4B-Thinking-1M-GGUF))** — vision + 1M context, but vision is dead weight for the broker and 1M context won't fit the 3060's KV cache anyway. If you ever want vision (screenshots, error pages, network diagrams), give it its *own* role rather than bending the broker.

> **Context on 12 GB, in practice.** The 256K/1M native windows are aspirational on a 3060 — the KV cache, not the weights, is the limit. Expect to cap the broker's context to ~32–64K (with KV-cache quantization if you push higher). That's still ample for the wide-read → brief-of-pointers job, which is *why* the broker hands the specialists pointers instead of dumping the whole graph.

### 4.1 Deployment

**Local (three models, all on-demand, one on the GPU at a time).** All three ship GGUF for Ollama / LM Studio: the broker `Qwen3-4B-Thinking-2507` (Unsloth, ~2.5–3 GB), the analyst `Foundation-Sec-8B` (~5 GB), and offense `DeepHat-V1-7B` (Qwen2.5-Coder-7B base, ~4.5 GB). On the reference 3060 they time-share the card (§4.2) — none resident. Sources and quants are in the §4 table.

**Cloud (the practice teacher).** DeepSeek V4 as a hosted OpenAI-compatible endpoint — Hermes, being model-agnostic, points at `https://host/v1`. **Used only on practice engagements** (labs/CTF/HTB/THM); prefer a US/EU host. Real work never calls it (§4).

**Self-hosted teacher (optional, needs a server).** To run the teacher locally instead of hosted, note V4 is open-weight but large — V4-Flash needs ~96 GB VRAM / 128 GB unified, not a 3060. On a server GPU you'd self-host via vLLM/Docker and point Hermes at it. On the reference box, practice uses the hosted teacher and real work uses the local stack.

Match format to runtime: GGUF + Ollama for the local stack; a hosted or vLLM endpoint for the practice teacher.

### 4.2 Reference deployment (RTX 3060 12GB / Ryzen 7 7700 / 32GB DDR5 / Pop!_OS)

This is the target build. The GPU hosts **one local model at a time**, on demand — so the three-model stack fits comfortably even though any single model is 3–5 GB, and real work needs no cloud at all:

- **Runtime:** Ollama (GGUF), not vLLM. The 3060 is Ampere; llama.cpp/Ollama with partial offload fits it, and Ollama's keep-alive timer gives the load-on-demand / auto-unload behavior directly.
- **VRAM budget — single-tenant, on-demand.** Broker `Qwen3-4B` ≈ 2.5–3 GB; analyst `Foundation-Sec-8B` Q4_K_M ≈ 5 GB; offense `DeepHat-7B` Q4_K_M ≈ 4.5 GB. **Only one is loaded at a time** (broker → analyst → offense, as the task moves), so peak GPU model use is ~5 GB against 12 GB — comfortable room for KV cache, a larger context, and the ~0.5–1 GB the desktop holds. The HardwareArbiter (Auto-Recon §8.1) time-shares the card: wake the broker to scope the graph, unload, wake the analyst to plan, swap in offense when you need an artifact. Recon **tools run in parallel on CPU/RAM and never touch the GPU.**
- **Practice teacher:** DeepSeek V4 via a hosted API (prefer a US/EU host) — no local VRAM, **practice engagements only**. Real engagements run the local stack with no network dependency (§4).
- **Don't thrash:** batch interpretation and lean on the keep-alive window so the model stays warm through a burst and unloads after idle — swapping per-finding costs more in load latency than it saves (Auto-Recon §8.1).
- **Context:** with only one local model on the card at a time, interpretation can afford a larger local context (~16–32k); the atomic-retrieval discipline keeps it lean regardless.
- **Embeddings:** a small model (`bge-small` / `nomic-embed-text`, ~0.1–0.5GB) resident at negligible cost, or on CPU.
- **System RAM (32GB):** holds the SQLite stores, the RAG corpus, tool-output buffers, and the Docker sandbox side by side — and this is where the *data-size* headroom lives (the "large data" OOM risk is RAM/storage, handled by streaming + the non-LLM filter + SQLite persistence, not by GPU management).
- **Sandbox:** Docker on Pop!_OS for tool/PoC execution (§13.2).

Net: with only one local model resident at a time and scanners GPU-free, the 3060 comfortably runs the local side of the copilot **and** continuous recon — without the multi-resident-model OOM risk the earlier all-resident plan carried. On practice the cloud teacher is off-box; on real work the whole stack is local.

### 4.3 Working with small models (anti-laziness)

7–9B models, especially at Q4, are prone to **laziness**: generic hand-waving instead of a concrete payload, placeholder code (`# implement the rest`), stopping at "…and so on", giving up after one attempt. You do not fix this by prompting more politely — you engineer it out at the system level:

- **Atomic decomposition.** Ask one concrete thing at a time. Small models collapse on "do this whole complex thing" but execute narrow single-step asks well. The orchestrator splits a request into sub-asks — this is the v2.5.0 hierarchical-decomposition idea repurposed as prompt structuring (not autonomous control).
- **Grammar-forced concrete output.** Constrain generation to a template with required fields (exact command, payload, next step) via llama.cpp / Ollama GBNF grammars (or JSON mode). The model becomes *unable* to emit "…and so on" — it must fill the field. This is the v2.5.0 FormExecutor determinism turned into an anti-laziness device.
- **Verify-and-retry.** A cheap post-check flags placeholders ("TODO", "implement here", trailing "…"), missing payloads, or incomplete code and auto-re-prompts ("be concrete, exact X, no placeholders") before the answer reaches the operator.
- **RAG as scaffold, not just recall.** Inject a concrete past payload/technique as a worked example. Small models are good at *mutating* a concrete example and bad at generating from a blank page, so the infinite-brain doubles as an anti-laziness crutch — the adapt-first step (§7) twists a retrieved template rather than starting empty.
- **Route hard reasoning to the deep reasoner.** The adapt-first "think" step (§7, Step 3) goes to the deep reasoner — **DeepSeek V4** at higher reasoning effort on practice, **`Foundation-Sec-8B`** on real work (§4) — so it reasons step-by-step instead of jumping to a lazy answer. (This anti-laziness discipline matters most for the *local* models — the broker, analyst, and offense — which are the small ones prone to it.)
- **Stamina lives in the orchestrator, not the model.** A 7B will not "keep going" across a long task. The system holds the to-do / hypothesis list (§5.1) and advances to the next atomic sub-task itself. Persistence is a state-machine property, not a model property.

### 4.4 Long-haul operation — the copilot-side endurance mechanisms

The copilot's marathon risks are — **on practice** — the cloud-teacher dependency, plus (both modes) context drift over hundreds of turns and hallucinated facts polluting the graph (Main Proposal §4.2 is the spine; recon's mechanisms are Auto-Recon §8.2).

**Resilient cloud client — the practice teacher as a supervised dependency.** V4 is called *only on practice engagements* (§4); those calls go through a client that treats the API as *expected to fail* (real work is all-local, so this section doesn't apply there):

- **Retry with exponential backoff + jitter** on transient errors (5xx, timeouts), and **request timeouts** so a slow call never hangs the loop.
- **Circuit-breaker.** After repeated failures the breaker opens — stop hammering the API, fail fast — and half-opens periodically to test recovery, closing when it returns.
- **Self-throttling** against the provider's rate limits (token/req budgets), so a busy practice marathon doesn't trip 429s in the first place.
- **Runtime degrade to a local reasoner** (the broker, or `Foundation-Sec` for depth) on breaker-open or sustained failure. A lab outage at hour 14 becomes "the copilot quietly drops to local reasoning and recovers to the cloud teacher when the breaker closes," never a stall. The operator is told which reasoner is live. *(Honest limit: while degraded, teaching-grade reasoning is weaker for the outage's duration — resilient ≠ lossless.)*

**Bounded, re-grounded context.** Over hundreds of turns a free-text rolling summary bloats and drifts (lost coherence, repeated work). Instead of growing a blob, the engagement state (§5.1) is **periodically regenerated from the graph** — the working context is *reconstructed* from the current hot-set facts, open candidates, and recent decisions on a cadence, so it stays bounded and stays *true to the graph* rather than accumulating narrative drift. Atomic retrieval (§7) keeps each prompt's context small regardless of how long the session has run.

**Write-back verification gate + provenance quarantine.** V4's hallucination rate means some outputs are wrong; the danger is a bad fact entering the shared graph via enrichment/interpretation and silently becoming ground truth. The gate keys on **verification and corroboration — not the model's self-reported confidence**, which is uncalibrated and near-meaningless from a small model (a "0.9" from an 8B tells you little). So every LLM-originated fact is:

- **Tagged with a provenance *class*** on write — `operator-confirmed` > `tool-observed` > `model-asserted` (the `provenance`/`source` field, §6/§9-recon). This authority order is the precedence rule the whole graph uses (Auto-Recon §8.2): a lower-authority writer never overrides a higher one.
- **Promoted only by a real signal, never by a number.** A `model-asserted` fact leaves quarantine only when something *checks* it: a deterministic validator confirms it (e.g. the CVE exists and matches, Auto-Recon §5.2), an independent source corroborates it, or the operator confirms it (§7.9). Self-confidence is at most a weak tiebreaker for ordering what to verify first — never the gate itself.
- **Down-weighted while quarantined** — a `model-asserted` fact carries less weight in reasoning and **never satisfies a precondition on its own** the way an operator-confirmed fact does.
- **Re-verified-or-expired** by the reconciliation pass (Auto-Recon §8.2): a `model-asserted` fact that no check ever corroborates ages out rather than persisting. A hallucination is thus *quarantined and self-expiring*, not permanent. *(Honest limit: this contains propagation to near-none; it does not lower V4's source rate — nothing at the architecture layer can.)*

---

## 5. Memory Architecture (the crux)

**The knowledge layer — the four stores, the `engagement` / `general` scope model, retrieval, and the five flows — is owned by the Knowledge-Architecture Blueprint.** This section covers only how the *Copilot* uses it. The anti-collision rule it inherits: **single source of truth per data type** — the boundary is drawn by *what kind* of knowledge it is. The stores the Copilot touches (full model there):

| Store | The Copilot's use of it | Source of truth for |
|---|---|---|
| Hermes memory | reads past sessions; distillation reads it | What you did, when, in which session |
| Infinite-brain graph | reads all scopes; writes confirmed + distilled facts | Techniques, vulns, CVEs, targets, and how they relate |
| Working memory | the live session — forms the query into the above | The query into long-term stores |

**Working memory** is not a separate component — it *is* the current Hermes session: this target, the goal (e.g. "exploit BOLA"), the constraints (e.g. "no info disclosure on this system"), and what has already failed. This live context is what forms the query into long-term memory, and — critically — it is what gets compared against a stored technique's preconditions to decide applicability (§7).

**The bridge: distillation.** Hermes remembering *that you did a thing* is not the same as the graph knowing *the conditions under which the thing works*. After a confirmed success, a distillation step reads the experience Hermes just logged and writes the durable, structured facts into the graph (§7, write-back). This bridge is where the Copilot adds value over a vanilla Hermes install.

### 5.1 Engagement state (long-duration continuity)

A real engagement runs for **days across many sessions** — far longer than any model context window or single Hermes session. The three stores above cover knowledge (graph), session logs (Hermes), and the immediate query (working memory), but none durably holds *the live state of one multi-day campaign*: the enumerated attack surface, the open hypotheses, what has been tried and ruled out, and where you are in the kill chain. Without it, you lose the thread between sessions — the single sharpest limit past 24h.

Model it **without adding a new store**:

- **Engagement-scoped subgraph.** The campaign's state lives as `engagement`-scoped nodes/edges in the graph (§6.3 scope class): the `target`(s), `finding`s, open `question` nodes, and tried techniques as `found_on` / `failed_on` edges. Durable — it survives session resets, machine sleeps, and the multi-day timeline.
- **Rolling summary.** The orchestrator maintains a compact, continuously-updated summary of the engagement (current surface map, top hypotheses, immediate to-do) sized to fit the small model's context. This is the anti-overflow mechanism: long sessions never blow the window because the model sees the summary, not the raw history. (Optionally a slimmed, state-only descendant of the v2.5.0 EngagementTreeView — kept as a *state* structure, not the retired orchestration.)
- **Resume.** Opening a new session on an existing engagement loads the rolling summary plus the engagement subgraph, so the copilot picks up where you left off instead of cold.

When the engagement ends, its *general* lessons distill into general-scope graph nodes (a new technique, a precondition refinement); the engagement-scoped record is archived.

---

## 6. Domain Knowledge Graph Schema

This section owns the graph's **node and edge types** (referenced by the Knowledge-Architecture Blueprint §3). The `scope` dimension on every node (`engagement` vs `general`), the store/retrieval model, and the flows are owned *there*, not here.

The infinite-brain *principles* are kept — atomic nodes, typed nodes, typed directional edges, trust metadata, scoped retrieval. The generic PKM taxonomy is **not** kept verbatim; it is replaced with offensive-security types.

### 6.1 Node Types

| Type | Purpose | Key fields |
|---|---|---|
| `vulnerability` | A vulnerability *class* (e.g. BOLA, SSRF) | name, OWASP/CWE ref, summary |
| `cve` | A specific CVE | id, CVSS vector + score, affected versions, summary |
| `technique` | A concrete method that exploits a vuln | summary, **preconditions**, steps-ref, reliability |
| `target` | A system / app / endpoint under test | name, scope-ref, observed properties |
| `payload` | A reusable payload / request shape | content-ref, applies-to (vuln/technique) |
| `tool` | An external tool used | name, invocation notes |
| `finding` | A confirmed observation on a target | description, severity, evidence-ref |
| `writeup` | An external solution / article / report | title, url, key takeaway |
| `concept` | A defined term the agent should know | definition |
| `source` | An external reference / persona | type, url-or-cite |
| `credential` | A captured/confirmed secret that can satisfy preconditions | kind (password/hash/token/key), principal, scope (where it works), source (operator/recon), status |
| `defense` | An observed defensive control on a target | type (WAF/rate-limit/filter/EDR/auth-control), identity, behavior, evidence-ref |

The single most important field is `technique.preconditions` — the structured statement of *what must be true on the target* for the technique to apply (e.g. "object IDs are leaked / discoverable"). Without it, retrieval returns techniques that do not actually fit (§7).

### 6.2 Edge Types

Directional, weighted, `A → B`.

| Edge | Meaning (A → B) | Weight |
|---|---|---|
| `exploits` | A (technique) exploits B (vulnerability) | 1.0 |
| `depends_on` | A is valid only if B holds (precondition link) | 1.0 |
| `chains_with` | A combines with B to form an attack chain | 1.0 |
| `affects` | A (cve/vuln) affects B (target/component) | 1.0 |
| `mitigated_by` | A is neutralized by B (control) | 1.0 |
| `satisfies` | A (credential/finding) makes true a precondition of B (technique) — the missing link that unblocks it | 1.0 |
| `found_on` | A (finding/technique) was used/found on B (target) | 0.5 |
| `failed_on` | A (technique) was tried on B (target) and did **not** work — carries the reason (e.g. precondition absent) | 0.5 |
| `derived_from` | A was created from B (e.g. a scouted writeup) | 1.0 |
| `variant_of` | A is an alternative form of B (never an overwrite) | 0.5 |
| `superseded_by` | A no longer works (patched/stale); B is the current replacement — A is kept, not deleted | 0.5 |
| `related_to` | Topical link, nothing stronger | 0.5 |
| `tagged_with` | A is tagged with topic-node B | 0.2 |

`variant_of` enforces the never-overwrite rule (§7): a new technique that solves the same vuln under different preconditions is a *variant*, not a replacement. `failed_on` captures **negative knowledge** — failures are evidence about preconditions, so a `failed_on` edge (with its reason) both warns "you already tried this here" and sharpens the precondition model retrieval depends on. `superseded_by` handles deprecation without deletion: a patched or stale technique stays in the graph (history matters) but is flagged so retrieval can de-rank it.

**Exploit candidates are computed, not stored.** A candidate's *condition status* and *feasibility* (ready / conditional / blocked) are derived **live** by evaluating `technique.preconditions` against the target's known facts (`finding`, `credential`) and its `defense` nodes: a precondition is met if a `satisfies` edge/fact covers it, and *blocked* if a `technique → defense` `mitigated_by` edge applies (condition: bypass). Because feasibility is a function of current graph state rather than a stored value, it **re-derives automatically the moment enrichment adds a fact** (§7.9) — an operator's confirmed credential flips every candidate it unblocks, with the `satisfies` edge recording *why* it became viable. This is what keeps the attack paths current as the operator works, and it is why `credential` and `defense` had to be first-class node types.

### 6.3 Metadata on Every Node
- **Provenance class (authority):** `operator-confirmed` > `tool-observed` > `model-asserted`. This is the graph's **precedence order** — when two writers disagree (enrichment, reconciliation, recon), the higher class wins and a lower-authority writer *flags* rather than overrides (§4.4; Auto-Recon §8.2). It is the field that actually gates trust; `Trust` below is the coarser who-authored-it label.
- **Trust:** `human` / `ai` / `hybrid` — who authored the content.
- **Confidence:** a *weak* signal only — a self-reported number is uncalibrated and never gates a write on its own; at most it orders what to verify first. Writes are gated by **verification/corroboration**, not this score (§4.4).
- **Status:** `active` / `deprecated` (patched/stale, see `superseded_by`) — lets retrieval de-rank dead knowledge without deleting history.
- **Scope class:** `general` (shareable across engagements — techniques, vulns, CVEs, concepts) vs `engagement` (client/target-specific — findings, targets, payloads). Drives the isolation rule in §11.
- **Timestamps:** created / last-confirmed — the freshness signal curation uses (§13.1), and the input to reconciliation's staleness horizon (Auto-Recon §8.2).

### 6.4 Storage
Back the graph with a queryable store (SQLite or a graph DB) so the `graph_query` server can traverse edges across hundreds of nodes. Markdown + YAML (Obsidian) is acceptable **only** as a human-readable frontend layered on top — never as the sole store, or edge traversal at scale becomes impossible.

---

## 7. Retrieval and Reasoning Loop

This formalizes the BOLA scenario. The query is built from working memory; results are matched **on preconditions**, not on vulnerability name alone.

**Delivery principle — mode-aware (teach on labs, support on real work).** The *posture* of an answer follows the reasoner in play (§4):
- **Real work (local reasoner, support):** solution first. While a live engagement runs, the copilot *delivers* the actionable thing — the request, the payload, the concrete steps — not a walkthrough. The operator is in flow and wants it to run, not a lecture; explanation is deferred to confirmed success (Step 6), where it doubles as the reasoning distilled into the graph. (Exception: a one-line safety/scope caveat if running it blindly could exceed scope.)
- **Practice (cloud reasoner, teacher):** explanation *is* the deliverable. On a lab/CTF/HTB/THM target the goal is skill, so the copilot leads with the deep *what / why / how* — why this technique fits these preconditions, why the adaptation works, what the failure taught — not just the runnable answer. Here the "lecture" is the point.

**Grounding guard — deterministic, not just a prompt.** When the copilot answers *from the graph* (the query path, and §-recon handoff answers), the anti-hallucination instruction in the prompt is backstopped by a deterministic check: named entities in the answer (hosts, ports, CVEs, credentials) are extracted and cross-checked against the retrieved fact set; any that are **not** present are flagged or stripped before the answer reaches the operator. A prompt can only *reduce* invention; this makes "no invented assets" an *enforced* invariant rather than a hope — the same model-proposes/parser-disposes discipline as recon's CVE validation (Auto-Recon §5.2). Especially load-bearing given the cloud model's high raw hallucination rate.

**Step 1 — Query.** From working memory, query the graph for techniques where `exploits → <vuln>` (e.g. BOLA), and compare each candidate's `preconditions` against the current target's observed properties.

**Step 2 — Branch on the result.**

- **Match** (a technique exists *and* its preconditions hold on this target): deliver it as-is.
- **Mismatch** (a technique exists but its preconditions do *not* hold — e.g. the known BOLA technique `depends_on` info disclosure, which this target lacks): enter the **adapt-first** path (Step 3).
- **Not found** (no technique for this vuln): scout the web (Step 4).

**Step 3 — Adapt-first (the "think" step).** Before scouting, the copilot reasons. It takes the known technique as a starting point and tries to twist it using *other* knowledge in reach — `related_to` techniques, applicable `cve` nodes, CVSS attack-vector details, payloads, and chains — to substitute the failing step. In the BOLA example: keep the broken-object-authorization core, but replace the "IDs come from an info-disclosure leak" step with another way to discover IDs (sequential/predictable identifiers, IDs leaked elsewhere, enumeration, etc.).
  - If a viable adaptation is formed → deliver it to the operator as a runnable solution.
  - If adaptation is exhausted and nothing viable forms → the branch **collapses into Not found** and proceeds to scout (Step 4).

**Step 4 — Scout.** Search/fetch the web for a solution (§10), tag its provenance for later `derived_from` linkage, and **deliver the solution** to the operator — actionable form, not an explanation.

**Step 5 — Deliver and execute.** The copilot hands over the solution (Match technique, adapted variant, or scouted method) as something the operator can run directly. The operator executes. The copilot does not.

**Step 6 — Confirm, explain, write back (human-gated).** On operator-confirmed success, the copilot *now* explains what worked and why — and that explanation is the same reasoning that gets distilled into the graph:
- A **new** `technique` node with its own `preconditions` (never an overwrite of the old one).
- Edges: `exploits → <vuln>`, `found_on → <target>`, `variant_of → <prior technique>` if it is an alternative form, and `derived_from → <writeup/source>` if scouted.

Coupling the explanation to the success moment is deliberate: the "why it worked" the operator hears is exactly the precondition-and-reasoning content the graph needs to store, so the teaching step and the distillation step are one and the same.

**Step 6b — Capture failure (when it did *not* work).** If the operator reports the candidate failed, that is recorded too: a `failed_on` edge from the technique to the target, tagged with the apparent reason (e.g. "precondition P absent", "WAF blocked", "patched"). This is negative knowledge — next time, retrieval can warn "you already tried this here and it failed," and the failure refines the precondition model. A repeated, generalizing failure is the signal to mark the technique `deprecated` / `superseded_by` (§6). Failure capture is human-gated like any other write.

**The never-overwrite rule.** Two techniques for the same vuln coexist, indexed by different preconditions. Over many engagements this builds a precondition-indexed library of *what works when*. That is the payoff: the next engagement, retrieval picks the technique whose preconditions match the target in front of you.

**Write gating.** Graph *reads* are free. Graph *writes* pass the **verification gate** (§4.4) — a deterministic check, an independent corroboration, or a one-tap operator confirmation — **not** a self-reported confidence number. This is the human-confirm-on-write rule and it is what keeps the brain from filling with techniques that looked right but never landed. (Your own flow already gated writes on "after confirm success" — this formalizes it.)

### 7.8 Attack-path brainstorming (defenses factored in)

The **deep reasoner** for this step is set by engagement type (§4): **Foundation-Sec-8B** on real work, **DeepSeek V4** (the teacher) on practice. Either way it does not read the whole graph — it consumes the **broker's task-scoped brief** (Qwen3, §4), dereferences the pointed-to facts (findings, candidates, defenses) straight from the graph, and spends its context on the plan. On practice the teacher additionally explains the *what/why/how* so the brainstorming doubles as instruction.

When recon hands off, findings arrive enriched with **exploitability** and **defensive posture** (Auto-Recon Blueprint §5.7). The reasoner uses these to brainstorm attack paths *with* the operator — advisory, never autonomous. The enrichment is what makes the brainstorming realistic: not "here are the vulns" but "here is which are viable given their defenses, and how to get around the defense."

- **Reason over vuln + exploitability + defense together.** A finding with a public exploit but a WAF in front is a different proposition than the same finding undefended. The copilot surfaces the constraint and the options: WAF-bypass approaches, an unprotected pivot (an endpoint on a different IP not behind the WAF), or a quieter alternative path.
- **Rank by viability, not just severity.** An offline-crackable Kerberoast (no network detection) may outrank a higher-CVSS web bug behind heavy filtering. The defense profile is a first-class input to prioritization.
- **Bypass-aware.** Where a defense blocks the obvious route, the copilot retrieves applicable bypass techniques from the knowledge base (the same precondition-indexed retrieval as Steps 1–3) rather than declaring the path dead.
- **Advisory and human-driven.** The copilot proposes ranked paths with the trade-offs; the operator evaluates, chooses, and executes. This is the planner in advisor mode — it brainstorms the chain, it does not run it (the skill-amplifier and fenced-autonomy principles).

This is the depth-side payoff of recon's §5.7 enrichment: the breadth engine characterizes the situation, and the copilot turns it into a ranked set of viable, defense-aware plays for the operator to drive.

**How the plan is generated (the method).** Three layers, each doing what it is best at:
- **Graph-enumerated candidate chains.** The precondition graph enumerates *candidate* attack chains — where one candidate's postcondition satisfies the next's precondition — **bounded** (max depth / max branches) so enumeration cannot combinatorially explode.
- **LLM-reasoned feasibility and narrative.** The reasoner evaluates the enumerated chains for viability with defenses factored in, proposes bypasses for blocked steps, ranks by viability, and writes the human-readable plan — grounded in the enumerated chains, not free-invented.
- **Playbook-backed.** Common patterns (AD: kerberoast → crack → lateral; web: `.git` → source → IDOR) match a library of known plays and are adapted, rather than re-derived each time.

The result is advisory: enumerated + reasoned + pattern-matched candidate plans, ranked, with the operator choosing and executing.

### 7.9 Operator findings: confirm and enrich (the feedback loop)

The engagement graph is a **living, shared model** that both the recon engine (breadth) and the operator (hands-on depth) populate. When the operator discovers something by manual testing that recon could not — a working credential, a confirmed vulnerable behavior, a new subdomain/host/parameter — they hand it to the copilot, which runs a two-part **confirmation** and then enriches the shared model:

1. **Confirm by reasoning.** The copilot walks the finding against everything known — consistency with the existing surface, plausibility, what it would imply — toward the explicit question "is this actually real?"
2. **Confirm actively.** It backs that with a *targeted* verification against the target (e.g., authenticate with the credential to confirm a session) — a single check, not a recon pass.
3. **Write the fact in.** On confirmation, the finding is persisted to the shared graph as a first-class node/attribute (`credential`, `finding`, new asset), with provenance = operator + confirmation evidence.
4. **Re-activate what it unblocks.** The copilot queries the graph for steps and candidates blocked on the missing info the fact supplies — these already exist as unmet-precondition records and coverage-ledger gaps (§7.4 of the Auto-Recon Blueprint), so no separate checklist is maintained. Exactly those are re-activated: the engine re-runs the specific blocked steps, and any newly-opened surface is mapped by its normal expansion loop.
5. **Re-derive paths.** Because everything is precondition-linked, the new fact can flip candidates from *blocked* → *ready* and open new chains; the planner (§7.8) re-derives the attack paths. The map sharpens as the operator works.

**Why enrich the one shared model rather than spawn a second recon:** the "explore where this leads" intuition is served by feeding the fact into the single engine's expansion loop — which is precise (re-activates exactly what the fact unblocks), efficient (targeted tasks onto the running queue, not a second engine contending for the one GPU), and coherent (one graph, no merge/de-conflict). A separate parallel recon would only win if it ran on separate hardware.

This **enrichment** channel is distinct from **steering** (Main Proposal §3.3): steering aims the scanners; enrichment feeds the model. Both keep the operator in control — enrichment never auto-acts on the finding, it confirms and records it so the paths get clearer.

---

## 8. MCP Server Contracts

The knowledge layer is exposed to Hermes as MCP servers, so it stays independently testable and portable (the same servers can later feed the Orchbiter project). Contracts are conceptual, not final signatures.

### `graph_query` (read)
- `find_techniques(vuln, target_properties)` → ranked candidates, each with `{technique, preconditions, applicability: match | mismatch}`.
- `traverse(node_id, edge_type, depth)` → connected nodes.
- `get_node(node_id)` → node body + metadata.

### `graph_write` (write, human-gated)
- `propose_node(type, fields, provenance_class)` → staged node id. Promotion out of quarantine is by the **verification gate** (§4.4) — a deterministic check, an independent corroboration, or an operator confirmation — **not** a self-reported confidence threshold.
- `link(a_id, edge_type, b_id, weight)` → edge id.
- Enforces never-overwrite: a same-vuln technique under new preconditions is created as a node + `variant_of` edge, never an update-in-place.

### `retrieve` (RAG, read)
- `search(query, k)` → top-k passages from the corpus (writeups, articles, CVE text) for context injection.

### `cve_lookup` (read — salvaged from v2.5.0)
- `lookup(cve_id)` → CVSS vector/score, affected versions, summary.
- `search(keyword)` → matching CVEs.

### `scout` (read + ingest)
- `search_web(query)` / `fetch(url)` → raw content.
- `propose_ingest(content)` → routes content into the corpus and proposes graph nodes (held for confirmation).

---

## 9. Skills

CTF know-how lives as native Hermes skills in `agentskills.io` format — portable, shareable, and the path Hermes is designed for. Skills are **procedural** ("how to enumerate for SQLi", "heap-pwn approach", "BOLA ID-discovery playbook"); the graph is **declarative** ("this technique works when these preconditions hold"). Keep the two distinct: a skill is a repeatable process, a graph node is a fact about what relates to what.

**CTF skills are not enough — IRL pentest needs a different spine.** CTF skills optimize for "find the flag fast." Real engagements need skills grounded in recognized methodology so coverage is systematic, not ad-hoc:

- **Base skills on frameworks, not invention:** PTES, OWASP WSTG (web), the OWASP API Security Top 10, NIST 800-115, and the practical references actually used in the field — HackTricks and PortSwigger's Web Security Academy. These define the skill set.
- **Cover the domains CTF underweights:** Active Directory (Kerberoasting, AS-REP roasting, ACL abuse, BloodHound paths, DCSync, lateral movement) — the single biggest CTF→IRL gap; cloud (AWS/Azure/GCP); business-logic flaws; and **reporting + responsible disclosure**, which is the actual deliverable in pentest and bug bounty.
- **Each skill is a methodology playbook, not an exploit** — trigger, steps, tools, what to record — which keeps it copilot-shaped and safe.
- **Index every skill on MITRE ATT&CK.** ATT&CK is the shared taxonomy across skills, the graph's technique nodes (§6), and Foundation-Sec (which understands it natively) — one vocabulary instead of three.

Skills the learning loop refines over time become more valuable as the graph that informs them grows richer.

---

## 10. Ingestion ("Scout the Internet")

Ingestion is a pipeline, not a new subsystem. Web search / fetch / browser (Hermes already has the tools) → dedupe → write into:
1. The **corpus** behind `retrieve` (RAG index) — latest CVEs, ExploitDB PoCs, advisories, CTF writeups.
2. **Proposed graph nodes** via `graph_write.propose_ingest` — held for operator confirmation before they become trusted nodes.

Continuous *knowledge* refresh (new CVEs, new writeups) is appropriate to run as a Hermes cron job or subagent. The *engagement* loop (§7) stays interactive. This is the line between "the brain stays current on its own" and "the copilot never acts on a target without you."

---

## 11. Guardrails

Two kinds of limitation, and only one is removed:

- **Removed:** corporate-policy refusals on legitimate offensive work — handled by the local uncensored model (§4).
- **Kept:** operational guardrails — the AuthorizationManager scope check and the audit trail, both salvaged from v2.5.0.

Scope enforcement keeps activity inside what is authorized (the bug-bounty scope, the CTF target, the engagement letter). The audit trail produces a defensible record — useful for bug-bounty submissions and for your own review. These cost nothing in capability and are the difference between a professional tool and a liability.

### 11.1 Engagement scope isolation

The brain is global on purpose — *general* knowledge (techniques, vulns, CVEs, concepts) is meant to compound across every engagement. But *engagement-specific* data (findings, targets, payloads tied to one client) must not leak across scopes. The `scope class` field (§6.3) draws the line:

- **General nodes** retrieve freely across engagements — that's the point of the library.
- **Engagement nodes** are tagged to their program and surface only within that program's sessions. A finding on client A's target never appears while testing client B.
- The copilot never proposes an action against anything outside the *currently authorized* scope, even if a relevant `engagement` node exists from past work. Out-of-scope is a hard stop, not a suggestion.

This keeps the cross-engagement learning that makes the copilot valuable while preventing both data bleed and accidental out-of-scope activity — an operational and a legal safeguard at once.

---

## 12. Technology Stack

Consolidated view of the tools and technologies, **default choice in bold** where options exist. Open choices are picked at the phase noted in §13.

### 12.1 Runtime and integration
| Component | Choice | Purpose |
|---|---|---|
| Agent runtime | **Hermes Agent** (Nous Research) | Harness: working memory, learning loop, skill engine, tool routing |
| Tool protocol | **MCP** (Model Context Protocol) | Exposes the knowledge layer and external tools to Hermes |
| MCP SDK | **Python FastMCP** (Node/TS MCP SDK acceptable per-server) | Build the `graph_query` / `graph_write` / `retrieve` / `cve_lookup` / `scout` servers |
| Skills format | **agentskills.io** | Portable CTF procedures the learning loop refines |

### 12.2 Models and inference
| Role | Model | Serving |
|---|---|---|
| Broker / organizer (constant, both modes) | **Qwen3-4B-Thinking-2507** — local, **on-demand** | Ollama (GGUF, `unsloth/…` UD-Q4_K_XL) |
| Deep reasoner (analyst / planner) | real → **Foundation-Sec-8B** (`-Reasoning`) local · practice → **DeepSeek V4** cloud teacher | Ollama (GGUF) / hosted API (US/EU) |
| Offensive artifacts | **DeepHat-V1-7B** (formerly WhiteRabbitNeo) — local, **on-demand**, uncensored | Ollama (GGUF, `mradermacher/…`) |
| Inference (local) | **Ollama** (or LM Studio) | Local GGUF, single-tenant GPU (§4.2, Auto-Recon §8.1) |
| Embeddings | A local embedding model (**bge** / nomic-embed) | Vectorize corpus + queries for RAG |

### 12.3 Knowledge and memory stores
*Architecture, scope model, retrieval, and the RAG roadmap are owned by the Knowledge-Architecture Blueprint (its §2, §5, §14); this table lists the Copilot's concrete tech defaults for those stores.*

| Store | Default | Alternatives | Purpose |
|---|---|---|---|
| Domain graph | **SQLite (graph schema)** | KuzuDB (embedded graph), Neo4j | The infinite-brain: typed nodes + edges |
| Vector index (RAG) | **sqlite-vec + SQLite FTS5** (hybrid: dense + lexical, one file) or LanceDB | FAISS, Chroma, Qdrant | Semantic + keyword retrieval over the corpus |
| Embedding model | **BGE-M3** (dense + sparse + multi-vector from one model, MIT) | Qwen3-Embedding (code-tuned), nomic-embed-text (Ollama-native) | Vectorize corpus + queries for hybrid RAG |
| Reranker | **BGE-reranker-v2-m3** | Qwen3-Reranker | Cross-encoder rerank → inject only the top-k into a small context |
| Hermes memory | **SQLite + FTS5** (built into Hermes) | — | Experiential / session memory |
| Human-readable view | Obsidian over markdown + YAML | — | Optional browse layer; never the source of truth (§6.4) |
| Audit log | **Append-only SQLite / JSONL** | — | Defensible engagement record (salvaged from v2.5.0) |

Keeping the graph, the vector index, the audit log, and Hermes memory all on SQLite (or SQLite-family) keeps the whole stack local-first, file-based, and dependency-light — fitting the "LLM on your laptop" goal.

**Retrieval shape.** Hybrid (dense + lexical), graph-primary, reranked — the full model is owned by the Knowledge-Architecture Blueprint §5, with the DIY-then-upgrade roadmap (`txtai` / `LLMWare` / `RAGatouille-ColBERT`) in its §14. In short: the graph answers first; RAG is the text fallback; hybrid is mandatory because security/code text is full of exact tokens (CVE IDs, versions, payloads) that pure-dense embeddings miss; and do **not** adopt an auto-extraction GraphRAG framework — the curated typed graph (§6) already does the graph job better for this domain.

### 12.4 Data sources (feed `scout` and `cve_lookup`)
- **Vulnerability / CVE data:** NVD API, OSV.dev, GitHub Advisory Database, VulnCheck — CVSS vectors come from the same feeds.
- **Exploit references:** ExploitDB, public PoC repositories.
- **Taxonomies:** MITRE ATT&CK, CWE (Foundation-Sec already understands these natively).
- **Techniques / writeups:** web search + fetch over CTF writeups, research blogs, and advisories.

### 12.5 Scouting and execution
- **Web retrieval:** Hermes web search / fetch; browser automation (Playwright) for JS-heavy sources.
- **Sandboxing:** Docker / SSH / local sandbox via Hermes, for running tools safely.
- **Operator tooling (you invoke; optionally wrapped as MCP):** nmap, ffuf / gobuster, Nuclei, sqlmap, Burp Suite, and similar. The copilot advises and prepares commands; you execute. Recon/scanner MCP wrappers salvaged from v2.5.0 live here.

### 12.6 Implementation language
**Python** for the MCP servers, the ingestion/distillation pipeline, and glue — it has the richest security and ML ecosystem. Individual MCP servers may be Node/TypeScript if preferred.

### 12.7 Hardware
NVIDIA GPU + CUDA. The reference 3060 runs the local stack — broker (`Qwen3-4B`), analyst (`Foundation-Sec-8B`), offense (`DeepHat-7B`) — **one at a time** at 4-bit (§4.1/§4.2). The cloud teacher (practice only) is hosted, or self-hosted on a server GPU via vLLM/Docker if you want it local.

---

## 13. Robustness and Operations

The core loop works; these are the things that keep it working as the brain grows and as it touches the untrusted internet.

### 13.1 Graph curation (the counterpart to never-overwrite)

Never-overwrite means the graph only grows, so it needs active curation or retrieval quality decays:

- **Dedup / merge.** Different sessions will create near-identical nodes (two `technique` nodes for the same method, two `cve` nodes for one CVE). A periodic pass (embedding-similarity + same-vuln heuristic) flags candidates; merges are human-confirmed. Merging preserves all edges from both nodes.
- **Deprecation.** When a technique stops working (patched, generalizing `failed_on` signal), mark it `deprecated` and add `superseded_by`. It stays for history; retrieval de-ranks it.
- **Freshness.** `last-confirmed` timestamps let retrieval prefer recently-validated knowledge and surface stale nodes for review. A CVE technique unconfirmed in a year is a review candidate, not an automatic trust.
- **Cadence.** Curation is a Hermes cron/subagent job (like ingestion, §10) — never part of the live engagement loop.

### 13.2 Self-security (the copilot threat-models itself)

The copilot ingests untrusted internet content and feeds an LLM that proposes commands. Treat that as an attack surface:

- **Scouted content is data, not instructions.** Content pulled by `scout` (writeups, CVE pages, PoCs) is wrapped/marked as untrusted on its way into the corpus and graph, so a malicious page cannot inject directives into the model's working context (prompt injection via RAG). Provenance (`derived_from`) is always recorded.
- **Never auto-run scouted code.** A scouted "exploit" may be malware aimed at *your* box. The human-confirm gate (§7) applies, and —
- **All tools and PoCs execute in the Docker sandbox, never the host.** This is what the §4.2 sandbox is for: a scouted or generated PoC runs isolated, with no path to the operator's machine or the brain's stores.
- **Skill/connector trust.** Imported `agentskills.io` skills and third-party MCP servers are reviewed before use — same untrusted-until-checked stance.

### 13.3 Bootstrapping (cold-start)

An empty graph makes every query "not found," so seed it before first use:

- Import structured public data — CVE feeds, MITRE ATT&CK, CWE — as `cve` / `concept` / `vulnerability` nodes.
- Ingest a starter corpus of high-quality writeups into the RAG index.
- Import your own past engagement notes as `technique` / `finding` nodes (this is the manual seeding referenced in §14, P1).

The goal is leverage from the first engagement, not the hundredth.

**Concrete sources (prefer live feeds over static dumps where freshness matters):**
- **CVE / vuln:** live — NVD API, OSV.dev, GitHub Advisory DB, CVElistV5. Bulk one-time seed — `AlicanKiraz0/All-CVE-Records-Training-Dataset` (~300k records), then keep current via live ingestion. A stale CVE store is worse than none.
- **Exploits/PoCs:** ExploitDB, Nuclei templates, Metasploit modules (live). Caution: some HF "exploit" dumps contain *synthetic* PoCs crafted from patterns, not real exploits — tag provenance and never treat them as ground truth (§13.2).
- **Taxonomies:** MITRE ATT&CK (STIX), CWE, CAPEC — authoritative, structured, ideal as both graph nodes and retrieval.
- **Expert reasoning (mine, don't train):** Pentest-R1's expert walkthroughs and Primus-Reasoning traces (see §14) can be ingested as corpus / distilled into skills *without fine-tuning* — mine the reasoning, not the weights.

### 13.4 Durability and portability (protect the crown jewel)

The graph is years of accumulated value; losing it is the worst failure mode. Because it is SQLite-family (§12.3):

- **Backup:** periodic snapshots; optionally a git-backed export of the human-readable Obsidian layer for diff-able history.
- **Sync:** a single portable brain file is what makes the laptop↔server hybrid (§4.1) work — the brain travels, the runtime is wherever you are.
- **Schema migrations:** version the schema and keep migration scripts; the node/edge model *will* evolve.

### 13.5 Evaluation (is it actually helping?)

Without measurement there is no way to know the copilot is improving you rather than just accumulating data. Track a few signals:

- **Retrieval hit-rate** — share of queries the graph answers without scouting.
- **Adaptation success-rate** — share of mismatch-branch adaptations (§7, Step 3) that landed.
- **Time-to-solution** — wall-clock from query to confirmed success, over time.
- **Graph health** — node/edge growth, duplicate rate, deprecated share.

Optionally, self-test against public benchmarks to track capability as the brain and skills mature — pick one per dimension rather than running all:
- **CTF dimension:** NYU CTF Bench, Cybench, or Intercode-CTF.
- **IRL pentest dimension:** CVE-Bench (exploit known real-world vulns), AutoPenBench or BountyBench (end-to-end multi-step).
- **Cheap knowledge regression:** CyberMetric, SecEval, or CTIBench (fast checks of the RAG + analysis path).

The curated meta-list `simon-p-j-r/LLM4Pentest` tracks these. This is also a natural bridge to the research venues in the sibling project's scope.

**Regression harness — the counterpart to the parsers' fixture tests (a years-long project *will* swap models and prompts).** The deterministic parsers have fixture tests; the model-dependent behaviors — interpretation quality and grounded answering — have almost none, so a prompt tweak or a model swap can silently regress quality with nothing to catch it. Maintain a small **held-out labeled eval set** and run it on *every* model or prompt change:
- **Interpretation eval** — a handful of hosts with *known* services→CVEs; assert the interpreter identifies ≥ N of M and emits ≤ K false CVEs *after* validation (Auto-Recon §5.2). This is the same objective bar as the slice's Checkpoint 5 (v1 `tasks.md`), promoted to a standing regression gate.
- **Grounded-answer eval** — fixed (question, fact-set) pairs with a known-correct grounded answer; assert zero invented entities get past the grounding guard (§7). 
- **Injection-resistance eval** — findings/tool-output containing embedded instructions; assert they are treated as data.
Run before adopting any new local model, any V4 tier change, or any prompt edit — otherwise "we upgraded the model" quietly becomes "we regressed and didn't notice."

### 13.6 Observability

When the copilot delivers a bad suggestion, you need to see *why*. Capture the retrieval trace (which nodes matched and their applicability verdict) and the deep reasoner's reasoning trace (DeepSeek V4 on practice, `Foundation-Sec-Reasoning` on real work — both emit these) into the audit log, so wrong answers are debuggable rather than mysterious.

### 13.7 Realistic expectations and limits

Honest scope-setting, so the tool is used for what it is good at:

- **Front-loaded to recon.** AI offensive capability is strongest at reconnaissance, enumeration, and triage; it degrades through the middle of the kill chain and is weakest at deep exploitation, post-exploitation, and novel chaining. Expect the copilot to feel most useful early and increasingly advisory-only as you go deeper.
- **Recall and adaptation, not invention.** The copilot recalls and twists *known* techniques. For genuinely novel vulnerabilities — often the high-value bugs — the graph and the web have nothing, and it cannot invent. It amplifies a skilled operator; it does not replace skill.
- **Verify everything.** Small Q4 models hallucinate CVEs, payloads, and API behavior. The human-execute gate and the sandbox (§13.2) contain the damage, but the speedup is capped by your verification — the correct posture for a copilot anyway.
- **Compounds over time.** Day one, with a cold graph, the tool is mostly a scout. Its value grows with the brain — months of disciplined write-backs are what make it sharp. Judge it at month six, not day one.
- **Ceiling set by model size.** 12GB forces the local stack to ~4–8B at Q4; the hardest reasoning moments will occasionally exceed that. On **practice** the cloud teacher (V4) already *is* the bigger model; on **real** work the escape valve is a server-hosted model (§4.1) when a specific hard problem needs one.

---

## 14. Build Sequencing

Build the concrete Copilot first. Let *Orchbiter* be extracted later from whatever proves reusable — do not design the general framework top-down.

1. **P0 — Runtime + models + guardrails.** Hermes running locally; the broker (`Qwen3-4B`) + analyst (`Foundation-Sec-8B`) + offense (`DeepHat-7B`) routed on-demand, with the practice teacher (`DeepSeek V4`) behind the resilient client; scope check + audit ported.
2. **P1 — Graph foundation + bootstrap.** Schema (§6) in a queryable store; `graph_query` + `graph_write` MCP servers; seed from public data + past notes (§13.3).
3. **P2 — Retrieval + reasoning loop.** Implement §7, including the adapt-first mismatch branch, never-overwrite write-back, and failure capture (Step 6b).
4. **P3 — Scout + distillation + self-security.** `scout` server, RAG `retrieve`, the ingestion pipeline, the distillation bridge, and the untrusted-content / sandbox controls (§13.2).
5. **P4 — Skills + curation + evaluation.** CTF skills as `agentskills.io`; the curation job (§13.1); the metrics in §13.5.

---

## 15. Open Questions / Deferred

- **Weight fine-tuning.** A LoRA over accumulated trajectories is possible but almost certainly not worth it for a solo operator. RAG + skills + graph deliver the large majority of the benefit at a fraction of the cost. Deferred unless a specific need appears. *If pursued, the datasets to start from are **Primus** (Trend Micro — pretraining/instruction/reasoning suite, MIT/ODC-BY) and **Pentest-R1** (500+ real-world expert pentest walkthroughs as Thought-Command-Observation tuples). Note both can be mined as corpus/skills without training (§13.3).*
- **Obsidian frontend.** Optional human-readable view over the graph; must not become the source of truth (§6.4).
- **Skill sharing.** `agentskills.io` portability opens the door to sharing/importing skills — scope and trust implications to be decided.
- **Copilot naming.** Working title only; the project needs a name distinct from Orchbiter.
