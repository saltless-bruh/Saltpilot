# Saltpilot — Gaps Ledger

**The rule this file enforces:** it is **0 or 1**. Code is either *actually implemented and proven*
(1), or it is a **declared gap** (0) tracked here. No placeholder, no look-pretty, no "there to fill
space." Nothing lives in between — if it isn't real, it's a line item below.

This is the single source of truth for what is *not* done or *not* proven in the current codebase —
by **code**, **logic**, or **design**. It uses a task-list ticking system:

- `[ ]` = **open gap** (a real 0 — limitation, hole, or unproven claim in the shipped code)
- `[x]` = **closed** (now a real 1 — implemented *and* proven; add the evidence inline)

Deferred-by-design v1-out-of-scope features are listed **separately at the bottom** so planned
future work is never confused with a hole in what we shipped.

*Last audited: 2026-07-29, against tip `d6b8397`. Suite: 123 passed, 1 skipped. Live spine drive
(real nmap+httpx + grounding guard) passed out-of-pytest.*

---

## What is a real 1 today (proven, not claimed)

These are **functioning**, with evidence — do not re-open them without a reason:

| Capability | Evidence (this audit) |
|---|---|
| Scope gate (fail-closed, resolve→pin IPs) | `tests/test_scope.py`; hostname→out-of-scope-IP rejected |
| Recon: **real nmap + real PD httpx**, fed tool-to-tool | live drive found port 43549, httpx enriched status 200 + title; `tests/test_recon_live.py` (2 passed, 29s) |
| Normalize / dedup / **idempotent** persistence | live re-run added **zero** net-new rows (3 assets / 2 findings both runs) |
| SQLite graph (WAL, null-safe upserts) | `tests/test_store.py`, `test_recon_persist.py` |
| CVE **validator** (drops fabricated/injected) | `tests/test_cve_validator.py`, `test_interpret.py` |
| **Grounding guard** (invented → `[unverified:]`) | live drive neutralized `10.66.66.66` / `3306` / `CVE-2021-99999`; `tests/test_ground_guard.py` |
| 4 MCP servers wired into Hermes | `hermes mcp list` shows scope/graph/recon/copilot all `✓ enabled` |
| Degrade-without-crash paths | `tests/test_e2e.py` (tool dies / model down → still persists + answers) |

The **deterministic spine is a 1.** The gaps below are concentrated in the **model-dependent half**
(never run against real weights here) and in **breadth** (coverage, retrieval, deferred scope).

---

## Open gaps (0 → to close)

### A. Reference-box — needs the real model / real GPU (cannot close in a CPU container)

- [ ] **G-RB1** *(reference-box · blocker for Checkpoint 5)* — **Interpretation quality is unmeasured
  against the real `Foundation-Sec-8B`.** The interpret→validate→persist machinery is proven, but
  only with a *stub* transport. The objective bar (≥N of M services, ≤K false CVEs) has never been
  scored on a labeled host. **Impact:** we do not actually know the local model is good enough — the
  central go/no-go of v1. **Close:** on the reference box, set `SALTPILOT_EVAL_MODEL_URL`, fill
  `expected_cves` + confirm N/M/K in `tests/regression/eval_set.json`, run
  `test_interpretation_quality_regression`, record the number in `docs/VALIDATION.md` (goal b).

- [ ] **G-RB2** *(reference-box)* — **Peak VRAM never physically measured.** Single-tenant residency
  *logic* is proven; the actual "one ~5 GB model within 12 GB, no co-residency" watch on the RTX
  3060 has not happened. **Close:** load each local model in turn on the box, watch `nvidia-smi`,
  record peak in `docs/VALIDATION.md` (goal e).

- [ ] **G-RB3** *(runtime · high)* — **No model server runs in this container, so the intelligence
  half produces nothing here.** `localhost:11434` is down, cloud egress blocked, no ollama process.
  Recon/scope/graph/CVE/guard all run; **interpretation fails per-host (best-effort) and `ask`
  degrades to no-reasoner.** Even Hermes' own tool-calling loop needs the model up. **Impact:** the
  end-to-end agent is only fully alive once a brain is attached. **Close:** serve
  `foundation-sec-8b` (+ the local reasoner) via Ollama on the box; this is the cloud→local switch
  in `SESSION_COMPACT.md` §7.

- [ ] **G-RB4** *(reference-box · low)* — **Cloud teacher path (DeepSeek, `practice`) never hit the
  real API** (egress blocked). Only stub-proven, incl. the cloud→local fallback. **Close:** one
  `practice`-engagement run against the real endpoint on a networked box; confirm fallback records
  who answered.

### B. CVE validation coverage — code/data (partially closeable now)

- [ ] **G-CVE1** *(data · high)* — **The CVE "database" is a 5-entry seed** (3 real: Heartbleed /
  Shellshock / Log4Shell + 2 synthetic), **product-level only (versions null).** The real
  `nvd_local` full mirror is reference-box. **Impact:** on this machine the validator drops nearly
  every real-world CVE as `NOT_FOUND` (safe, but heavy false-negatives), and it silently means
  "validated" ≈ "one of five." **Close:** seed a real NVD/OSV mirror on the box; point
  `SALTPILOT_CVE_DB` / `nvd_local` at it; re-run interpretation over a labeled host.

- [ ] **G-CVE2** *(logic · medium)* — **Version-range matching is under-exercised.** The
  token-product + version logic exists but only one synthetic versioned entry tests it; real CPE /
  semver-range behavior is unproven. **Impact:** version-specific CVEs (the common case) may
  mis-match against real data. **Close:** add real versioned CVEs to the mirror and extend
  `test_cve_validator.py` with real version-range cases.

- [ ] **G-CVE3** *(logic · low)* — **Misconfigured CVE source fails to an empty source that drops
  ALL CVEs.** Fail-safe is correct (drop, don't fabricate) but a bad `nvd_local` path yields zero
  CVEs *silently*. **Close:** log a loud warning when the resolved CVE source is empty/unreadable so
  a misconfig isn't mistaken for "no CVEs found."

### C. Retrieval & guard — logic (deliberately naive in v1)

- [ ] **G-Q1** *(logic · medium)* — **`facts_for_query` is a naive keyword/stopword filter, not
  semantic/RAG retrieval.** A broad question returns *all* facts; a differently-phrased specific
  question can miss facts. **Impact:** answer quality/completeness is retrieval-limited and unproven
  on real question sets. **Close:** the "RAG retrieval" post-slice step — only if v1's naive
  retrieval proves too weak; validate retrieval quality on real questions first.

- [ ] **G-Q2** *(logic · medium)* — **The grounding guard checks invented *entities* (IPs, hosts,
  ports, CVEs), not invented *claims*.** A false assertion that reuses only real entities (e.g. a
  wrong statement about a real host) passes the guard. Unusual hostname formats may also slip the
  regex. **Impact:** grounding is entity-level, not semantic — narrower than "everything is true."
  **Close:** add claim-level grounding (fact-attributed sentence checking) in a later slice; for now
  documented as a known boundary.

### D. Confidence signal — code (decorative-by-design)

- [ ] **G-C1** *(code · low)* — **`confidence` on findings is not a calibrated signal.** httpx
  hardcodes `0.9`; nmap uses `0.5` or nmap's own `conf/10`. It is non-gating by design (Copilot
  §4.4), but as written it is essentially **decorative** and must never be read as a real
  probability. **Close:** either derive it from real evidence strength, or rename/annotate it so no
  consumer treats it as calibrated. (Acceptable to leave open in v1 — flagged so it isn't trusted.)

### E. Interface & operability — integration

- [ ] **G-I1** *(design · low)* — **No standalone `saltpilot` CLI.** `tasks.md`'s "`saltpilot recon`
  / `saltpilot ask`" are realized **only** as MCP tools driven through Hermes (entrypoints are the 4
  `*-mcp` servers). Correct for the on-Hermes design, but there is no direct binary for a
  non-Hermes operator. **Close:** add a thin `saltpilot` console entrypoint if a standalone CLI is
  wanted; otherwise mark as intentional and update the task language.

- [ ] **G-I2** *(integration · medium)* — **Setup has no model-server provisioning or health
  check.** `scripts/setup_hermes.sh` wires servers + points the model at `localhost:11434`, but does
  not start/verify a model. If the model is down, the whole agent loop is dead (see G-RB3) with no
  early signal. **Close:** add a preflight to `setup_hermes.sh` that checks the model endpoint and
  fails loudly with the fix.

### F. Recon breadth — coverage

- [ ] **G-R1** *(design · medium)* — **Only localhost has ever been scanned.** No real remote
  authorized target → latency, rate-limits, and hostile/odd banners at scale are unproven. **Close:**
  run against an authorized remote lab host on the reference box (`SESSION_COMPACT.md` §7.5).

---

## Deferred by design — NOT v1 gaps (planned "after the slice")

These are **intentionally unbuilt** in v1 (see `specs/tasks.md` → "After the slice"). Listed for
completeness; they are *scope*, not *holes*. Ticking here means "started as its own validated
slice," not "should have been in v1."

- [ ] **D-1** More recon domains/tools (subfinder, katana, nuclei) — each = one `ToolAdapter` + parser tests.
- [ ] **D-2** Typed graph (node/edge + preconditions) + exploit-candidates-with-conditions.
- [ ] **D-3** Enrichment loop (operator finding → confirm → write-back → re-derive).
- [ ] **D-4** Offense model + attack-path planning (advisory).
- [ ] **D-5** Rust TUI + MCP boundary as a client.
- [ ] **D-6** Long-haul layer (Custodian/tiering, Supervisor, saturation, checkpoint/resume, digests).

Each follows the same discipline: small spec → build → **validate the claim** → only then expand.

---

## How to work this ledger

1. When you close a gap: flip `[ ]`→`[x]`, append the **evidence** (test id / measured number /
   commit) inline — same bar as the "real 1" table above. No tick without proof.
2. New gap discovered mid-work → add it here immediately with an ID, don't leave it implicit.
3. The **reference-box block (A) + G-CVE1 + G-R1** are the ones the planned local IRL test closes —
   they are the reason for the cloud→local switch, tracked in `docs/VALIDATION.md` and
   `specs/SESSION_COMPACT.md` §7.
