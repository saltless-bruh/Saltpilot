# Saltpilot v1 — Session Compaction & Handoff

*A durable record of the session that built the Saltpilot v1 thin slice (Milestones 0–7),
so the next session — including the planned **local, in-real-life test** — can resume without
re-deriving anything. Written into `specs/` on purpose: this is project memory, not chat scrollback.*

---

## 0. TL;DR

The **v1 thin slice is complete and pushed** (branch `claude/project-proposal-blueprints-o2e44l`,
PR #1, tip `836eac8`). All **39 v1 task boxes** in `specs/tasks.md` are ticked; **Checkpoints 0–7**
are annotated MET (Checkpoint 5's machinery is proven, its objective quality bar is deferred to the
reference box). Test suite: **123 passing, 1 skipped** (the skipped one is the model-only
interpretation eval, which needs a real GPU-served model).

The core loop is real and closes end to end, both hermetically and **live**:

```
scope → recon (nmap + httpx behind Workbenches) → deterministic normalize/dedup
      → local-model interpret (CVE-validated) → SQLite graph → grounded answer (guarded)
```

**Two things are honestly NOT proven yet**, by design, because they measure the real model on real
hardware and this build ran in a CPU-only container:
1. **Interpretation quality** — Checkpoint 5's objective N-of-M-services / ≤K-false-CVEs bar on a
   labeled host, run against real `Foundation-Sec-8B`.
2. **VRAM budget** — peak VRAM for one resident model on the RTX 3060.

Both have frozen, ready-to-run runners. **These two are exactly what the upcoming local IRL test is
for** — see §7.

---

## 1. What Saltpilot is (one paragraph)

A **local-first, authorized offensive-security agent** built as an **extension of Hermes Agent**
(the real PyPI package `hermes-agent`, v0.19.0, Nous Research). Saltpilot is *not* a fork — it
registers as a bundle of **MCP servers + a skill** and is driven from the `hermes` CLI, exactly as
the Main Proposal (`specs/blueprints/00_MAIN_PROPOSAL.md`) describes. The whole point of v1 is to
prove the smallest honest version of the core loop: scope discipline, tool-fed-from-tool recon, a
**deterministic spine that surrounds the model on both sides** (parsers/scope-gate before it; CVE
validator + grounding guard after it), and a grounded answer an operator can trust.

---

## 2. Where the code lives (module map)

| File | Responsibility |
|------|----------------|
| `pyproject.toml` | deps (`defusedxml>=0.7`, `mcp>=1.2`); 4 console entrypoints `saltpilot-{scope,graph,recon,copilot}-mcp` |
| `saltpilot/config.py` | `Engagement`/`ModelConfig`/`ReconConfig`; `load_engagement()`; `stable_engagement_id()` (deterministic id from target+scope → idempotency) |
| `saltpilot/scope.py` | `ScopeGate`, `ScopeVerdict`; fail-closed `check()` and `resolve_and_gate()` (returns **pinned in-scope IPs**; strict CIDR-bounding) |
| `saltpilot/findings.py` | `Finding`, `Asset`, `Fact` dataclasses |
| `saltpilot/store.py` | `GraphStore` (SQLite WAL); null-safe upserts (`col IS ?`); `persist_findings`, `upsert_interpretation`, `log_run`, `facts_for_query()` + keyword filter |
| `saltpilot/workbench.py` | `Workbench`/`ToolAdapter` Protocols; `IntentSpec`/`ToolInvocation`(+`stdin`)/`RawOutput`/`ReconOutcome`/`CoverageRecord`/`WorkbenchResult` |
| `saltpilot/adapters/nmap.py` | `NmapAdapter` (defusedxml, partial-recovery, OPEN ports only) + `NetworkWorkbench` |
| `saltpilot/adapters/httpx.py` | `HttpxAdapter` (ProjectDiscovery httpx; distinguishes the PD binary from the Python-httpx impostor; configurable `binary`) + `WebWorkbench` (stdin targets) |
| `saltpilot/normalize.py` | `canonicalize_host`, `build_alias_map`, `normalize`, `dedup` (IP↔hostname → one asset) |
| `saltpilot/recon.py` | `run_invocation` (subprocess discipline), `web_feed` (probe **ALL** open ports), `ReconRunner` (two-stage nmap→httpx; optional interpret step), `build_recon` |
| `saltpilot/models.py` | `Role`, `Completion`, `ResidencyManager` (single-tenant GPU), providers (`Ollama`, `DeepSeekV4`, `_OpenAICompat`), `RoutedProvider` (R7.4 routing guard), `build_model_provider` |
| `saltpilot/interpret.py` | `CveValidator` over pluggable `CveSource`; `Interpreter` (delimiter-wrapped untrusted findings, extract-only); `parse_interpretation_reply`; `Interpretation` |
| `saltpilot/query.py` | `CopilotQuery` (retrieve→prompt→REASONING→guard→`Answer`); `ground_guard` (rewrite invented entities → `[unverified: …]`) |
| `saltpilot/mcp/*_server.py` | 4 FastMCP servers: `scope` (scope_check/resolve_and_gate), `graph` (graph_query/graph_findings), `recon` (run_recon; reads `SALTPILOT_HTTPX_BIN`), `copilot` (ask) |
| `saltpilot/skill/SKILL.md` | Hermes skill (`saltpilot-recon`), scope-first workflow |
| `scripts/setup_hermes.sh` | reproducible Hermes wiring (install, register 4 MCP servers, install skill, set model endpoint) |
| `docs/VALIDATION.md` | the Validation-Goals table (5 PASS, 2 REFERENCE-BOX) |
| `docs/SLICE_NOTES.md` | one-page proved / didn't / surprised |
| `tests/` | 123 tests; real captured fixtures; `test_regression.py` + `regression/eval_set.json` (frozen held-out set); `test_e2e.py`; `test_recon_live.py` (real nmap+httpx) |

---

## 3. The five slice-blocking correctness fixes (the spine)

These are the parts that make the autonomous loop *safe to trust*. Every future slice must **extend**
them, never route around them.

1. **Scope-resolution hole** → the gate resolves hostnames and hands tools **pinned in-scope IPs**,
   never a raw hostname. A hostname resolving to an out-of-scope IP is rejected; resolver error =
   fail closed.
2. **Host-identity idempotency** → IP and hostname for the same host collapse to **one asset** via
   the alias map, so re-recon adds zero rows.
3. **httpx/nmap coupling** → the model names an **intent**, the Workbench renders the command; httpx
   probes **all open ports**, not just nmap's http-labeled ones.
4. **CVE fabrication** → the model *proposes*, a **deterministic `CveValidator` disposes**
   (exists? product/version match?). A hallucinated or injected CVE never becomes a stored fact.
   This is the strongest injection defense — stronger than the prompt.
5. **Grounding guard** → "no invented assets" is an **enforced invariant**, not a prompt hope.
   Invented hosts/ports/CVEs are rewritten to `[unverified: …]` before the operator sees them.

---

## 4. Milestone-by-milestone (what shipped)

- **M0 — Scaffold + real Hermes wiring.** Package skeleton, 4 MCP servers, the skill. Tasks 0.1/0.5
  done **live**: `hermes-agent` v0.19.0 installed in `/opt/hermes-venv`, all 4 servers registered
  and tool-discovered (`hermes mcp add`/`list`), skill enabled, reproducible via `setup_hermes.sh`.
- **M1 — Scope gate.** `ScopeGate` + `resolve_and_gate` (fix #1). Fail-closed.
- **M2 — nmap.** `NmapAdapter` + `NetworkWorkbench`, defusedxml, partial-XML recovery, OPEN-only.
- **M3 — httpx (fed from nmap).** `HttpxAdapter` + `WebWorkbench`; the tool-feeds-tool pipeline
  (fix #3); stdin target feed.
- **M4 — Model layer (residency-aware).** `RoutedProvider` R7.4 routing: **ANALYSIS always local**;
  **REASONING = cloud teacher on `practice`, local on `real`**; *no config can send `real` to cloud*
  (structural). `ResidencyManager` = single-tenant GPU. Cloud→local fallback (R6.3), recorded.
- **M5 — Interpretation.** `Interpreter` (findings as delimiter-wrapped **untrusted data**,
  extract-only) + `CveValidator` (fix #4). Injection defense proven two ways (delimiter strip +
  output-side validator). **Checkpoint 5's objective bar deferred to the reference box.**
- **M6 — Copilot query.** `CopilotQuery` + `ground_guard` (fix #5). Grounded, cited answers;
  honest "No relevant facts found." when uncovered; every query logged.
- **M7 — End-to-end validation & honest failure.** `test_e2e.py` (full loop + degrade cases),
  `docs/VALIDATION.md`, `docs/SLICE_NOTES.md`, frozen regression set. Live capstone: real nmap+httpx
  on a localhost service → interpret → grounded `ask` citing the real discovered port, invented
  entities neutralized.

---

## 5. Non-obvious gotchas discovered (do not re-learn these the hard way)

- **SQLite `NULL` is distinct under a `UNIQUE` constraint.** A host asset (`port=NULL`) duplicates on
  re-run unless upserts use `col IS ?` matching. The table constraint alone does not give
  idempotency.
- **A launcher (Hermes) spawns stdio MCP servers with a *sanitized* PATH**, and the name `httpx` is
  shadowed by the unrelated **Python httpx CLI**. Web probing silently degraded until the recon
  server took its httpx binary from an env var (**`SALTPILOT_HTTPX_BIN`**). The `HttpxAdapter` also
  actively distinguishes the ProjectDiscovery binary from the impostor.
- **Hermes model config:** setting `model.base_url` drops the scalar `model` name — set the
  `model.name` subkey.
- **`hermes mcp add`** needs the mcp SDK in the venv (`hermes-agent[mcp]`), and `--accept-hooks` is a
  **group** flag: `hermes mcp --accept-hooks add …`.
- **MCP SDK install on debian** fought a system PyJWT → `pip install mcp --ignore-installed PyJWT`
  (used for all editable installs thereafter).
- **`ResidencyManager` must keep the unloader on same-model re-acquire** — evict only on a genuine
  model change.

---

## 6. Environment this session ran in

- **CPU-only container**, proxy-filtered egress: pypi/npm/crates/go allowed; **ollama.com model pulls
  and NVD are blocked.** This is why real GPU-served weights and the live NVD mirror could not be
  exercised here — and why §7 (the local box) exists.
- Hermes installed in venv **`/opt/hermes-venv`**; ProjectDiscovery httpx built at
  **`/opt/pd-bin/httpx`**.
- To prove *wiring* without real weights, stub OpenAI-compatible endpoints stood in for the model —
  never faking the *measurements*, only the transport.

---

## 7. ⭐ NEXT: the local, in-real-life (IRL) test — cloud → local

> This is the section the next session should act on. The user's plan: **switch from cloud to local
> and run the real test on the reference box.** Everything below is the handoff for that.

### 7.1 The reference box
RTX 3060 12 GB / Ryzen 7 7700 / 32 GB / Pop!_OS. This is where the two REFERENCE-BOX validation
goals get real numbers, because they measure **the real model on the real GPU** — which a CPU
container structurally cannot do.

### 7.2 Switching the model layer from cloud to local
The routing is already built for this — flipping to local is a **config/engagement change, not a
code change**:
- Set the engagement type to **`real`** → by R7.4 the reasoner is the **local** model (Qwen3), and
  **no external call is made** (this is structural, not a toggle that can be misconfigured).
- ANALYSIS (interpretation) is **already always local** — point it at a local Ollama `/v1` serving
  **`Foundation-Sec-8B`**.
- Serve the models locally (Ollama), then set the model endpoint (`setup_hermes.sh` /
  `model.base_url` + `model.name`). Provide a **local NVD/OSV mirror** so `CveValidator` validates
  against real data (env `SALTPILOT_CVE_DB` or `nvd_local`).

### 7.3 Validation Goal (b) — interpretation quality (Checkpoint 5, the go/no-go)
Runner is frozen: `tests/test_regression.py::test_interpretation_quality_regression`, driven by
`tests/regression/eval_set.json`.

1. On the box, serve `Foundation-Sec-8B` and export
   **`SALTPILOT_EVAL_MODEL_URL`** = that Ollama `/v1` URL.
2. Build/choose a **small labeled lab host** (known services → known applicable CVEs).
3. In `eval_set.json → interpretation_eval`: set `host`, the `findings`, and **fill `expected_cves`**
   with the host's true applicable CVEs (from the seeded mirror). Confirm/adjust the starting
   thresholds **N/M/K = 2/3/1** (identify ≥N of M services; ≤K false CVEs after validation).
4. Run the eval. **This is the go/no-go on `Foundation-Sec-8B` being good enough.** If it can't
   clear the bar, that's a **design finding** to resolve *before* expanding — bigger/different model
   or a restructured prompt — not something to paper over.
5. Record the real N/M/K result back into `docs/VALIDATION.md` (goal b) and keep the eval frozen so a
   later model swap can't silently regress (Copilot §13.5).

### 7.4 Validation Goal (e) — VRAM budget
Single-tenant residency *logic* is already proven. On the box: load each local model in turn, watch
`nvidia-smi`, and confirm peak ≈ **one ~5 GB model within the 12 GB budget, with no co-residency**
(the prior local model must unload on a model change). Record the peak in `docs/VALIDATION.md`
(goal e).

### 7.5 Real recon target (beyond localhost)
v1 only ever scanned **localhost**. The IRL test is the chance to run against a **real remote
authorized target** — surfacing latency, rate-limits, and hostile/odd banners at scale that a
loopback service never shows. Keep scope discipline absolute: the gate hands **pinned in-scope IPs**
only. Do this only against a target you are authorized to test.

### 7.6 Definition of done for the IRL test
`docs/VALIDATION.md` goals (b) and (e) flip from **REFERENCE-BOX** to **PASS** (or to a recorded
design finding with a decision), with real numbers; the regression set carries the labeled host
forward. At that point every Validation Goal has a real recorded result and v1 is validated on
hardware, not just in a container.

---

## 8. After the IRL test — the expansion discipline

Do **not** open the whole design at once. Add features one at a time, each on its own small spec,
each **stress-tested before the next** (from `specs/tasks.md`, subject to what v1's findings say):

1. **RAG retrieval** — only if v1's naive graph retrieval proved too weak.
2. **More recon domains/tools** — subfinder, katana, nuclei (each = one `ToolAdapter` + parser tests).
3. **Typed graph + exploit-candidates-with-conditions** — node/edge + precondition model.
4. **Enrichment loop** — operator finding → confirm → write-back → re-derive.
5. **Offense model + attack-path planning** — advisory plans.
6. **Rust TUI + MCP boundary** — in-process calls become MCP tools; TUI is a client.
7. **Long-haul layer** — Custodian/tiering, Supervisor, saturation, checkpoint/resume, digests — last.

Each step repeats: small spec → build → **validate the claim** → only then expand.

---

## 9. Working agreements carried forward

- **Branch:** `claude/project-proposal-blueprints-o2e44l`. **PR:** #1 (reference it; don't open new
  PRs unless asked). Commit with descriptive messages + required trailers; push with retry/backoff.
- **After every milestone (standing rule):** audit tasks-list vs. actual codebase; complete anything
  unimplemented unless blocked; tick `[ ]`→`[x]` in `specs/tasks.md` with an `*(audit: …)*` note.
- **Source of truth:** the Main Proposal + the five blueprints in `specs/blueprints/`; `design.md` +
  `requirements.md` for the how.
- **Honesty over green checkmarks:** reference-box items are recorded as such with a ready runner —
  never faked. That discipline is the point of the checkpoints.
- Do not put the model identifier into any committed artifact.

---

*Compaction written 2026-07-27. v1 slice complete at commit `836eac8`. Next action on deck: the
local IRL test (§7).*
