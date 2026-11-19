# Saltpilot — Auto-Recon Blueprint

**Part of:** Saltpilot. The **Main Proposal** is the source of truth for the program-level view, the integration with the Copilot, and shared infrastructure; the **Knowledge-Architecture Blueprint** owns the knowledge layer, including how recon reads and writes it (its §7). This blueprint details one of Saltpilot's two features — the autonomous Auto-Recon Engine (breadth).

**Version:** 1.15
**Status:** Design baseline
**v1.15 — knowledge-layer wiring:** added the “recon owns no knowledge stores of its own” clarifier (§5.2) and pointed graph reads/writes at the **Knowledge-Architecture Blueprint** (§3 scope model, §7 recon’s read/write contract; the node schema stays Copilot §6).
**v1.1 added:** the concrete recon processing pipeline — deterministic normalization, the two-tier interpreter/reasoner split, and the learning-doc contract (§5.1–5.4).
**v1.2 added:** a non-LLM noise-filter stage between Normalize and Interpret (§5.5), adapting BIFAI-NET's compute-proportional scorer (C5), density, and calibration ideas.
**v1.3 added:** the progressive general→specific recon workflow (waves W0–W3), the copilot-activation point, bidirectional human-steered depth, and a workflow diagram (§7).
**v1.4 added:** failure handling and resilience — isolation, classify-and-respond, visible coverage gaps, fail-closed scope, and crash resume (§7.4).
**v1.5 added:** tool management — manifests, structured invocation, version adaptation by introspection, and the preflight tool-doctor with a tell-by-default / fix-on-opt-in boundary (§4.1).
**v1.6 adds (mined from the auto-pentest proposal):** hostile-tool-output defense (§5.6), a bounded expansion budget (§6), critical-finding escalation (§7.5), and a HardwareArbiter for tool/inference resource contention (§8).
**v1.7 adds:** exploitability and defensive-posture enrichment of findings (§5.7), feeding the Copilot's attack-path brainstorming.
**v1.8 adds:** the recon execution model — a local Git-like DAG of hash-chained sprint-blocks, with re-recon as forward re-execution (never a revert) filtered by coverage/precondition records (§7.6).
**v1.9 reworks the HardwareArbiter (§8.1):** with the copilot's reasoning on cloud and scanners GPU-free, the arbiter now schedules single-tenant GPU turns between the two on-demand local models (batched, keep-alive) rather than refereeing tool-vs-inference contention; scanners run in parallel, never queuing for the GPU.
**v1.10 adds the recon-side long-haul layer (§8.2):** the Custodian (hot/warm/cold graph tiering, DAG compaction, GC, heap watermark), the Supervisor + process janitor (timeouts, reaping, FD/process backpressure, component restart), checkpoint/resume, steady-state data hygiene (WAL + write-queue, reconciliation, adaptive filter recalibration), and saturation/backpressure (monitoring-cadence backoff, trigger coalescing, VRAM-swap hygiene). Native marathon support (Main Proposal §4.2, Principle 8).
**v1.11 — review fixes + Workbench:** §4.1 reframed as the category **Workbench** layer (model emits intent, never commands; resolves+gates hostnames itself; shares facts not guesses). Output-side validation: interpreter CVE claims verified against a real source before storing (§5.2). Host canonicalization + service-as-attribute identity (§5.1). Reconciliation mode/cost-gated; fact precedence (operator>tool>model) + snapshot reads; "settled" defined for tiering (§8.2).
**v1.12 — full-read consistency pass:** §5.2 reframed from a two-*model* split to two *stages* (interpret + reason) on the analyst seat (Foundation-Sec real / V4 practice), fixing a cross-file contradiction with Copilot §4 and the practice=Qwen3+V4 rule; §8.1 HardwareArbiter rewritten to the one-local-model-at-a-time premise across three models (reasoning is local on real work, not off-box); §5.1/§5.7/§7.3-diagram interpret labels mode-neutralized; §8.2 cross-ref fixed (write-back gate is Copilot §4.4).
**v1.13 — diagrams + shared-stack clarifier:** added a **recon stack/architecture diagram** (§7.3, above the workflow diagram) and a **Workbench intent->command diagram** (§4.1). Made explicit that Auto-Recon owns no models of its own — it uses the shared stack (Main Proposal §4 / Copilot §4), the broker and analyst seat only, never the offense seat (§5.2); the stack diagram references the shared seats rather than redrawing them.
**v1.14 — workbench update mechanism tightened (§4.1):** made the robustness path explicit — version-keyed command templates + parsers, a contract self-test (assert output parses into the expected finding shape) as the real verifier, with --version/--help demoted to detection/assist (not an auto-remapper); capability-fallback + tool-doctor coverage note as containment; and the live intent catalog (read fresh every call, never in weights) as why the model needs no change-notification.
**Lineage:** descends from the Auto-Pentest Framework / *Orchbiter*. **Program context & integration with the Copilot:** see the Saltpilot Main Proposal (source of truth); the Copilot is the companion feature this engine hands off to.

---

## 1. Purpose and Scope

The Auto-Recon Engine has **one job: reconnaissance**, done brutally well, across every domain — web, cloud, apps, OS/internal, network, and (aspirationally) hardware. It maps a target's attack surface as exhaustively as the engagement allows.

It is deliberately **not** a full-chain auto-pentest. The autonomous phase is fenced to *information-gathering* and **terminates at a clean handoff** to the human-driven Pentest Copilot. It maps the surface; the human exploits it.

**Why recon-only.** AI offensive capability is strongest at reconnaissance and degrades through the kill chain. Pointing autonomy at recon aims it at the one place it actually works. Recon is also breadth/coverage/tedium — ideal for tireless automation — and unlike full-chain, it has a *definition of done* (the surface is mapped), so it is bounded and shippable.

**Two modes** (§3): **White-pentest** (loud, exhaustive — the default) and **Red-stealth** (quiet, OPSEC-aware, detection-evading).

**Authorized use only.** Recon that expands automatically can wander out of scope faster than any other phase, so scope-gating the expansion loop (§6) is the single most important control in this system.

---

## 2. Relationship to the Pentest Copilot (the unified session)

The Engine and the Copilot are one *experience* and two *components*.

**The unified session.** A Pentest Copilot session **opens with autonomous recon**. The session starts, the Engine maps the surface and writes it into the Copilot's engagement state and graph, and then control hands to the human-driven copilot, already loaded with the target. Recon establishes the engagement — the session's "main topic" — exactly the way the opening of a chat session sets the context for everything that follows.

**Combine the experience, keep the components modular.** The Engine remains a distinct, reusable module — it can run standalone, on a schedule, or as the session opener. The seam moves from "two tools the operator bridges by hand" to "one session: autonomous opener → human copilot," with the Engine still separable underneath. This preserves the project separation established earlier while delivering a single workflow.

**Why this recombination is safe** (where full auto-pentest was not): the autonomy is fenced to recon and **terminates**. It is bounded information-gathering with a clear "done," not autonomous exploitation. At the handoff, the human drives — every offensive action after recon is human-initiated, per the Copilot's design principle (Copilot spec §1).

---

## 3. The Two Modes (build big → small)

**Build order: White first, then constrain into Red.** Stealth is *subtraction*, not a separate build. You cannot make something stealthy that does not yet work, because stealth is defined by *what you choose not to do*. So build the maximal (White) system first, then add a discipline layer that holds it back (Red).

| | White-pentest (default) | Red-stealth |
|---|---|---|
| Goal | Maximum coverage and speed | Map the surface **without being detected** |
| Detection | Irrelevant | The primary constraint |
| Use | Pentest, bug bounty, audit, CTF | Adversary simulation / true red team |
| Tooling | Aggressive (masscan, full nuclei, brute content discovery) | Quiet equivalents (slow nmap, targeted probes, passive-heavy) |
| Pace | As fast as the target tolerates | Low-and-slow, jittered |
| Surface touched | Everything in scope | Only what is strictly needed |

**Red-stealth is a policy layer over the identical modules**, not a separate engine. It applies: passive-first / active-minimal, rate-limiting + timing jitter, source rotation / proxying, quiet tool selection, detection-signature avoidance (no known-bad user agents, no aggressive scan patterns), and scope-minimal touching. The mode is chosen at session start and governs every module's behavior through one shared policy object.

**Honest limit:** Red mode *reduces* detectability; it never guarantees non-detection. Treat it as best-effort OPSEC, not invisibility.

---

## 4. Architecture: Modular Domains

A single engine cannot cover all domains — they use wildly different tools. The Engine is a set of **pluggable domain modules** behind a common orchestrator and a common attack-surface schema (§9).

| Module | Covers | Wraps (examples) |
|---|---|---|
| OSINT / passive | Domains, DNS, certs, ASN/netblocks, leaked secrets, employees, tech footprint | crt.sh/CT logs, subfinder/amass (passive), Shodan/Censys, GitHub dorking |
| Web | Subdomains, content/endpoint discovery, params, APIs, JS analysis, WAF/tech fingerprint | amass/subfinder, ffuf/feroxbuster, katana, nuclei, Wappalyzer, **reNgine-style engines** |
| Cloud | Public buckets/blobs, exposed services, IAM/config (with creds), K8s exposure | cloud_enum, ScoutSuite, Prowler |
| Network / host | Host discovery, port/service/OS fingerprint, protocol enum | nmap, masscan/naabu, SNMP/SMB/LDAP enum |
| Apps (mobile/binary) | APK/IPA static analysis, endpoints/secrets, thick-client analysis, SBOM/SCA | MobSF, apktool, dependency/SCA scanners |
| OS / internal (AD) | Users/groups/ACLs/trusts/GPOs, shares, Kerberos, internal mapping | BloodHound/SharpHound, enum4linux-ng |
| Hardware / IoT / RF | Firmware extraction, exposed services, wireless enumeration | binwalk, firmware tooling, SDR/wireless tools |

**Wrap mature tools; don't reinvent.** reNgine already does exhaustive *web* recon with correlation and a database; reconFTW runs best-of-breed tool pipelines; ScoutSuite/Prowler own cloud config; BloodHound owns AD. The Engine's differentiation is **multi-domain breadth + AI orchestration + the Copilot handoff**, not rebuilding any single scanner.

### 4.1 The Workbench — category tool layers behind an intent interface

A model that free-writes shell commands from memory is a liability: its tool-syntax knowledge is frozen at training time, wrong for niche tools, blind to version changes, and — for a cyber-*tuned* local model — may be missing the tool's flags (or the tool) entirely. So **the model never writes a command, and never names a tool or a flag. It expresses *intent*; a Workbench translates.**

**What a Workbench is.** A Workbench is the tool layer for one recon **category** — a *web* workbench, an *app* workbench, a *cloud* workbench, a *network* workbench, an *OS/AD* workbench, an *OSINT* workbench. Each exposes a small set of **category intents** (what one can *want* to do there — "discover services on this host", "enumerate subdomains of this domain", "probe web technology on these hosts", "check these hosts against known-vuln templates") and owns everything behind them: which tool serves the intent, how to build the exact command for the *installed* version, and how to normalize the output. The model picks an intent and supplies typed parameters (target, depth, wordlist-size); the workbench chooses the tool and renders the command. **The model cannot hallucinate a command or a flag, because it never touches one** — it names a goal; the workbench knows the how. (This is the reason a fine-tuned local model's stale tool knowledge can't produce a dead command: it isn't allowed to produce a command at all.)

```text
  analyst seat  -->  emits INTENT + typed params
                     (e.g. "probe web on these hosts", depth=fast)
                                  |   never a command, never a flag
                                  v
  +==============================================================+
  |  WORKBENCH   (category: web)                                 |
  |    1  pick the tool for the INSTALLED version                |
  |    2  resolve hostname -> re-check IP vs scope -> pass IP    |
  |    3  render the exact command line                          |
  |    4  run it: Docker sandbox · timeout · child-reaped        |
  |    5  parse structured output -> common finding schema       |
  +===============================|==============================+
                                  |  normalized findings
                                  v
            pipeline (§5.1)  ->  graph  ->  handoff

  The model names a GOAL; the workbench owns the HOW. Because its
  tool knowledge may be stale or missing, it is never allowed to
  emit a command. Update a tool -> re-introspect (--help) -> the
  workbench refreshes -> no model retraining.
```

**Why category workbenches, not one flat tool list.** Each category has its own intents, tools, output shapes, and update cadence. Splitting by category keeps each workbench small and independently maintainable, matches how recon is organized (§4), and lets the model reason at the level it is good at ("I want web tech on these hosts") instead of the level it is bad at ("`httpx -json -td -sc -title …`").

**Each workbench declares, per intent:**
- **Intent → tool(s)** — which installed tool serves it, with fallback ordering (§7.4) when the primary is missing.
- **Parameter contract** — the typed parameters the model may set (not raw flags), with constraints; a deterministic renderer builds the CLI for the installed version.
- **Output → normalizer** — the parser turning the tool's *structured* output (XML/JSON) into the common finding schema (§5.1).
- **Scope discipline (closes a gate-bypass).** The workbench **resolves any hostname to an IP itself, re-checks that IP against scope, and passes the *IP* to the tool** — never a hostname the tool would resolve on its own. Otherwise a tool's internal DNS could reach an IP the scope gate never saw (§6). Scope's fail-closed guarantee only holds if tools never do their own resolution on a gated target.
- **Version & health** — how to check the installed version, plus install/upgrade commands.

**Cross-category cooperation shares facts, not guesses.** A workbench that consumes another's output must not inherit its *classifications*. Concretely: the web workbench does **not** trust the network workbench's service labels to decide what is HTTP — it probes the open ports itself and decides, because a web service on an odd port (or mislabeled by the scanner) would otherwise be silently lost. Workbenches pass *facts* (open ports), not *interpretations* (this port "is" http).

**How it adapts when a tool updates — and why the model is never told.** A tool version lives entirely in the *lower* interface (the command line + the output parser), so a flag rename or a JSON-schema change is invisible to the model by construction — the intent "probe web" does not move. The workbench absorbs the change in four layers, most-automatic first:
- **Version detection is the trigger.** The tool-doctor runs `--version` at engagement start (and can on a schedule). If the detected version matches what the mapping was written for, nothing else happens.
- **Version-keyed command templates + parsers are the real robustness.** The workbench does not store "the nuclei command"; it stores command templates and output parsers **keyed by version range** (e.g. `nuclei ≥3 → -jsonl` + its parser; `nuclei 2.x → -json` + its parser). A known breaking bump (v2→v3) is therefore a *non-event*: the workbench already holds both and selects by detected version.
- **A contract self-test verifies the mapping, by behaviour not by help-text.** After a version change, run the tool against a known fixture (a localhost test service / canned input) and assert the output **parses into the expected finding shape**. Parses → the mapping still holds. Fails → it's broken; flag it. (`--version`/`--help` are used to *detect* a version and to *diff* what changed when you write an update — **not** as an auto-remapper; scraping help text into a correct command for an arbitrary tool isn't reliable, so it is demoted to detection/assist.)
- **On a break with no known mapping: contain, then flag.** The **capability-fallback** (§7.4) routes that intent to an alternative tool so recon keeps running, and the tool-doctor raises a coverage note ("amass 4.x detected, mapping is for 3.x → routed subdomain-enum to subfinder"). The engine degrades coverage, never stalls.

Genuinely new breaking versions still need *you* to add the new version's template + parser — but that is a small, localized edit to *one category module* that touches neither the model nor the rest of the system. The system's job is **detect → contain → flag**, so you make a five-line change at your leisure instead of hitting a silently-broken scan mid-engagement. Volatile tool knowledge is externalized into the workbench and refreshed from reality, never trusted to model weights (the same principle as RAG-grounding the interpreter, §5.2).

**The model stays current by construction — there is no "change notification."** The only thing the model must be current on is the **intent catalog**: the menu of intents, their typed params, and a one-line description each. That catalog is **injected into the model's context at runtime and read fresh every call — never baked into weights** — so the model is always in sync with what the workbench can actually do *right now*, with no notify step:
- A tool update *adds* a capability (or you add a tool) → a new intent appears in the catalog → the model can request it next session, no retraining.
- An intent *breaks* with no fallback → it is marked `unavailable`/`degraded` in the catalog → the model simply doesn't offer or use it (the operator sees the coverage gap).
- An intent is *fallback-routed* to another tool → the model still sees it as available; the substitution is transparent to it and surfaced only to the operator.

**Tool health — the "tool-doctor".** A preflight pass at engagement start checks every tool the planned waves need is present and compatible, emitting an actionable report *before* recon runs. On a miss or runtime failure, deterministic checks (`which`, `--version`, exit codes, error patterns) classify the cause (not installed / outdated / not in PATH / missing dep / permission / broken), and the workbench's stored install/upgrade command makes the note actionable. **Boundary: diagnose-and-tell by default; self-fix only on opt-in** (auto-installing software is consequential — supply-chain and breakage risk — so the default hands the operator the exact command; only explicitly-enabled auto-remediation for trusted package managers applies it, in the sandbox). Meanwhile the capability-fallback (§7.4) tries an alternative so a broken tool degrades coverage and raises a flag rather than stalling.

---

## 5. The AI's Role: Orchestrator and Synthesizer, Not Scanner

The scanners are deterministic and do the actual discovery. The AI never runs the scans itself and **never invents findings** — all ground truth comes from tools. Its four jobs:

- **Adaptive expansion.** Recon is an *expanding graph*: a found subdomain spawns a port scan, a found cloud IP spawns cloud enum, a found endpoint spawns parameter discovery. The AI drives that expansion recursively and tirelessly — the "brutal" the project is named for.
- **Cross-domain correlation.** Tie findings into one coherent map (this IP → this ASN owned by the org → runs this service → maps to this CVE → reachable from this subdomain).
- **Triage / prioritization.** Exhaustive recon is a firehose; the AI ranks the interesting surface so the operator is not drowned. Without this, brutal recon is just noise.
- **Coverage assurance.** Methodology-complete sweeps (PTES / OWASP / domain checklists) so nothing is missed.

Because ground truth comes from deterministic tools, autonomy is *safe here* in a way it is not during exploitation — there is nothing for the model to hallucinate into a false finding.

### 5.1 The processing pipeline

Raw scanner output is not model-friendly — nmap XML, nuclei JSON, BloodHound graphs, ScoutSuite dumps are dense and domain-specific, and feeding them straight to a model produces noise because the model burns capacity on *parsing* and *recall* instead of *reasoning*. The recon function is therefore a pipeline that turns raw output into meaning, then into decisions. It loops until coverage is complete and scope is exhausted:

1. **Plan** (reasoner) — given the known surface + scope + mode, select the next recon task(s).
2. **Execute** (deterministic tools) — the domain module runs its specialist tools, scope-checked (§6) and mode-paced (§3). Produces raw output.
3. **Normalize** (deterministic adapters) — *before any model sees it*, a thin per-tool adapter parses raw output into a common structured form (nmap XML → `{host, port, service, version, banner}`; nuclei JSON → `{template, severity, url}`). Never make a model do parsing a parser can do — this removes the "model can't read XML" problem and cuts tokens by an order of magnitude. The normalizer also **canonicalizes host identity** — resolving and unifying IP↔hostname so one machine is one asset — and treats the scanner's *service label* as an attribute, **not** part of identity. Asset identity is `(canonical_host, port)`; a re-scan that reclassifies a port therefore updates the asset instead of duplicating it, which is what actually makes re-recon idempotent (§9).
4. **Filter** (cheap, non-LLM) — a lightweight scorer drops or aggregates routine findings so only high-signal and uncertain ones reach the interpreter (§5.5). This is what keeps the firehose out of the model's context.
5. **Interpret** (the analyst seat → *learning doc*) — adds *meaning* to the surviving findings: Foundation-Sec on real work, V4 on practice (§5.2, §5.3).
6. **Correlate** (reasoner) — consumes the learning docs (never raw data), builds the unified attack-surface graph, dedups, links across domains, and decides **expansion**: what new recon tasks the findings spawn (→ back to Plan).
7. **Triage** (reasoner) — rank the surface into the prioritized view for the handoff (§7).
8. **Persist / hand off** — write graph + engagement state (§7, §9).

### 5.2 Interpret, then reason (digested docs, never raw output)

**Recon owns no models of its own.** It uses the program's shared model stack (Main Proposal §4 / Copilot §4) — specifically the **broker** and the **analyst seat**, never the offense seat (recon never exploits). What follows is only *which pipeline stage calls which seat*.

**Recon owns no knowledge stores of its own, either.** It uses the shared knowledge layer (Knowledge-Architecture Blueprint): it **writes** `engagement`-scope facts (its validated pipeline output) and **reads** general-scope knowledge, the corpus, and scout — never writing general scope. The full read/write contract is that blueprint's §7.

The pipeline splits two *stages* so the expensive reasoning never wastes context on raw scanner output. Both map onto the model stack (Copilot §4), and the discipline is that reasoning works over *digested* material, never the firehose:

- **Interpret — the analyst seat** (`Foundation-Sec-8B` on real work, `DeepSeek V4` on practice). It reads the normalized findings and adds *meaning* — what `OpenSSH 7.4`, a public-ACL S3 bucket, or a Kerberoastable account implies — compressing megabytes of raw output into a compact, security-aware **learning doc** (§5.3). On real work Foundation-Sec does it (domain knowledge baked in); on practice V4 does it (and explains, since practice is for learning).
- **Reason (plan / correlate / triage / expansion) — the same analyst seat**, now working only over the *digested learning docs*, and reading the graph through the **Qwen3 broker's task-scoped brief of pointers** (§4) rather than the whole graph. It decides what new recon the findings spawn (→ back to Plan).

So the reasoning stage never sees a line of raw nmap output — only the interpret stage's brief and the broker's pointers. That is what keeps recon inside a small context on a 12GB box: interpretation compresses the firehose before it reaches reasoning, and the broker hands down references instead of the whole graph. (The local models involved — the analyst seat on real work, and the Qwen3 broker — still load one at a time, §8.1.)

Two refinements make the interpreter reliable:
- **RAG-ground it.** The interpreter pulls relevant CVE/technique facts from the knowledge graph + corpus (the same layer the Copilot uses) into its context, so interpretation rests on *retrieved facts*, not stale parametric memory — critical for the version-specific CVE claims it would otherwise hallucinate.
- **Structure its output.** The learning doc is schema-constrained (§5.3), so the interpreter must fill fixed fields — no vague hand-waving (the anti-laziness discipline, Copilot spec §4.3).
- **Validate its claims — don't just trust them.** RAG-grounding reduces hallucinated CVEs on the *input* side; a deterministic check closes the *output* side. Every CVE the interpreter asserts is verified against a real source (a local NVD/OSV lookup) — *does this ID exist, and does it match this product/version?* — **before** it is stored. Unverifiable or mismatched IDs are dropped or flagged, never persisted as fact. This is the missing cheap-deterministic-*after*-model half of the core principle (the same principle that gates the *input* is pointed at the *output*): the model proposes, a parser disposes. It generalizes — **wherever a model asserts a checkable fact, a deterministic validator checks it before it becomes graph truth.**

### 5.3 The learning doc (the interpretation contract)

The learning doc is the typed artifact the interpreter writes and the reasoner consumes — the same provider-agnostic, on-disk contract-boundary discipline as the coding framework's `tasks.json`. Per asset or recon task it carries:

- **Found** — the normalized findings (what the tools saw).
- **Meaning** — security interpretation in plain terms (exposed services, versions, misconfigs).
- **Significance** — why it matters, mapped to MITRE ATT&CK / CWE / CVE.
- **Exploitability** — applicable exploits/tools/techniques and public-exploit availability/maturity (§5.7); reference, not execution.
- **Defenses** — defensive posture in front of this asset: WAF, filtering, headers, rate-limit/lockout, IDS hints (§5.7).
- **Next** — suggested follow-up recon / expansion.
- **Provenance & confidence** — which tool, raw-evidence reference, and how sure (feeds §13.2 untrusted-content handling in the Copilot and the graph's trust metadata).

It is durable and triple-purpose: input to the reasoner, a human-readable brief, and the raw material the handoff distills into graph nodes (§7).

### 5.4 Why this tackles every category

The pipeline is **category-agnostic; only the tools and adapters are category-specific.** Each domain module (§4) supplies exactly three things — its tool set (Execute), its parsers (Normalize), and a little domain context for the interpreter (Interpret) — then plugs into the identical Plan → Filter → Interpret → Correlate → Triage spine. Web, cloud, network, AD, mobile, and hardware findings all flow through one pipeline and correlate into one map because they share the common normalized schema and the common learning-doc schema. Adding a new category is adding a module, not changing the engine.

### 5.5 Noise filtering before the interpreter (the cheap pre-LLM gate)

Even normalized, recon output is a firehose — and letting an *LLM* decide what is noise re-bloats the very context you are trying to protect. The fix is a **non-LLM filter between Normalize and Interpret**, so the model never sees the firehose at all. This adapts the compute-proportional "cheap scorer before the expensive model" pattern from the BIFAI-NET proposal (its **C5** layer: a lightweight autoencoder scores flows; the heavy model runs only on what it flags), tuned for recon findings rather than network flows.

The filter is a cheap CPU pipeline:
1. **Dedup + rule-based junk removal** (deterministic) — exact/near-duplicates collapsed; known artifacts (closed/filtered ports, standard boilerplate) dropped unless requested.
2. **Commonality / density scoring** — adapting BIFAI-NET's *Prior Cluster Density*: findings in dense "expected" regions (default banners, ubiquitous services, standard responses) score low-signal; findings in sparse/novel regions score high-signal. The 10,000th routine HTTP 200 is noise; the one odd service on an odd port is signal.
3. **Anomaly scoring** — a lightweight autoencoder (or isolation-forest / one-class model) trained on "expected" findings emits a reconstruction-error/anomaly score; high error = interesting. This is BIFAI-NET's C5 autoencoder-scorer repurposed; it runs on CPU and never touches the model context.
4. **Calibrated threshold + route** — scores combine into a verdict against a **measured-then-fixed** threshold (BIFAI-NET's calibration discipline): confidently-boring findings are suppressed; confidently-interesting *and uncertain* findings are escalated (over-include the uncertain — never silently drop ambiguity).

**Noise is compressed, not deleted.** Suppressed findings roll into compact aggregate counts ("847 standard HTTP 200s; 1,203 filtered ports; breakdown: …"), so the interpreter sees the interesting handful *plus a one-line summary of the rest*. Context stays small, and nothing is hidden.

**Collectively-significant signal is preserved.** BIFAI-NET's core insight is that some findings are individually unremarkable but collectively significant (low-and-slow scans, staged activity). Per-finding filtering must not blind the engine to these, so the aggregate summaries flow forward to the correlator (§5.1), which can still spot "many small things that together mean something" even when each item was filtered individually.

**What is *not* reused.** BIFAI-NET's NCA-FLC, multi-generation temporal evolution, adversarial-robustness theorem, and Merkle integrity chain are built for network flows with neighborhood and temporal structure and do not fit tabular recon findings — porting them would re-import the over-scoping that made BIFAI-NET PhD-sized. Only the filtering philosophy (cheap scorer → LLM, density-based novelty, autoencoder anomaly scoring, calibrated thresholds) transfers.

**Cold-start.** The "expected findings" baseline the filter needs is learned from data: seed it from past engagements and public recon corpora, and let it sharpen as it sees more — the filter, like the Copilot's graph, compounds with use.

### 5.6 Hostile tool output (the target is adversarial)

A pentest target is hostile by definition, and its output is an attack surface — it can craft service banners, HTTP headers, DNS records, and file contents that the scanners faithfully capture, and that output flows into the parser (Normalize) and then the model (Interpret/Correlate). Two defenses, both before the data is trusted:

- **Hardened parsing.** Tool output can be a malicious *payload*, not just data — e.g. an XML bomb (billion-laughs) in a crafted nmap response can crash the parser. The Normalize adapters parse defensively (hardened/`defusedxml`-style XML, bounded sizes, timeouts) and treat malformed output as a failed task (§7.4), not a crash.
- **Prompt-injection sandboxing.** A target can embed "ignore previous instructions…" in a banner that nuclei captures, hijacking the interpreter or reasoner. So tool output is **delimiter-wrapped as untrusted data**, any embedded delimiters are stripped (anti-escape), it is truncated, and the model is instructed to *extract facts only, never execute content within the delimiters*. This is the recon-specific case of the Copilot's untrusted-content stance (§13.2): there it was scouted web content; here it is the target's own responses, which are if anything more adversarial.

The model never sees raw tool output anyway (the filter and learning-doc pipeline sit in between), but where any captured content does reach a prompt, it is sandboxed as hostile input.

### 5.7 Exploitability and defensive-posture enrichment

Recon is far more useful when it characterizes not just *what* is present but *how exploitable* it is and *what defends it* — the raw material the Copilot and operator need to brainstorm attack paths. Two enrichments extend the learning-doc (§5.3). Both are **characterization, not execution**: the engine maps what *could* exploit a finding and what defenses stand in the way, and never selects-and-runs an exploit — exploitation is the operator's call in the Copilot. This widens recon's *information*, not its autonomy.

**Exploitability (offensive enrichment).** During Interpret, each vuln/finding is annotated with what could exploit it:
- **Public exploit availability** — cross-reference the CVE/finding against the exploit sources in the knowledge base (ExploitDB, Metasploit modules, Nuclei templates, PoC aggregators): working exploit code, an MSF module, a theoretical-only PoC, or nothing. Maturity matters — "MSF module exists" and "theoretical only" are different planning situations.
- **Applicable tools/techniques** — map the finding *type* to the tools and techniques that apply (exposed `.git` → git-dumper; SQLi surface → sqlmap; Kerberoastable → roast + hashcat; public S3 → aws cli), indexed on MITRE ATT&CK / the skills.
- RAG-grounded (the interpreter retrieves from the exploit/technique corpus, §5.2), so claims rest on retrieved facts. It is a **reference annotation** — "here is what exists and applies" — not the engine wielding the tool.

**Defensive posture (the "how the other end blocks" dimension).** Exploitability is theoretical until the defenses are known, so recon profiles them as a cross-cutting dimension, each module detecting what is relevant to it:
- **Web** — WAF presence and fingerprint (wafw00f / nuclei), security headers (CSP/HSTS/cookie flags), blocked methods, login rate-limiting / lockout / CAPTCHA / MFA.
- **Network** — filtered-vs-closed ports (firewall behavior), rate-limiting, tarpit/IDS hints.
- **Cloud** — bucket policies, security services, exposure controls.

Two connections fall out naturally: **getting blocked is itself defensive intel** (failure-as-signal, §7.4 — a scan that trips a WAF reveals the WAF and what it catches), and the **defense profile feeds Red-stealth mode** (§3 — the IDS/WAF posture is what informs low-and-slow choices).

**Exploit candidates with conditions.** Combined, exploitability and defensive posture produce, per vuln, an **exploit candidate** the planner can act on: its *availability* (available vs theoretical), its *preconditions* (from the matched `technique`, Copilot §6), its *condition status* — which preconditions the recon data meets, which are unmet, and which are **blocked by an identified defense** — and a *feasibility* verdict (*ready* / *conditional, needs X* / *blocked, needs a bypass*). So "SQLi on api.acme.com" becomes "SQLi — blocked: Cloudflare WAF → condition: WAF bypass; otherwise ready." *Conditions* are the through-line of the whole system: the graph's preconditions, defenses as precondition-modifiers, and the Copilot's adapt-first reasoning all speak the same language.

**How candidates are generated (the method).** The reasoner (the analyst seat, §5.2) is the engine, but it is *engineered to consume extracted structured facts rather than reason from memory* — grounding it so it cannot freewheel:
- **Deterministic availability lookup** — cross-reference each CVE/finding against exploit sources (ExploitDB, Metasploit module DB, Nuclei metadata, Vulners/PoC aggregators). This answers "does an exploit exist, and how mature" authoritatively; the model never guesses it.
- **Precondition structure** — the matched `technique` node supplies the precondition skeleton, with the observed defenses applied as modifiers. The model never invents preconditions; it fills and evaluates a provided structure.
- **Reasoning over the extracted facts** — the model then assembles the candidate-with-conditions and handles the *novel / theoretical* combinations the two deterministic sources cannot express on their own (an unusual chain, a bypass hypothesis, an adapted technique).

This is a C-centric design grounded by deterministic A/B extractors: authoritative facts in, reasoning on top, no ungrounded invention.

Both enrichments land in the learning-doc and flow to the Copilot at handoff, where they become the basis for attack-path brainstorming (Copilot Blueprint §7.8) — reasoning about *viable* paths and *bypasses* with the defenses factored in, which is what turns a vuln list into a plan.

---

## 6. The Expansion Loop and Scope Gating (the safety core)

Automatic expansion is the entire value of the Engine, and also its entire risk: a loop that pivots subdomain → IP → ASN → more hosts → cloud will happily start scanning third parties, which is illegal and engagement-ending.

- **Scope gates the expansion loop, not just the seed.** Every newly-discovered asset is checked against the authorized scope **before** it is recon'd. Out-of-scope is a hard stop, never a suggestion.
- **Passive vs active separation.** Passive OSINT (no packets to the target) may run freely; active probing is scope-gated and rate-limited.
- **Reuse the AuthorizationManager** (salvaged from the auto-pentest framework / shared with the Copilot), extended to evaluate scope on *each expansion step*.
- **Mode-aware pacing.** White mode rate-limits to avoid DoS-ing the target; Red mode rate-limits far harder for stealth.
- **Bounded expansion (budget, not just scope).** Scope-gating stops the loop going *out of bounds*, but nothing stops it going *infinitely deep within bounds* — the reasoner can keep spawning tasks (subdomain → resolve → scan → find more → …) or loop. So the loop carries an explicit budget: max expansion depth, max tasks per wave, and a total recon time cap. Scope-gating is the *where*; the budget is the *how-much*. Hitting a budget is a graceful stop with a coverage note (§7.4), not a failure.

---

## 7. The Progressive Workflow and Handoff

Background recon only helps if the copilot has context to start with, so the **order** of recon matters as much as the recon itself. The workflow runs **general → specific**: fast broad tools first (to activate the copilot with an immediate working surface), then heavy tools going deep underneath while the operator is already working. Each wave is *targeted at what the previous wave found* — the heavy tools never run blindly on everything.

### 7.1 Recon waves (general → specific)

| Wave | Depth / pace | Tools (web example) | Role |
|---|---|---|---|
| **W0** | Passive / instant (~seconds) | WHOIS, DNS, CT-log subdomains, tech fingerprint | Skeleton before any scanning; no packets to target, always safe |
| **W1** | Fast active / broad (~minutes) | nmap top-ports, httpx (alive/title/tech), fast resolution | The "general" pass — produces a real working surface. **Copilot activates here.** |
| **W2** | Deep / targeted (background, long) | full nmap, ffuf/feroxbuster, nuclei, params, JS analysis | Run *only on what W0/W1 flagged interesting*; streams into the live session |
| **W3** | Exhaustive / continuous (ongoing) | full coverage + re-scan for changes | Brutal completeness + continuous monitoring |

Every wave's findings flow through the per-finding pipeline (§5.1) into the graph, so the copilot always sees *interpreted* surface, not raw output. The loop is **bidirectional** in two ways: the operator **steers** where the deep waves spend effort ("go deep on host X"), and the operator **enriches** the shared model with hands-on findings fed back through the copilot. A confirmed operator fact (a credential, a new asset, a confirmed behavior) **re-activates exactly the recon steps blocked on that missing info** — those are already recorded as unmet preconditions (§5.7) and coverage-ledger gaps (§7.4), so re-activation is a query, not a new checklist — and any newly-opened surface is mapped by this same expansion loop, into the same graph. No separate parallel recon is spawned: enriching the one engine is precise, cheaper on the single GPU, and avoids a merge problem (Copilot Blueprint §7.9). Both channels keep the operator in control of the autonomous engine.

### 7.2 The handoff

- **Recon writes** engagement-scoped nodes — `target` / `service` / `finding` / `cve` — into the shared knowledge graph (schema: Copilot §6; the `scope` model and recon's full read/write contract: Knowledge-Architecture Blueprint §3, §7), and seeds the rolling-summary engagement state (Copilot §5.1).
- **The Copilot opens** by presenting the *prioritized* surface: "here is everything I found, here is what is interesting, where do you want to start?" — the triage output, made interactive.
- **The engagement (the session's main topic) is established by recon**, then driven by the human.
- **Streaming, not blocking.** The copilot becomes available after W0/W1; W2/W3 continue in the background, feeding new findings into the live session as they land.

### 7.3 The recon stack and workflow

**The stack** — recon's own components; the model *seats* are the shared stack (§4 / Copilot §4), referenced not redrawn:

```text
  +==============================================================+
  |  DOMAIN MODULES (pluggable, §4)                              |
  |    web · cloud · network/host · OS/AD · OSINT · apps · hw    |
  +===============================|==============================+
                                  |  model emits INTENT  (never a command)
  +===============================v==============================+
  |  CATEGORY WORKBENCHES (§4.1)                                 |
  |    intent -> pick installed tool -> resolve+gate host -> IP  |
  |    -> render command -> run (sandbox, timeout) -> parse      |
  +===============================|==============================+
                                  |  raw output
  +===============================v==============================+
  |  DETERMINISTIC PIPELINE (§5.1)                               |
  |    normalize -> filter (non-LLM) -> interpret -> correlate   |
  |    -> triage     (canonical host id · CVE-validated)         |
  +===============================|==============================+
                                  |  interpreted surface + candidates
  +===============================v==============================+
  |  SHARED KNOWLEDGE GRAPH   (+ engagement state)               |
  +===============================|==============================+
                                  |  handoff (§7.2)
                                  v
                PENTEST COPILOT  (human-driven)

  USES THE SHARED MODEL STACK  (Main Proposal §4 / Copilot §4):
    broker  Qwen3-4B ......... scopes the graph for reasoning
    analyst seat ............. interpret + correlate / triage
       real -> Foundation-Sec  ·  practice -> DeepSeek V4
    (offense seat = copilot-only; recon never exploits)
```

**The workflow** — waves → pipeline → graph → handoff:

```text
                   TARGET + SCOPE + MODE (White | Red)
                               |
  +=================================================================+
  |          PROGRESSIVE RECON WAVES   (general -> specific)         |
  |                                                                 |
  |   W0  PASSIVE      WHOIS / DNS / CT-logs / fingerprint  ~secs   |
  |   W1  FAST ACTIVE  nmap top-ports / httpx / resolve     ~mins   |
  |                                                                 |
  |   ----------  >> COPILOT ACTIVATES FROM HERE <<  ----------     |
  |                                                                 |
  |   W2  DEEP        full-nmap / ffuf / nuclei / params   bg/long  |
  |   W3  EXHAUSTIVE  full coverage + re-scan (monitor)    ongoing  |
  |                                                                 |
  |   W0/W1 = broad & fast      W2/W3 = deep, aimed at W0/W1 hits   |
  +================================|================================+
                                   |  raw output (each wave)
                                   v
                +-----------------------------------------+
                |           PER-FINDING PIPELINE          |
                |  normalize -> filter (non-LLM, CPU) ->  |
                |  interpret (analyst) -> correlate       |
                +--------------------|--------------------+
                                     v
                  ATTACK-SURFACE GRAPH  (+ engagement state)
                                     |
                                     v
                +-----------------------------------------+
                |           PENTEST COPILOT (you)         |<---------+
                |    reads graph . talks . works w/ you   |          |
                +--------------------|--------------------+          |
                                     |  "go deep on host X"          | steers
                                     +-------------------------------+
                                         directs W2 / W3 targeting

  SCOPE GATE  ::  every wave -> wave expansion is checked against scope
                  before it runs   (out-of-scope = hard stop)
  STREAMING   ::  W2/W3 findings flow into the live session as they land
```

### 7.4 Failure handling and resilience

Recon runs dozens of external tools across networks and models — failures are *expected*, not exceptional. Governing principle: **recon is best-effort and partial by nature, so a failure degrades *coverage*, it does not break the engine.** A scanner dying on one host must never stop recon on every other host, wave, or domain.

**Isolation.** Every recon task runs isolated — one task, no carryover (§5), inside the Docker sandbox (§8). A failed task is logged, marked, and the engine continues. One tool / one host / one wave failing is a local event, never a global one.

**Classify, then respond.**
- **Transient** (timeout, target rate-limit, network blip, model briefly OOM) → **retry** with bounded exponential backoff + jitter; mode-aware (Red retries fewer and slower to stay quiet). After the retry budget, give up gracefully.
- **Permanent** (tool missing, output format unparseable, auth absent) → **don't retry; fall back.** Each *capability* ("port scan", "subdomain discovery") maps to an ordered list of tools, so a primary failure tries the next (subfinder→amass, nmap→naabu). If none works, record a coverage gap. The job survives even when a specific tool does not.
- **Partial** (some output then died) → **salvage** what parsed, mark it incomplete.
- **Empty** (no output) → a valid result ("nothing here"), not a failure.

**Hard timeouts + circuit breakers.** Every tool call has a kill-on-timeout (scanners hang on filtered hosts; the sandbox makes them killable). A tool or target that fails repeatedly trips a circuit breaker — stop hammering it, which saves time and (in Red mode) avoids tripping defenses.

**Gaps are visible, never silent.** Like the noise filter's aggregate counts (§5.5), failures surface as an explicit **coverage ledger** — attempted / succeeded / failed / skipped — carried into the handoff (§7.2). The copilot reports gaps to the operator ("couldn't full-port-scan host X — nmap timed out 3×; retry, try masscan, or skip?"), so a missed scan becomes a *decision*, not a silent hole. A silent coverage gap is a missed attack surface masquerading as completeness — the worst outcome, so it is designed out.

**Crash resilience.** The task queue and findings live in durable storage (the graph + engagement state, Copilot §5.1/§13.4), and recon tasks are idempotent (re-running a scan is safe). If the engine itself crashes, it resumes — re-running pending and failed tasks — losing at most the single in-flight task, not the engagement. A partially-failed wave still hands the copilot whatever surface it *did* produce; the copilot activates on partial W0/W1 results with the gaps flagged.

**Scope-gate fails *closed* (the one inversion).** Everywhere else, failure means degrade-and-continue. For the scope check (§6) it means the opposite: if scope evaluation errors or is uncertain, the asset is treated as **out-of-scope and not scanned**. Never default-allow on a scope-check failure — it is the one failure that could cause real-world harm.

**Failure as signal.** A persistent pattern — a target rate-limiting or blocking aggressive scans — is information: in White mode it can prompt suggesting a switch to Red pacing; consistent blocks tell the operator the target has active defenses worth noting.

### 7.5 Critical-finding escalation (alert, never auto-act)

Most findings ride the normal stream and wait their turn in triage (§5). But a high-severity finding should not wait — an exposed `.env`, default admin credentials, an unauthenticated admin panel, or a confirmed CVSS ≥ 9 vulnerability should **immediately alert the operator**, jumping the queue ("⚠ exposed admin credentials on host X"). This is break-glass that interrupts the *human*, not the workflow: the engine never auto-acts on the finding (recon is recon-only, and exploitation is the operator's call in the Copilot) — it just surfaces the critical item now instead of an hour from now. Triggers are a CVSS threshold plus a small list of finding types (exposed credentials/secrets, sensitive files, unauthenticated admin surfaces).

To keep the alert channel meaningful, **non-critical notifications are batched** (grouped tool-doctor notes, coverage gaps, routine findings) so escalations stand out rather than drowning in a stream of low-priority pings.

### 7.6 Execution model: sprint-blocks and re-recon (a local Git-like history)

Recon's execution history is structured as a **local, Git-like commit DAG** — deliberately *not* a blockchain. A blockchain's defining machinery is consensus (proof-of-work, distributed agreement), which is pure overhead for a single writer on one box. Recon wants Git's model instead: an append-only, content-addressed, hash-linked DAG of immutable checkpoints with cheap branching — taking only the *tamper-evidence* slice of the blockchain idea (the hash-chain), not the consensus.

**The mapping:**
- **Sprint-block = a commit.** A self-contained sprint of recon work (executed tasks + results), immutable, identified by a content hash, referencing its parent's hash. The hash-chain makes the history **tamper-evident** — a defensible engagement record that strengthens the audit trail (Copilot §11).
- **The block chain = the commit DAG.** Blocks link in time, but because recon **branches** (an exploratory lead, a divergent strategy), the structure is a **DAG, not a line** — exactly why Git fits and a blockchain (single canonical chain, no branching) does not.
- **The live graph = the working tree.** The attack-surface graph is the *current materialized state*, obtained by replaying the block history. Blocks are the log; the graph is the view.
- **Two granularities, both kept.** *Within* a block, tasks form a dependency **DAG** (what needs what — §5.1). The **blocks** chain as temporal checkpoints (what ran when, where to re-run from). Task-DAG = dependency structure; block-chain = provenance/checkpoint spine.

**Re-recon = a forward step with a backward reference (never a revert).** Because the graph is a *living, shared model* that operator enrichment also writes to (§7.9), "go back to a failed block" must **not** revert the graph — that would destroy facts confirmed in later blocks (a credential, say). Instead:
- **The filter locates the target.** Failed/blocked tasks are already tagged with their block and recorded as coverage-ledger gaps (§7.4) and unmet preconditions (§5.7). Querying those *is* the index into the chain — "which block's tasks were blocked on this missing info?"
- **Re-execution anchors and re-runs forward.** It re-runs the failed tasks of that block — safe because recon tasks are **idempotent** (§7.4), so results refresh *forward* into the living graph; the graph never moves backward.
- **The re-run is a new block referencing the failed one** — "sprint 7 re-ran the blocked parts of sprint 3 after credential X arrived." That reference is the provenance of *why* recon re-ran; the enrichment loop (§7.9 of the Copilot) is *when*.

**The Git-worktree image — and its limit.** A re-run or exploratory branch is best pictured as a **Git worktree**: a working state over the *same shared object database*, not a clone — which reinforces the one-shared-model rule (a re-run shares the one history; it is never a separate parallel recon, §7.9). The refinement: worktrees are about multiple simultaneous *checkouts*, and the common re-run needs no isolation (idempotent forward re-runs suffice, HEAD simply advances). The worktree is the right picture for the *optional* case where a re-run or exploratory branch executes in its own working state and then merges its fresh findings forward — the anti-clone, sharing one history. The backbone is the commit-DAG + branching; the worktree is one feature layered on it.

**Deliberately excluded (the local-only slice).** No consensus / proof-of-work (single writer). No distributed collaboration — no remotes, push/pull, or cross-clone merge-conflict resolution. This is a *local* Git-like history: the DAG, content-addressing, hash-chaining for tamper-evidence, and branching — nothing from the distributed layer.

---

## 8. Runtime and Hardware

- **Hermes fit.** Recon runs as a Hermes subagent / opening phase — which matches Hermes's subagent model (isolated context, results fed to the main agent) — populating the graph and engagement state before the main copilot loop takes over. Long recon runs asynchronously (Hermes cron/subagent).
- **Hardware (RTX 3060 12GB / Ryzen 7 7700 / 32GB / Pop!_OS).** All scanners run inside the Docker sandbox (Copilot §13.2), never on the host — and on CPU / network, **not the GPU**. The local models (broker, analyst, offense) load **one at a time** on the GPU; on real work the analyst reasoner is local, on practice it is the cloud teacher (Copilot §4). GPU tenancy is scheduled by the arbiter (§8.1).

### 8.1 Resource sharing on one box — the HardwareArbiter

The contention the earlier all-*resident* plan carried — multiple models pinned in VRAM while background scans run — is designed out by **loading one local model at a time** and keeping **scanners GPU-free**. The local models (broker `Qwen3-4B`; the analyst seat `Foundation-Sec-8B` on real work; the offense model `DeepHat-7B` when you build an artifact) share the card by *taking turns*, never co-residing; the scanners (nmap, masscan, nuclei, ffuf) are CPU / network / disk bound and **never touch the GPU**. On practice the analyst reasoner is the cloud teacher (off-box, no GPU cost), leaving even more headroom. So the HardwareArbiter's job is scheduling turns, not refereeing a fight.

It now does two light things:

- **Single-tenant GPU scheduler (the main job).** Only one local model is resident at a time. The arbiter wakes the **broker** (Qwen3) to scope the graph, the **analyst** (Foundation-Sec on real work) to interpret/reason a **batch** of findings, or the **offense** model when the operator needs an artifact — each kept warm through its burst (Ollama keep-alive) and unloaded after an idle window. Peak GPU model use is one ~5GB model against 12GB — no swap-storm, because loads are **batched with hysteresis**, not per-finding. A priority queue lets an operator-driven offense request or a critical-finding interpretation (§7.5) jump ahead of routine batch work. **Scanners run in parallel throughout — they never queue for the GPU.**
- **Light RAM/CPU coordination.** The one place tools and a local model still meet is system RAM (32GB): a large scan burst's output buffers, plus a loaded model, plus the graph. The arbiter avoids launching a big interpretation batch at the exact moment a memory-heavy scan peaks — and the streaming + non-LLM filter (normalize-then-drop-raw, noise→counts, §5.5) keeps tool-output RAM bounded, so this rarely bites.

Still **cooperative, never preemptive**: a running scan is never killed (that breaks TCP / scan state), in-flight inference is never interrupted, and a watchdog force-releases a hung model to prevent deadlock.

Net: because only one local model is resident at a time and scanners never use the GPU (and on practice the reasoner is off-box entirely), the 3060 comfortably runs continuous recon *plus* on-demand local inference — the arbiter schedules turns rather than refereeing a thrash.

### 8.2 Long-haul operation — the recon-side endurance mechanisms

Recon runs *continuously*, so it carries most of the marathon-hardening load (Main Proposal §4.2 is the program spine; this is the recon detail). The rule: **bounded steady state + supervised, self-healing components.**

**The Custodian — steady-state resource governance.** A low-priority background task that caps every resource recon grows:

- **Hot / warm / cold graph tiering (the linchpin).** The engagement graph is not queried whole. Only the **hot set** — in-scope assets, live/conditional exploit candidates, unmet preconditions, recent findings, anything the copilot is actively reasoning over — stays in the fast query path. **Warm** = settled but potentially relevant (mapped, no open candidates); **cold** = out-of-scope, superseded, or aged-out subgraphs, compacted to archive tables (recoverable, not deleted). Recon's correlation, the copilot's retrieval/RAG, and live feasibility re-derivation touch **only the hot set**, so query latency is a function of *active working-set size*, not total accumulated volume — flat at hour 30 as at hour 1. Promotion/demotion is event-driven and the policy is **tested and tunable, not vibes** — because this rule alone keeps latency flat, it gets scope-gate-level rigor. A subgraph is **`settled`** (eligible to demote to warm/cold) when *all* hold: no new finding or candidate-state change within it for a dwell time `T_settle`; it has **no open (ready/conditional) exploit candidates**; and it is **out of the active scope focus**. Demotion is reversible: a subgraph is **promoted back to hot** the moment enrichment, a new finding, or the operator references it. Too-eager demotion causes promotion thrash (facts the enrichment loop still needs get evicted); too-lazy lets the hot set grow and breaks the flat-latency promise — so `T_settle` and the working-set cap are measured and adjusted like any other tuned threshold.
- **Sprint-DAG snapshot + compaction.** Periodically checkpoint the materialized graph state and archive the sprint-blocks behind it, preserving the hash-chain across the snapshot boundary (Git `gc`/`repack` over §7.6). The recent chain stays live for re-recon; deep history compacts to archive.
- **Audit/log rotation, evidence-blob GC, heap watermark.** The audit log rotates (append-only but size-capped, older segments archived); evidence blobs keep their content-hash live but expire bulky raw payloads on an age/size policy (provenance survives, storage doesn't balloon); and a **backend heap watermark** flags creep, triggering a Supervisor component reset before OOM.

**The Supervisor — assume-failure self-healing.** Every long-running part — the recon orchestrator, each scanner subprocess, the local model runner, the store, the cloud client — is a *supervised component* with a health probe and a restart-from-persisted-state policy. If one hangs or leaks, the Supervisor restarts **that component** from SQLite + the sprint-DAG head without tearing down the engagement. Inside it, the **process janitor** handles the classic long-run subprocess rot:

- **Hard per-tool timeouts** — every scanner has a wall-clock cap; overrun is killed and recorded as a partial/failed task (§7.4), never left hanging.
- **Mandatory child-reaping** — spawned processes are reaped on exit; no zombie accumulation over 24h.
- **FD / process budget with backpressure** — a ceiling on concurrent tool processes and open descriptors; when near it, recon **queues** new scans instead of spawning into exhaustion (so "recon goes quiet" from FD starvation cannot happen — it slows and drains instead).

**Checkpoint / resume (recon side).** On a cadence and at safe points (sprint-block boundaries), the Custodian writes a compact recovery point: the graph snapshot, in-flight sprint status, the coverage ledger, and scope/mode. Resume reloads it and **re-runs the incomplete idempotent sprints** — which §7.6 already makes safe (idempotent tasks refresh forward; the graph never rolls back). **Pause** is a checkpoint plus a graceful quiesce (let running scans finish or checkpoint their partial state, then stop spawning); **resume** reloads and re-attaches. This is what lets one engagement span several marathons. (The operator-facing pause/handoff UX is TUI §5.9.)

**Steady-state data hygiene (recon-owned parts):**

- **WAL + single-writer queue + checkpointing.** All SQLite-family writes (findings, enrichment write-backs, audit, engagement state) go through one write queue in WAL mode, with the Custodian driving periodic WAL checkpoints — ending "database is locked" and unbounded WAL growth under sustained concurrent writes.
- **Reconciliation pass — mode- and cost-gated (it must not fight stealth or saturation).** Two tiers, because *re-verifying* a fact means *re-scanning*, which collides with both the saturation backoff (whose whole job is to stop redundant scanning) and Red-stealth mode (where re-probing is exactly the noise being avoided):
  - **Passive aging — always on.** Age facts by timestamp and mark ones past a staleness horizon `superseded_by` (Copilot §6). No traffic; safe in any mode.
  - **Active re-verification — loud mode only, rate-limited, and *suppressed* while saturation-backoff or stealth is engaged.** Only when the engagement is in loud White mode and not backed-off does reconciliation actually re-probe ("is this service still up / this credential still valid?"), and even then under a rate cap. In stealth or backoff, high-value facts are *flagged as possibly-stale* for the operator rather than silently re-scanned.
- **Fact precedence — who wins when writers disagree.** Over a marathon the graph is written by three sources; without an authority order a long run silently lets one invalidate another. The order is **operator-confirmed > tool-observed > model-asserted**. Reconciliation **flags, it does not override** a higher-authority fact: if active re-verification finds an operator-confirmed credential now failing, it raises a *contradiction for the operator*, it does not delete the operator's fact. The Custodian's tiering/compaction never changes fact *content*, only *location*. And because live feasibility re-derivation (Copilot §6) reads a fact set that other writers are concurrently updating, it reads from a **transactional snapshot** — a consistent read — so a busy 24h session can't produce candidate feasibility computed over a half-written graph.
- **Adaptive noise-filter recalibration.** The §5.5 autoencoder threshold is recalibrated on a **rolling window** rather than measured-once-then-fixed, so as the target's response distribution shifts over a long run the filter neither starts dropping real findings nor lets noise flood.

**Saturation & backpressure (recon-owned):**

- **Saturation state.** When W3 (exhaustive continuous) stops yielding new findings over a window, recon **backs off** from redundant re-scanning to a low-frequency **monitoring cadence** (periodic light re-checks for target *change*), ramping back to active only on an enrichment fact, a scope change, or a detected change. This ends the "20 hours pinning the GPU to regenerate the same findings" failure — idle recon should *watch*, not *churn*.
- **Re-recon trigger coalescing.** Enrichment and change-detection can fire re-recon sprints faster than they complete; overlapping/duplicate triggers are debounced and merged so an active operator can't build an unbounded backlog.
- **VRAM-swap hygiene.** Between on-demand model swaps (§8.1), explicit VRAM cleanup plus a periodic CUDA-context health check; a fragmented or bad context triggers a clean model-runner reset (via the Supervisor) rather than accumulating failures over hundreds of swaps.

Together these take Tier-1 accumulation/subprocess/resume and Tier-2 store/stale/filter issues to near-none, and drive the recon-side Tier-3 (saturation, swap hygiene) low. What they can't do: lower the reasoner's hallucination *rate* (contained on the copilot side by the write-back gate, Copilot §4.4) or make a consumer GPU immune to sustained thermal load (pacing, TUI §5.9).

---

## 9. Output Schema (the contract)

The Engine emits one artifact: the **attack-surface map**, typed to flow straight into the Copilot graph. Every asset carries:

- **Identity:** type (domain / IP / host / service / endpoint / cloud-resource / app), value, parent/source.
- **Detail:** technology + versions, observed behavior, mapped CVEs/CWEs.
- **Exposure:** reachability, ports/protocols, auth observed.
- **Vulnerabilities:** potential/detected vulns (CVE/CWE), each with evidence and confidence (inferred or detected, not confirmed).
- **Defenses:** the defensive surface — WAF identity/behavior, rate-limiting, filtering, security controls observed (§5.7); these act as precondition-modifiers.
- **Exploit candidates:** per vuln — availability (available/theoretical), preconditions, condition status (met/unmet/blocked-by-defense), and feasibility (ready/conditional/blocked) (§5.7).
- **Provenance:** which module/tool found it, when, and the raw evidence reference (for §13.2 untrusted-content handling and trust metadata).
- **Scope status:** in-scope / out-of-scope (gated), and the **mode it was discovered under** (White/Red).

This is a provider-agnostic, typed boundary — the same discipline as the Copilot's MCP contracts — so the Engine is swappable and independently testable.

---

## 10. Build Sequencing

1. **P0 — Core loop + one module + White mode.** Orchestrator, the scope-gated expansion loop (§6), the common schema (§9), and one domain module (Web, wrapping existing tools), loud.
2. **P1 — Breadth.** Add Cloud, Network/host, and OSINT modules.
3. **P2 — Intelligence layer.** Cross-domain correlation and triage/prioritization (§5).
4. **P3 — The handoff.** Seed the Copilot's engagement state and graph; the streaming/continuous-monitoring model (§7).
5. **P4 — Red-stealth.** Add the stealth policy layer over the working White system (§3).
6. **P5 — Remaining domains.** Apps (mobile/binary), OS/AD, then hardware/IoT/RF as appetite allows.

---

## 11. Realistic Limits

- **Recon finds the surface, not the bugs.** The Engine maps; the human (with the Copilot) exploits. It is a force-multiplier for coverage, not a vulnerability oracle.
- **Bounded by tool quality.** It is only as good as the scanners it wraps; it inherits their false positives and blind spots.
- **Stealth is imperfect.** Red mode reduces detectability, never guarantees it.
- **All-domain breadth is aspirational.** Build the high-value domains first (web, cloud, network, OSINT); exotic domains (hardware/RF) are later-or-never, not day-one.
- **Scope discipline is the whole game.** The expansion loop is powerful precisely because it is automatic, which is exactly why a single scope-gating bug is the worst failure mode in the system. Treat §6 as the part to get right before anything else.
