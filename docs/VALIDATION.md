# Saltpilot v1 — Validation Goals (Milestone 7.3)

The Validation Goals from `specs/requirements.md`, recorded honestly. Each is a **recorded PASS**
(with evidence) or a **recorded finding with a decision** — which is what Checkpoint 7 requires to
release the slice. Two goals depend on the physical reference box (RTX 3060 12GB / Ryzen 7 7700 /
32GB / Pop!_OS); those are recorded as **REFERENCE-BOX** with a ready runner, not faked.

| # | Goal | Status | Evidence / decision |
|---|------|--------|---------------------|
| (a) | Both tool parsers produce correct typed findings from real output | **PASS** | `tests/test_nmap_parse.py`, `tests/test_httpx_parse.py` assert the exact `Finding` list from **real captured** `nmap -sV -oX` and `httpx -json` fixtures (+ truncated/malformed salvage). Confirmed live: `tests/test_recon_live.py` runs real nmap and real ProjectDiscovery httpx against a localhost service. |
| (b) | `Foundation-Sec-8B` interpretation clears the objective bar (≥ N of M services, ≤ K false CVEs after validation) | **REFERENCE-BOX** | The interpret→validate machinery is proven (`tests/test_interpret*.py` + a live run over HTTP: a real CVE validated+kept, a fabricated one dropped). The **objective N/M/K measurement is fundamentally a test of the real model on a labeled host** — a stub cannot stand in. **Decision:** run `tests/test_regression.py::test_interpretation_quality_regression` with `SALTPILOT_EVAL_MODEL_URL` set to a real Foundation-Sec-8B; confirm/adjust N/M/K (currently 2/3/1) and fill `expected_cves` for the labeled host. Runner is frozen and ready. |
| (c) | Graph round-trips; re-run idempotent, incl. a host seen as IP and hostname collapsing to one asset | **PASS** | `tests/test_recon_persist.py` (idempotent re-run, exact asset/finding counts), `tests/test_normalize.py` (IP+hostname → one asset via the alias map), `tests/test_store.py` (WAL, schema survives reopen). Confirmed live: the nmap live test re-runs with no new rows. |
| (d) | Reasoner answer is grounded — the guard lets **zero** invented hosts/ports/CVEs through | **PASS** | `tests/test_ground_guard.py`, `tests/test_query.py`, `tests/test_e2e.py`. Confirmed live (Checkpoint 6 + the M7 capstone): grounded entities passed with citations while `9.9.9.9` / `3306` / `CVE-2021-99999` were all rewritten to `[unverified: …]`; a not-in-graph question returned "No relevant facts found." |
| (e) | Peak VRAM stays within budget for one loaded model | **REFERENCE-BOX** | Single-tenant residency **logic** is proven (`tests/test_models.py` + a live swap showing the prior local model unloaded on model change). The **physical VRAM watch needs the 3060.** **Decision:** on the box, load each local model in turn and confirm peak ≈ one ~5 GB model of 12 GB (`nvidia-smi`), no co-residency. |
| (f) | Scope gate blocks an out-of-scope asset **and** a hostname resolving to an out-of-scope IP | **PASS** | `tests/test_scope.py` — the explicit out-of-scope IP/domain cases, resolver-error fail-closed, and `test_hostname_resolving_to_out_of_scope_ip_is_rejected` (the scope-resolution-hole fix). |
| (g) | The loop runs cleanly as a Hermes extension (MCP servers + skill) driven from the `hermes` CLI | **PASS** | Milestone 0 done live: `hermes-agent` v0.19.0 installed; four Saltpilot MCP servers (`scope`/`graph`/`recon`/`copilot`) registered and tool-discovered via `hermes mcp add`/`list`; the recon skill enabled (`hermes skills list`); `run_recon` driven **end-to-end through the `hermes` CLI** (model tool-call → real nmap+httpx → persisted). Reproducible via `scripts/setup_hermes.sh`. |

## Checkpoint 7 — release the slice

**Every Validation Goal has a recorded pass or a recorded finding with a decision** → the slice is
releasable. Five goals PASS (a, c, d, f, g). Two (b interpretation-quality, e VRAM) are recorded
**REFERENCE-BOX** with a ready runner and a concrete decision, because they measure the real model
on the real GPU — which by design cannot be met in a CPU container, and faking them would defeat
the point of the checkpoint.

**Regression carry-forward (7.5):** the grounded-answer spot-checks and the interpretation-quality
eval are frozen in `tests/regression/eval_set.json` + `tests/test_regression.py`; the deterministic
half runs in CI, the model half runs on the box on every model/prompt change (Copilot §13.5).
