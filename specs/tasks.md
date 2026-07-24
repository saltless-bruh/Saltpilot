# Saltpilot v1 (Thin Slice) — Tasks

Ordered, incremental build plan. Each task is small, testable, and references the requirements it satisfies. **Milestones end in a validation checkpoint — do not proceed past a checkpoint until it passes.** That rule is the point: it forces build-then-learn instead of building the whole design on faith.

Legend: `[R#]` = requirement satisfied. `⛔ CHECKPOINT` = stop and verify. **`⟵ slice-blocking fix`** = a correctness fix from the architecture review that must land *in that task* — these are the design-logic flaws (CVE fabrication, host identity, scope-resolution hole, httpx coupling, grounding guard) that would otherwise be built on and bite in week one.

**The head start builds on Hermes:** the components below are implemented as **MCP servers + a skill** that Hermes loads and drives (Main Proposal §2), run from the `hermes` CLI (the interim frontend — the custom TUI / ACP client is a later phase). So no UI work is needed to run and test the slice, and there is no throwaway standalone CLI.

---

## Milestone 0 — Scaffolding (Saltpilot-on-Hermes)

- [ ] 0.1 Install Hermes; confirm `hermes` runs and its model endpoint points at local Ollama (`Foundation-Sec-8B`). The head start builds *on* the proven harness, not a standalone CLI (Main Proposal §2).
- [ ] 0.2 Create the Saltpilot extension skeleton: `saltpilot/` package, `pyproject.toml` (Python 3.11+), `engagement.toml` example, `tests/` + `fixtures/` dirs, and the **skill** + **MCP-server** scaffolds Hermes will load. Pin deps: stdlib `sqlite3`, an HTTP client for the reasoner API, a TOML reader, an MCP server lib.
- [ ] 0.3 Implement config loading from `engagement.toml` into a typed `Engagement` object. `[R1, R7]`
- [ ] 0.4 Implement `GraphStore.init_schema()` — create the SQLite schema from `design.md`, WAL mode on, behind the **graph-MCP** server. `[R5]`
- [ ] 0.5 Register the skill + the MCP servers with Hermes; drive them from the `hermes` CLI (interim frontend — no custom TUI yet).

⛔ **CHECKPOINT 0:** from the `hermes` CLI the Saltpilot skill runs and creates the DB with the schema and an `engagement` row (`sqlite3` shows WAL mode); Hermes lists the registered Saltpilot MCP servers. Nothing else runs yet — but it runs *as a Hermes extension*.

---

## Milestone 1 — Scope gate (fail-closed first)

- [ ] 1.1 Implement `ScopeGate.check()` for domains, IPs, CIDRs, **and `resolve_and_gate()`** — resolve a hostname to IPs, gate each, return only in-scope IPs (tools receive IPs, never hostnames). `[R1.1, R1.2]` **⟵ slice-blocking fix: scope-resolution hole**
- [ ] 1.2 Make every error/ambiguity path return `OUT_OF_SCOPE` (fail closed); `check` never raises. `[R1.3]`
- [ ] 1.3 Unit tests: in-scope host, out-of-scope host, in-CIDR, explicit out-of-scope override, malformed input, resolver error → fail-closed on the last two; **plus a hostname that resolves to an out-of-scope IP → rejected**.

⛔ **CHECKPOINT 1:** the out-of-scope and ambiguous tests pass. Scope is the one control that must be right before any tool can run.

---

## Milestone 2 — First tool end-to-end (nmap)

- [ ] 2.1 Define the **`Workbench`** and `ToolAdapter` protocols and the `Finding`, `IntentSpec`, `ToolInvocation`, `ToolStatus`, `RawOutput` types from `design.md`. Tools live behind category workbenches; the caller passes an *intent*, never a command. `[R2.6, R3]`
- [ ] 2.2 Implement the **network workbench** — intent `discover_services(host)` → `NmapAdapter` (`is_available` via `--version`, `render` → `nmap -sV -oX`, `parse` XML → `Finding`s). The workbench calls `resolve_and_gate` and scans **IPs**. `[R2.1, R2.6, R3.1, R3.2]`
- [ ] 2.3 Unit-test `NmapAdapter.parse()` against a **real captured `nmap -oX` fixture** → assert exact `Finding` list. Add a malformed fixture → assert graceful partial parse. `[R3.4]`
- [ ] 2.4 Implement a minimal `ReconRunner` that runs one workbench intent: scope-gate targets, subprocess with timeout, reap child, classify outcome, parse. `[R2.4, R2.5]`
- [ ] 2.5 Implement `canonicalize_host()`, `normalize()`, `dedup()` — identity `(canonical_host, port)`, service as an *attribute*; unify IP↔hostname (a host seen both ways = one asset). `[R3.3]` **⟵ slice-blocking fix: host identity / idempotency**
- [ ] 2.6 Persist findings via `GraphStore.upsert_asset/upsert_finding`; re-run and assert no duplicates. `[R5.1, R5.3]`
- [ ] 2.7 Emit a coverage record for the nmap run. `[R8.1]`

⛔ **CHECKPOINT 2:** `saltpilot recon` on an authorized lab host runs nmap, persists correct services as findings, and a second run adds no duplicates. **First evidence the pipeline is real.**

---

## Milestone 3 — Second tool + the fed-from-first pattern (httpx)

- [ ] 3.1 Implement the **web workbench** — intent `probe_web(hosts, ports)` → `HttpxAdapter` (`httpx -json`) → `web_endpoint`/`tech` findings (status, title, tech, tls). **Probe *all* open ports and let httpx decide what is web — do not filter by nmap's service label.** `[R2.2]` **⟵ slice-blocking fix: httpx/nmap coupling**
- [ ] 3.2 Unit-test `HttpxAdapter.parse()` against a real `httpx -json` fixture.
- [ ] 3.3 Extend `ReconRunner` to run adapters in sequence and feed httpx from nmap's output; missing-tool → capability gap + skip + continue. `[R2.3]`
- [ ] 3.4 Persist web findings; extend the coverage summary.

⛔ **CHECKPOINT 3:** on a lab web host, nmap finds the web port and httpx enriches it (tech/title/status), all persisted. The tool-feeds-tool pattern works — this is the shape every future adapter reuses.

---

## Milestone 4 — Model layer (residency-aware)

- [ ] 4.1 Implement `OllamaProvider` (local) for role `ANALYSIS`, loading `Foundation-Sec-8B` on demand. `[R4.3, R7.1]`
- [ ] 4.2 Implement `DeepSeekV4Provider` (hosted API) — the **cloud teacher**, used only when `engagement.kind = practice`. `[R7.3]`
- [ ] 4.3 Implement `RoutedProvider`: analysis→local always; reasoning→**cloud teacher if `kind=practice`, local support if `kind=real`** (never send a real engagement to the cloud); only one local model resident at once. `[R7.1–R7.4]`
- [ ] 4.4 Add bounded retry + timeout on the cloud path, then fall back to local and record which reasoner answered. `[R6.3]`

⛔ **CHECKPOINT 4:** a trivial prompt returns a completion from the local analysis model; a `practice` engagement routes reasoning to the cloud teacher, a `real` engagement routes it to the local reasoner (Qwen3) (and makes **no external call**). Confirm only one local model is resident at a time (watch VRAM). `[Validation: VRAM budget + no real→cloud leak]`

---

## Milestone 5 — Interpretation

- [ ] 5.0 Implement `CveValidator.validate()` against a local NVD/OSV source — *exists? matches product/version?* → VALID / NOT_FOUND / MISMATCH — with unit tests (real CVE, made-up ID, right-ID-wrong-product). `[R4.2]` **⟵ slice-blocking fix: CVE fabrication**
- [ ] 5.1 Implement `Interpreter.interpret()`: per-host prompt, findings passed as **delimiter-wrapped untrusted data**, extract-facts-only instruction. `[R4.1, R4.4]`
- [ ] 5.2 Parse the reply into an `Interpretation`; **validate every asserted CVE via `CveValidator` before storing** (drop NOT_FOUND, flag MISMATCH); tag model, provenance class `model_asserted`. `[R4.2, R4.5]`
- [ ] 5.3 Persist interpretations; wire interpretation into the recon flow (after normalize/dedup).
- [ ] 5.4 Test the injection guard: a fixture finding whose banner contains "ignore previous instructions…" → assert the interpreter treats it as data (does not obey it).

⛔ **CHECKPOINT 5 (major — now objective, not a vibe):** on a small **labeled** lab host (known services→CVEs), interpretation identifies **≥ N of M known services** and emits **≤ K false CVEs after validation** (set N/M/K before running). This is the go/no-go on `Foundation-Sec-8B` being good enough — if it can't clear the bar here, that's a design finding to resolve (bigger/different model, or restructure the prompt) *before* building further. `[Validation: interpretation quality]`

---

## Milestone 6 — Copilot query (grounded answer)

- [ ] 6.1 Implement `GraphStore.facts_for_query()` — pull the engagement's assets/findings/interpretations, optional keyword filter. `[R6.1]`
- [ ] 6.2 Implement the grounding prompt: "answer only from these facts; cite the fact ids; if not covered, say so." `[R6.2, R6.4]`
- [ ] 6.2b Implement `ground_guard()` — extract hosts/ports/CVEs from the answer; strip/flag any not in the fact set; unit-test a fully-grounded answer (passes) and an inventing one (stripped). `[R6.2]` **⟵ slice-blocking fix: grounding guard**
- [ ] 6.3 Implement `CopilotQuery.answer()`: retrieve → prompt → reasoner → **`ground_guard`** → `Answer` with grounded fact ids, flagged entities, reasoner used. `[R6.1, R6.2, R6.5]`
- [ ] 6.4 Log every query (question, facts, reasoner, answer) to `run_log`. `[R8.2]`
- [ ] 6.5 Wire `saltpilot ask "<question>"` to the query path.

⛔ **CHECKPOINT 6 (the whole point):** `saltpilot ask "what's the most interesting thing you found?"` returns an answer whose entities are **all traceable to stored facts — the guard lets zero invented hosts/ports/CVEs through**; asking about something not in scope/graph yields an honest "no relevant facts." This is the core-loop proof. `[Validation: grounded answer]`

---

## Milestone 7 — End-to-end validation & honest failure

- [ ] 7.1 Full run on the lab target: `engage → recon → ask`, from a clean DB. `[R8.3]`
- [ ] 7.2 Kill a tool mid-run (or point at a down host) → assert the pipeline degrades, records the failure, still persists and answers over partial results. `[R2.5, R8.3]`
- [ ] 7.3 Run the **Validation Goals** checklist from `requirements.md` and write down the results honestly: parser correctness, interpretation quality, idempotency, grounded-answer/no-invention, VRAM budget, scope-gate block.
- [ ] 7.4 Write a one-page "what the slice proved / what it didn't / what surprised me" note.
- [ ] 7.5 Freeze the Checkpoint-5 labeled set and the grounded-answer spot-checks as a small **held-out regression set**; re-run it on every model or prompt change thereafter (Copilot §13.5) — so a later model swap can't silently regress quality. `[Validation: regression]`

⛔ **CHECKPOINT 7 (release the slice):** every Validation Goal has a recorded pass, or a recorded *finding* with a decision. Only now is v1 "done."

---

## After the slice — the expansion discipline (problems 4 & 5)

Do **not** open the whole design after v1. Add features one at a time, each on its own small spec and each **stress-tested before the next**, roughly in this order (subject to what v1's findings say):

1. **RAG retrieval** — only if v1's naive graph retrieval proved too weak. Validate retrieval quality on real questions.
2. **More recon domains / tools** — subfinder, katana, nuclei; each is one new `ToolAdapter` + parser tests.
3. **The typed graph + exploit-candidates-with-conditions** — grow the relational schema into the node/edge + precondition model; validate candidate quality.
4. **The enrichment loop** — operator findings → confirm → write-back → re-derive; validate a flip end-to-end.
5. **The offense model + attack-path planning** — add on-demand offense; validate advisory plans.
6. **The Rust TUI + MCP boundary** — turn the in-process calls into MCP tools; build the TUI as a client.
7. **The long-haul layer** — Custodian/tiering, Supervisor, saturation, checkpoint/resume, digests — last, and only once there's something worth running for 24h. Do the "two of these fire at once" failure-mode review here.

Each step repeats the same loop: small spec → build → **validate the claim** → only then expand. That is what keeps a years-long project from collapsing under its own scope, and what turns the elegant-but-unproven design into something known to actually work.
