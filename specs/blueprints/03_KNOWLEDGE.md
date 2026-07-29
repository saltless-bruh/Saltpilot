# Saltpilot — Knowledge-Architecture Blueprint

**Version:** 1.1
**Status:** Feature blueprint — owns the knowledge layer.
**v1.1 —** added the **graph-vs-DAG decision** (§3: a general cyclic graph is the storage model; DAGs are *derived views* — attack paths, the sprint-DAG, provenance chains) and the **RAG head-start-and-roadmap** section (§14: DIY `sqlite-vec` + `FTS5` + `bge-reranker` now, with `txtai` / `LLMWare` / `RAGatouille-ColBERT` as tested upgrades behind the retrieval contract).
**Role:** This document owns the **knowledge layer** in depth: the stores, the scope model, retrieval, the five flows, and exactly how the **Auto-Recon Engine** and the **Copilot** read and write it. It is the depth behind Main Proposal §4. Where it and the Main Proposal disagree on the *seam*, the Main Proposal wins; the graph's **node/edge schema** is owned by **Copilot Blueprint §6** and referenced here, not redrawn.

**Companion blueprints:** Main Proposal (the seam), Copilot (graph schema §6, retrieval loop §7, memory §5), Auto-Recon (the recon pipeline §5).

---

## 1. What this owns (and what it doesn't)

The knowledge layer is the **connective tissue** both features share (Main Proposal §4). This blueprint fixes *how it works and who touches what*, so the two features never fight over it.

- **This owns:** the four stores and their boundary rule; the engagement/general **scope model**; **retrieval** mechanics; the five **flows** (ingest, retrieve, distill, promote, new-CVE); the **read/write division** between the features; the **MCP surface**; and the knowledge layer's **lifecycle & tiering**.
- **This does *not* own:** the graph **node/edge schema** (Copilot §6), the recon **pipeline** that produces facts (Auto-Recon §5), or the **reasoning loop** that consumes them (Copilot §7). It owns the *architecture around* those, not those.

Everything here is reached by both features through **Hermes tool routing** (MCP servers), never bespoke wiring (Main Proposal §2).

---

## 2. The stores (four, plus working memory)

The anti-collision rule is **single source of truth per data type**: each kind of knowledge lives in exactly one store, and the boundary is *what kind* of knowledge it is — not who is using it. Get this right and the two features can both read and write without colliding.

| Store | Owns (source of truth for) | Backing |
|---|---|---|
| **The graph** | Structured facts — targets, findings, vulns, CVEs, techniques + preconditions, and how they relate | SQLite graph |
| **RAG corpus** | Raw reference *text* not yet distilled — CVE descriptions, writeups, PoCs, CVSS notes, tool docs | sqlite-vec + FTS5 |
| **Hermes memory** | Autobiography — *what was done, when, in which session* (the experience substrate) | SQLite + FTS5 (Hermes) |
| **Scout** | The outside world / what's new — NVD, OSV, GHSA, the web | live feeds (MCP) |
| *Working memory* | *The current query into the above — not a persistent store; it is the live Hermes session context* | — |

Two boundaries worth stating plainly, because they are where confusion starts:
- **Graph vs corpus.** The graph holds *facts and relationships* ("`nginx 1.2.3` on `admin.acme.com` is affected by `CVE-2026-X`"). The corpus holds *text* ("the CVE-2026-X advisory, the PoC writeup"). A fact is distilled *from* text into the graph; the text stays in the corpus for when the fact isn't enough.
- **Graph vs Hermes memory.** The graph holds *what is true about the domain*; Hermes memory holds *what the operator/agent did*. "SMB signing is disabled on DC01" is a graph fact; "at 14:32 we ran a relay attempt and it worked" is Hermes autobiography. Distillation (§6.3) is the bridge that turns the second into the first.

---

## 3. The graph in two scopes

The graph is **one store partitioned by a `scope` dimension on every node/edge** — not two graphs. This is the single most important idea in the layer, because it is what lets one store hold both a target's private facts *and* the general wiki without them contaminating each other.

- **`engagement` scope — the per-target "brain."** This campaign's surface, services, findings, hypotheses, candidates, tried/failed. Born when the engagement opens, grown by recon and the operator, and **archived** when it ends. Private to that engagement.
- **`general` scope — the wiki + experience.** Target-independent knowledge: vuln classes, techniques with their preconditions, CVE↔product relationships, and **distilled lessons** from past work. Durable; grows across every engagement; never tied to one client.

The user-facing "three-tier brain" maps onto this exactly: **target brain** = engagement scope; **general wiki** = general scope + the RAG corpus; **experience** = general scope distilled from Hermes memory. It is three tiers of *use*, two scopes of *storage*, one graph.

*(Node and edge types — `target`, `service`, `finding`, `cve`, `technique`, `credential`, `defense`, and the precondition edges — are defined in Copilot §6. `scope` is a dimension on all of them, owned here.)*

**Graph, not DAG — storage vs derived views.** The store is a *general directed graph* (cycles allowed), **not a DAG** — deliberately. The domain has real cycles: credential reuse, lateral movement, co-hosting, and bidirectional relations all form loops, and forcing acyclicity would drop real edges for **no** retrieval gain (knowledge retrieval is associative traversal, which doesn't benefit from acyclicity). Acyclicity is imposed only where the data is genuinely acyclic — as **derived views computed over the graph**, never as the storage model:
- **Attack paths** — a candidate's route from access to goal: a DAG of steps + preconditions; feasibility is a reachability computation over it.
- **Sprint / task dependencies** — the recon **sprint-DAG** (Main Proposal §7 / Auto-Recon §8.2): execution ordering, acyclic by construction.
- **Provenance / derivation** — "this fact was derived from those": a DAG the write-back gate (§11) and feasibility re-derivation walk.
- **Precondition resolution** — a candidate's precondition dependency tree.

So: the graph stores *knowledge* (associative, cyclic); DAGs express *orderings and derivations computed from it*. Use each where its shape matches the data. *(If the graph ever feels tangled, the fix is schema + the scope split above + typed edges — not global acyclicity, which would amputate cycles the domain actually contains.)*

---

## 4. The referee — four rules that prevent a mess

Both features read and write the same layer. Four rules keep that safe:

1. **Single source of truth per data type** (§2) — a fact goes to the graph, text to the corpus, autobiography to Hermes memory. No store duplicates another's job.
2. **Scope** (§3) — every graph write declares `engagement` or `general`. Recon writes only engagement scope; general scope has exactly one writer (§8).
3. **Provenance + validation** — every fact carries a provenance class with the authority order **`operator-confirmed > tool-observed > model-asserted`**; a lower-authority writer *flags*, never overrides. Model-asserted checkable facts are validated before they land: **CVEs** against a real source (Auto-Recon §5.2), **answer-named hosts/ports/CVEs** by the grounding guard (Copilot §7). Unverified facts are **quarantined**, not written as truth (the write-back gate, §11).
4. **Graph-primary retrieval** (§5) — reads hit the graph first; the corpus and scout are consulted only on a miss or for undistilled material. The graph is the answer; the corpus is the fallback.

---

## 5. Retrieval — graph-primary, hybrid, bounded

A read resolves in a fixed order, cheapest and most-trusted first:

1. **Graph first.** The **broker** (`Qwen3-4B`, Main Proposal §5) scopes the relevant subgraph and hands the deep reasoner a **task-scoped brief of pointers** (fact IDs / graph refs), not a wall of facts. The reasoner dereferences the real, validated facts it needs. Most reads end here.
2. **RAG corpus on a miss / for undistilled text.** Hybrid retrieval — **dense** (BGE-M3 embeddings over sqlite-vec) **+ lexical** (FTS5), then a **reranker** — returns the most relevant raw text (a CVE advisory, a writeup) when the graph doesn't yet hold the fact.
3. **Scout for the genuinely new.** If neither has it, the scout can fetch from the outside world (§6.1), which then flows back into the corpus/graph.

**Bounded by design.** Retrieval only ever touches the **hot** working set (§10), so a read at hour 30 costs the same as at hour 1 — the property the long-haul substrate depends on (Main Proposal §7). The broker's brief-of-pointers is what keeps the reasoner's context small even when the graph is large.

---

## 6. The five flows

The stores are nouns; these are the verbs that connect them. Each names its **trigger**, **mechanism**, and **owner**.

### 6.1 Ingest — the outside world in
*Trigger:* scheduled sync, or a scout query during work. *Mechanism:* the scout pulls from NVD/OSV/GHSA/web; new **text** lands in the RAG corpus, new **CVE facts** are normalized for matching (§6.5). *Owner:* the `scout` MCP server (a Hermes scheduled job for the periodic sync). Fetched content is treated as **untrusted** (sandboxed, never executed).

### 6.2 Retrieve — knowledge out
The read path of §5 (graph → RAG → scout), exposed via `graph_query` and the retrieval MCP servers. Used by both features on every reasoning step.

### 6.3 Distill — experience formation (the loop that makes Saltpilot learn)
*Trigger:* a **confirmed success** on the Copilot side (an operator-verified exploit/technique). *Mechanism:* the Copilot reads the relevant **Hermes memory** ("we did X against a service like Y and it worked") and writes a durable **`general`-scope technique node + its preconditions** into the graph — the reusable lesson, stripped of the specific target. *Owner:* the **Copilot** (the sole writer of general scope, §8). Validated on the way in (a lesson is only distilled from a *confirmed* outcome, never a model hunch).

### 6.4 Promote — engagement lessons rise at the end
*Trigger:* engagement close. *Mechanism:* the engagement-scope record is **archived** (recoverable, cold); any *general* lessons it produced are already in general scope via distillation, and a final pass promotes anything engagement-local that generalizes. *Owner:* the Copilot / the Custodian (§10).

### 6.5 New-CVE — the reactive flow (the one that was missing)
*Trigger:* a new CVE arrives via ingest (§6.1) while an engagement is live. *Mechanism, deterministic:*
1. the CVE's affected products are **matched mechanically** against every `service`+version in the **live engagement-scope** graph — not the model guessing;
2. a hit creates a **candidate** ("CVE-2026-X may affect `admin.acme.com nginx 1.2.3`"), provenance = freshly-ingested + matched;
3. the reasoner **enriches feasibility** (public PoC yet? exposure?) via scout;
4. it is **surfaced to the operator, never auto-exploited** (fenced autonomy);
5. because the graph persists and feasibility is recomputed, a CVE that drops on day 3 **auto-re-scores** the affected nodes.
*Owner:* the `cve_lookup` + `scout` servers feed it; the recon/enrichment loop matches and surfaces it.

---

## 7. How Auto-Recon uses it

Auto-Recon is the **populator of the engagement scope** (breadth).

- **Writes:** `engagement`-scope facts only — hosts, services, findings, candidates — through its deterministic pipeline (normalize → interpret → **validate** → write). Every model-asserted CVE is validated before it lands (Auto-Recon §5.2); writes go through the verification gate (§11).
- **Reads:** `general`-scope knowledge (known vuln/technique/CVE relationships), the **corpus** (to interpret findings, ground candidate generation), and **scout** (fresh CVE match). It reads the general wiki; it does **not** write it.
- **Never:** writes `general` scope, and never exploits (so it never produces "confirmed exploit" facts — those come from the operator via the Copilot).
- **Via:** `graph_write` (engagement scope), `graph_query`, `scout`, `cve_lookup` — all Hermes-routed.

## 8. How Copilot uses it

The Copilot is the **reader of everything** and the **sole writer of general knowledge** (depth).

- **Reads:** the whole layer — the engagement brain (what recon found), general knowledge, the corpus, Hermes memory (past sessions), and scout.
- **Writes two things:** (1) **operator-confirmed** `engagement`-scope facts (the enrichment channel, Main Proposal §3.3 — a confirmed credential/behaviour, provenance `operator-confirmed`); and (2) **`general`-scope experience** via distillation (§6.3) after a confirmed success. It is the **only** writer of general scope.
- **Grounding:** every answer it delivers passes the grounding guard (Copilot §7) — hosts/ports/CVEs it names must exist in the fact set or be stripped/flagged.
- **Via:** `graph_query` (all scopes), `graph_write` (confirmed engagement + general), `scout`, `cve_lookup`.

**The division in one line:** recon *fills the target brain*; the Copilot *confirms it and turns success into durable experience*. Two writers, one non-overlapping boundary — recon owns engagement-breadth, the Copilot owns confirmation + all of general scope.

---

## 9. The MCP surface

The layer is exposed to Hermes as MCP servers, so both features reach it through tool routing (Main Proposal §2). Contracts (detail in Copilot §8):

- **`graph_query`** — scoped reads: `by_scope`, `by_type`, `neighbors(node)`, `preconditions_of(candidate)`. Returns pointers the broker can brief over.
- **`graph_write`** — `propose_node(type, fields, provenance_class, scope)`; promotion out of quarantine is by the **verification gate** (§11), not a confidence threshold. `link(a, b, edge)`. **Never-overwrite:** a lower-authority writer flags, never clobbers (§4).
- **`scout`** — fetch from the outside world (sandboxed, untrusted); feeds ingest (§6.1).
- **`cve_lookup`** — validate/resolve a CVE against a real source (NVD/OSV/GHSA); the deterministic half of CVE validation (§4) and new-CVE matching (§6.5).

---

## 10. Lifecycle & tiering (the long-haul tie-in)

The layer is built to run for a marathon, so it is **bounded, not ever-growing** (Main Proposal §7, the Custodian):

- **Hot / warm / cold tiering.** Only the active working set — in-scope, live candidates, recent findings — stays **hot** and queryable. Settled, aged, or out-of-scope subgraphs **compact to cold** storage (recoverable). Retrieval, RAG, and feasibility re-derivation only ever touch the **hot** set (§5), which is why query latency is flat over a 30-hour run.
- **Engagement archival.** At close, the engagement-scope subgraph is snapshotted and moved cold; general-scope knowledge it produced remains hot in the wiki.
- **Corpus hygiene.** Evidence blobs keep hashes, expire raw; the corpus is deduplicated; embeddings are rebuilt incrementally.

This is why "the graph grows forever" is not a failure mode: total volume grows, but **live cost is bounded to the hot set.**

---

## 11. Guardrails — keeping hallucination out of the knowledge

The layer is the program's long-term memory, so a single hallucinated fact that becomes "truth" is a compounding error. Four mechanisms stop that:

- **Provenance authority** (§4): `operator-confirmed > tool-observed > model-asserted`; a weaker source can flag but never overwrite a stronger one.
- **The write-back gate** keyed on **verification/corroboration, not self-reported confidence** — a possibly-hallucinated fact is **quarantined**, down-weighted, and re-verified-or-expired rather than silently becoming ground truth (Copilot §4.4).
- **Deterministic validation after the model** (Principle 6): model-asserted CVEs validated against a real source before write (Auto-Recon §5.2); answer-named entities checked by the grounding guard (Copilot §7).
- **Cross-target contamination barrier.** A distilled experience ("this worked on target A") is retrieved as a **prior/hint**, ranked below tool-observed facts, and **re-validated against the current target** — never written straight into a new engagement's graph. This is what lets general-scope experience help without leaking one target's specifics into another.

*(Honest limit: these contain hallucination propagation to near-none; they cannot lower the model's underlying source rate — Main Proposal §7.)*

---

## 12. The layer at a glance

```text
   scout  —  the Internet   (NVD · OSV · GHSA · web)
     │
     │  ingest  (sandboxed · untrusted)
     ▼
   RAG corpus  —  raw reference text   (CVEs · writeups · PoCs · docs)
     │
     │  retrieve   (only on graph-miss / undistilled)
     ▼
 ═══════════════════════════  THE GRAPH  ═══════════════════════════
   engagement-scope                       general-scope
   the per-target brain     ── promote ──▶ the wiki + experience
     ▲                                        ▲
     │  Auto-Recon writes findings            │  distill  (Copilot,
     │  (validated pipeline)                  │  after a confirmed win)
     │                              Hermes memory ◀── Copilot logs
     │                              (what was done, when)
 ══════╪════════════════════════════════════════════════════════════
       │
   new-CVE:  ingest ──▶ match the live engagement graph ──▶ candidate
             (deterministic · surfaced to operator · never auto-exploited)

   reads: broker scopes the graph → brief of POINTERS → deep reasoner
   writes: recon = engagement scope · Copilot = confirmed + all general
```

---

## 13. What v1 builds (the thin slice)

v1 (the `saltpilot-spec-v1` slice) deliberately builds only the spine of this layer, so the core loop is provable before the full memory system exists:

- **One graph, engagement scope only.** Canonical host identity, the validated CVE path, and grounded answers — but **no general scope, no distillation, no promotion** yet (the graph is small, so there is no broker and no experience loop in v1).
- **Validation on from day one:** the CVE validator and the grounding guard are v1 slice-blocking tasks — because they are exactly what Checkpoint 5 proves.
- **Corpus + scout minimal:** a local CVE/OSV mirror for validation; no full RAG corpus, no distillation bridge.

The full layer in this blueprint — general scope, the distillation and promotion flows, hot/warm/cold tiering, the new-CVE reactive flow — is the target the slice grows into, not v1 scope.

---

## 14. The RAG subsystem — head start and roadmap

The RAG layer is the *text fallback* under a graph-primary design (§5), so it is built small first and grown only where retrieval quality demands it. The path is **DIY-first, product-later** — and every step stays behind the same MCP retrieval contract (§9), so swapping an implementation changes nothing upstream.

**Head start (build this now) — DIY from primitives.** `sqlite-vec` (dense) + `FTS5` (lexical) + `bge-reranker` (rerank): hybrid, reranked, graph-primary. Chosen over any framework because it stays SQLite-family, local, and portable; adds **no competing orchestrator** (Hermes owns orchestration — Main Proposal §2); and keeps RAG proportional to its role (the graph does the heavy lifting; RAG is the fallback). **Hybrid is not optional here:** the corpus is CVE IDs and version strings (`CVE-2026-1234`, `nginx 1.2.3`) that need exact-token lexical matching, which dense embeddings blur. Cheap early win: **contextual retrieval** — prepend a line of context to each chunk before embedding.

**What "in shape" looks like.** Once the core loop and the knowledge layer are proven, the RAG subsystem is: a bounded, deduplicated corpus over the **hot set** (§10); hybrid + reranked retrieval that the broker brokers into pointer-briefs (§5); scout-fed ingestion (§6.1); and a path that **promotes frequently-retrieved corpus text into graph facts** (distillation, §6.3) — so good text becomes structured knowledge over time and the corpus stays the fallback, never the primary. At that point the DIY layer is a known quantity with a **quality baseline** to measure upgrades against.

**Upgrade options (test, then adopt selectively — never on hype).** Each is a drop-in improvement to *one part* of the DIY layer, behind the retrieval contract (§9):
- **`txtai`** — swap the hand-wired hybrid index for a lightweight embedded search engine if the DIY plumbing becomes a maintenance drag. Same local/SQLite spirit, less code to own. *Adopt if:* it beats the DIY baseline on retrieval quality **and** cuts maintenance, without dragging in an orchestrator.
- **`LLMWare`** — adopt its CPU/edge + small-specialized-model pipeline for stronger **document processing** (parsing messy PDFs/office advisories and writeups) on the 12GB box without GPU cost. *Adopt if:* it measurably improves ingestion of messy security docs at acceptable CPU cost.
- **`RAGatouille / ColBERT` (late-interaction)** — upgrade the **retriever itself** to multi-vector late-interaction if hybrid + rerank plateaus and retrieval quality is the *proven* bottleneck. Higher storage, higher quality. *Adopt if:* it shows a recall/precision gain over hybrid+rerank that justifies the storage cost.

The discipline is the same as everywhere in Saltpilot: **prove the DIY baseline, keep every upgrade behind the retrieval contract, adopt only what beats the baseline on a real metric.** Anything that wants to own storage, a UI, or orchestration — RAGFlow, Cognita, R2R, or LangChain/LangGraph as an orchestrator — stays out: it fights local-first, SQLite-family, and the one-orchestrator rule.

---

## 15. Open questions

- **Distillation trigger precision.** What exactly counts as a "confirmed success" worth distilling — operator-tagged only, or also high-corroboration tool outcomes? (Affects how fast general scope grows and how noisy it gets.)
- **General-scope decay.** Whether distilled techniques age out or are re-validated on a cadence, so a technique that stopped working doesn't linger as a confident prior.
- **Corpus provenance for the new-CVE flow.** Which feeds are authoritative enough to auto-match against the live graph vs. which only surface as softer hints.
- **Cross-engagement general scope vs multi-client isolation.** General scope is target-independent by construction, but confirming that *no* engagement-specific identifier ever rides along in a distilled lesson needs an explicit check (ties to Main Proposal §10, multi-engagement state).
