# Saltpilot — TUI Blueprint

**Version:** 1.4
**Status:** Design baseline
**v1.4:** transport decision — the TUI is an **ACP (Agent Client Protocol) client** driving `hermes acp` (§1, §2), resolving the Main Proposal's open question about a custom frontend attaching to Hermes. ACP chosen over the internal `tui_gateway` JSON-RPC for stability (documented standard); `tui_gateway` kept as a per-gap fallback. Verified against Hermes's docs (v0.14+); pin a version and confirm the ACP event surface at build time.
**v1.3:** model-name sync — status headers now show the current local stack (Qwen broker · Foundation-Sec · DeepHat) instead of the old WhiteRabbitNeo/V4 mix; matches Copilot §4 (broker-fronted stack).
**v1.2 adds:** the long-haul UX (§5.9) — digests over firehose with widening alert batching, "since you were away" summaries, `/pause`+`/resume` for multi-session marathons, `/handoff`, bounded scrollback, and a load/thermal/health indicator — plus the commands in §6.5. Native marathon support (Main Proposal §4.2).
**v1.1 adds:** the recon↔copilot communication made visible — exploit-candidates-with-conditions (feasibility ●/◐/○) and defenses in the focus views (§5.3), the enrichment screen showing a hands-on finding confirmed and folded in with candidates flipping and re-recon firing (§5.8), the `/found` enrichment command distinct from `send to copilot` (§6.5), and enrichment in the state-transition map (§7).
**Part of:** Saltpilot. The **Main Proposal** is the source of truth for the program, its integration, and shared infrastructure. This blueprint owns the **frontend**: the TUI's tech stack, screens, interactions, and keybindings. The backend it drives is **Hermes** (via ACP — Main Proposal §2), which runs the Copilot and Auto-Recon logic detailed in their blueprints.

---

## 1. Role and Boundary

The TUI is Saltpilot's face — and only its face. It is **one client on Hermes's session plane**, driving the agent through the **Agent Client Protocol (ACP)**: `hermes acp` runs Hermes as an ACP server, and the TUI is an ACP client. It renders state and sends intent; it contains no security logic, no model calls, and no scope decisions. Everything that matters — the agent loop, model inference, recon orchestration, scope enforcement — lives behind ACP in Hermes and the MCP tools it calls, so the TUI can crash, restart, or be swapped without risk to an engagement.

This resolves the Main Proposal's open question (§2 / §10): a custom local frontend attaching to Hermes is a **first-class, documented pattern**, not a hope. The same session plane already serves Hermes's own CLI/TUI and its ~20 messaging gateways; the Saltpilot TUI is one more client — so the backend stays scriptable and Hermes-drivable without the UI (Main Proposal §5.1), and the UI stays free to be fast and disposable.

---

## 2. Tech Stack

- **Language / framework — Rust + Ratatui.** Chosen for smooth, high-frequency redraws of a dense, live-updating dashboard — the case where a Python TUI (Textual) shows its overhead. Reuses existing Saltnitor (Ratatui) experience.
- **Terminal backend — crossterm** (cross-platform; raw mode, events, resize).
- **Async runtime — tokio.** The TUI multiplexes three event sources: keyboard/mouse input, a render tick, and a stream of backend events (findings, wave progress, alerts). An async select-loop keeps input responsive while recon streams.
- **Transport — ACP (Agent Client Protocol).** The TUI speaks **ACP** to `hermes acp` (Main Proposal §2). ACP is a documented standard (Zed's editor↔agent protocol), so it is a stable contract that survives Hermes upgrades — chosen over Hermes's *internal* `tui_gateway` JSON-RPC, which is undocumented and free to change per release. Two directions:
  - **Commands up** (TUI → Hermes): `start_engagement`, `set_scope`, `set_mode`, `focus_category`, `deep <asset>`, `send_to_copilot <ref>`, `chat <text>`, `report`.
  - **Events down** (Hermes → TUI): `finding`, `wave_progress`, `coverage_update`, `critical_alert`, `copilot_token` (streaming chat), `tool_doctor_report`, `arbiter_state`.
  Saltpilot-specific cockpit events ride over ACP as structured payloads. **Caveat to confirm at build time:** ACP is editor-oriented, so pin a Hermes version and verify (`hermes acp --help`) that it carries these cockpit events plus the streaming and handoff signals; anything ACP can't express falls back to the internal `tui_gateway` JSON-RPC or a side MCP channel — ACP for the main drive, `tui_gateway` only for a specific gap, never wholesale.
- **State model — local view-state only.** The TUI keeps a lightweight projection of engagement state for rendering (the surface tree, wave status, alert list, chat scrollback). The backend remains the source of truth; the TUI reconciles on each event and can request a full snapshot on reconnect.
- **Alternative considered — Go + Bubble Tea.** Viable and faster to build; rejected only because Rust/Ratatui gives a hair more performance and reuses existing skill. Recorded so the trade-off is explicit.

---

## 3. Design Principles

1. **Two panes embody the two features.** Left = **Copilot** (depth, human-driven). Right = **Auto-Recon** (breadth, autonomous, streaming). The seam between features is a keystroke (`→ send to copilot`).
2. **Left pane feels like Claude Code CLI.** Clean streaming responses, tool/command results inline and collapsible, minimal chrome, keyboard-first, the conversation as the focus.
3. **Right pane is overview + focus (depth, not density).** A labeled at-a-glance map by default; drill into a category or asset for full, **category-specific** detail. Minimize for scanning, expand for using.
4. **Command + chat mix.** One input bar: prose goes to the Copilot, `/commands` drive the engine. Most actions have both a command and a keybinding.
5. **Visible, never silent.** Suppressed noise shows as counts, failures as a coverage ledger, critical findings as interrupts — never hidden (a program-wide principle, surfaced in the UI).

---

## 4. Layout

```text
┌─ status header ───────────────────────────────────────────────────────────┐
│  COPILOT  (left, ~60%)              │  RECON · LIVE  (right, ~40%)          │
│  Claude-Code-feel chat              │  overview by default / focus on drill │
│                                     │                                       │
├─────────────────────────────────────┴───────────────────────────────────────┤
│  input bar: prose → Copilot   |   /commands → engine            [mode][live] │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **Status header** — program name, mode (White/Red), scope, loaded models, live indicator.
- **Left pane** — Copilot conversation + inline command/tool results.
- **Right pane** — recon overview (default) or a focused category/asset (expands).
- **Input bar** — single line; prose or `/command`; shows current mode and recon-live state.

---

## 5. Screens (per function)

### 5.1 Engagement start (scope + mode)

The first screen. Recon does **not** run until scope is set — scope fails closed (Main Proposal §2). Mode defaults to White.

```text
┌─ Saltpilot · NEW ENGAGEMENT ─────────────────────────────────────────────┐
│                                                                           │
│   target      ┃ acme.com                                                  │
│   scope       ┃ *.acme.com, 203.0.113.0/24                                │
│   out-of-scope┃ blog.acme.com                                             │
│   mode        ┃ ( • ) White-pentest   ( ) Red-stealth                     │
│                                                                           │
│   [ Tab ] move field   [ Space ] toggle mode   [ Enter ] run preflight    │
└───────────────────────────────────────────────────────────────────────────┘
```

`Enter` runs the **tool-doctor preflight** (Auto-Recon Blueprint §4.1) before recon starts:

```text
┌─ Saltpilot · PREFLIGHT ───────────────────────────────────────────────────┐
│  ✓ nmap 7.94     ✓ httpx 1.6     ✓ subfinder 2.6     ✓ nuclei 3.x         │
│  ✗ ffuf          not found  →  go install …/ffuf/v2@latest   [ i: install ]│
│  ⚠ amass 3.x     v4 recommended → …                          [ u: upgrade ]│
│                                                                           │
│  18 ready · 1 missing · 1 outdated      [ Enter ] start anyway   [ a: all ]│
└───────────────────────────────────────────────────────────────────────────┘
```

- `i` / `u` print the exact remediation (tell-by-default); `a` applies all fixes **only if** auto-remediation is enabled (opt-in). `Enter` starts recon with fallbacks covering the gaps.

### 5.2 Main split — overview (the default working screen)

```text
┌─ Saltpilot ─────────────────[ White │ scope *.acme.com │ models Qwen·FSec·DHat ]─┐
│ COPILOT                            │ RECON · LIVE                                │
│                                    │ ENGAGEMENT                                  │
│ you ▸ most promising surface?      │   mode   White-pentest   target acme.com    │
│                                    │   wave   W1 fast-active ▸  ●●●○  62%        │
│ saltpilot ▸ top targets:           │   coverage  ok 31 · fail 2 · skip 4  [/cov] │
│  1 admin.acme.com — exposed .git   │ ───────────────────────────────────────    │
│  2 api.acme.com — swagger open     │ ⚠ CRITICAL ALERTS (2)                       │
│  3 dev.acme.com — Jenkins 2.x      │   exposed admin creds @ admin.acme.com      │
│                                    │   public S3 bucket    acme-backups          │
│ you ▸ /focus web                   │ ───────────────────────────────────────    │
│                                    │ SURFACE BY CATEGORY         [/focus <cat>]  │
│ saltpilot ▸ focusing web surface → │   ▸ Web      14 hosts · 6 findings  ◆        │
│                                    │     Cloud     3 assets · 2 findings  ◆       │
│                                    │     Network  22 hosts · 39 services          │
│                                    │     AD        1 domain · 1 finding  ◆        │
│                                    │     OSINT    31 subdomains · 4 leaks  ◆      │
├────────────────────────────────────┴───────────────────────────────────────────────┤
│ › ask… or  /focus <cat> /deep <host> /findings /scope /mode red /report  [White][⏵]│
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Labeled regions: **ENGAGEMENT** (status), **CRITICAL ALERTS** (escalations), **SURFACE BY CATEGORY** (every domain, its size, and ◆ where the interesting findings are).

### 5.3 Focus — Web (category-specific fields)

`/focus web` (or select the row + `Enter`) expands the recon view to give columns room:

```text
┌─ Saltpilot · RECON ▸ WEB ──────────────────[ 14 hosts · 6 findings · esc back ]─┐
│ HOST                TECH / SERVER       STATUS  NOTES                             │
│ ⚠ admin.acme.com    nginx · PHP 7.4     200     exposed .git · login form         │
│ ◆ api.acme.com      nginx · Node 18     200     /v2 swagger open · JWT            │
│   dev.acme.com      Jenkins 2.x         403     login · CVE-2024-xxxx?            │
│ ─────────────────────────────────────────────────────────────────────────────   │
│ ▸ admin.acme.com                                                                  │
│   endpoints   /admin  /login  /.git/HEAD  /api/v1/users                          │
│   params      ?id= (admin)   ?redirect= (login)                                  │
│   defenses    Cloudflare WAF · no rate-limit on /login                           │
│   candidates  ● ready        exposed .git → source disclosure                    │
│               ◐ conditional  IDOR /api/v1/users — needs: valid session           │
│               ○ blocked      SQLi /search — blocked by WAF → needs bypass         │
│   next        dump .git → source review · get a session to test IDOR            │
│   actions     [d /deep] [s → send to copilot] [c copy] [n note]                  │
└───────────────────────────────────────────────────────────────────────────────────┘
```

The **candidates** block is recon's §5.7 output made visible — feasibility (`● ready · ◐ conditional · ○ blocked`) with the *condition* spelled out (what a conditional one needs, what a blocked one is blocked by). This is the line that changes when you enrich: supply the missing session and the `◐ conditional` IDOR flips to `● ready` (§5.8).

### 5.4 Focus — AD (entirely different fields)

`/focus ad` — same panel, domain-appropriate fields, proving the category-awareness:

```text
┌─ Saltpilot · RECON ▸ AD ───────────────────[ corp.acme.local · esc back ]───────┐
│ DOMAIN  corp.acme.local     users 412 · groups 38 · computers 96                 │
│ ─────────────────────────────────────────────────────────────────────────────  │
│ ⚠ KERBEROASTABLE (3)        svc_sql · svc_backup · svc_web                        │
│ ⚠ AS-REP ROASTABLE (1)      j.doe                                                 │
│ ◆ ACL PATHS                 Helpdesk → GenericAll → Domain Admins                 │
│   SHARES                    \\fs01\backups (read) · \\fs01\hr$ (denied)           │
│   TRUSTS                    corp.acme.local ↔ legacy.acme.local                   │
│ ─────────────────────────────────────────────────────────────────────────────  │
│ ▸ svc_sql  (kerberoastable)                                                      │
│   spn        MSSQLSvc/sql01.corp.acme.local:1433                                 │
│   member of  Domain Users · SQL Admins                                           │
│   next       roast → offline crack → SQL Admins                                  │
│   actions    [d /deep]  [n /note]  [s → send to copilot]                         │
└──────────────────────────────────────────────────────────────────────────────────┘
```

**Per-category fields** (what each focus view renders):
- **Web** — host, tech/server, status; asset: endpoints, params, findings, tech, next.
- **Network** — IP, open ports, services + versions, OS, CVEs.
- **Cloud** — resource type, public/exposure, service, IAM/misconfig.
- **AD/OS** — kerberoastable / AS-REP accounts, ACL paths, shares, trusts, SPNs.
- **Apps** — endpoints/secrets found, permissions, vulnerable dependencies.
- **OSINT** — subdomains, emails, leaked credentials, exposed repos.

### 5.5 Critical-finding alert

A high-severity finding (exposed creds, CVSS ≥ 9) **interrupts** rather than waiting in the stream (Main Proposal §3.3): the ALERTS region flashes, a bell rings (optional), and a toast appears over the right pane. It never auto-acts.

```text
│                                    │ ╔═══════════════════════════════════════╗ │
│                                    │ ║ ⚠ CRITICAL — exposed admin creds       ║ │
│                                    │ ║   admin.acme.com  /.git/config         ║ │
│                                    │ ║   [ Enter focus ] [ s → copilot ] [esc]║ │
│                                    │ ╚═══════════════════════════════════════╝ │
```

Non-critical notifications (tool-doctor notes, coverage gaps) are **batched** into a quiet area so the alert channel stays meaningful.

### 5.6 Coverage ledger (`/cov`)

The full picture of what recon did, didn't, and couldn't — the visible-gaps principle made browsable.

```text
┌─ Saltpilot · COVERAGE ─────────────────────────────────[ esc back ]───────┐
│  ok 31 · fail 2 · skip 4                                                   │
│  ✓ web/httpx · web/ffuf · net/nmap-top · osint/subfinder · …              │
│  ✗ web/nuclei  admin.acme.com  timeout ×3 → fell back to manual  [retry]  │
│  ✗ net/nmap-full 203.0.113.7  host unreachable                  [retry]  │
│  ⤿ cloud/prowler  skipped — no creds (passive only)                       │
└───────────────────────────────────────────────────────────────────────────┘
```

### 5.7 Report (`/report`)

Generates the engagement report from the graph + audit trail; preview in-pane, then export.

```text
┌─ Saltpilot · REPORT ───────────────────────────────────[ e: export md/pdf ]─┐
│  Engagement acme.com · White-pentest · 2026-…                               │
│  Surface: 14 web · 22 net · 3 cloud · 1 AD · 31 subdomains                  │
│  Findings: 2 critical · 4 high · 9 medium …                                 │
│  [ preview scrolls here ]                                                    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.8 Enrichment — a hands-on finding, confirmed and folded in (recon ↔ copilot)

This is the screen that shows the two features **talking to each other**. You've been testing by hand and cracked a credential recon couldn't have. You submit it; the **left pane (Copilot)** confirms it and the **right pane (Recon)** updates the shared model live — the fact lands, blocked candidates flip, re-recon fires, the path opens. Left is the confirm *conversation*; right is the shared graph *reacting*. (Architecture: Main Proposal §3.3 enrichment channel; Copilot §7.9; Auto-Recon §7.6 re-recon.)

```text
┌─ Saltpilot ─────────────────[ White │ scope *.acme.com │ models Qwen·FSec·DHat ]─┐
│ COPILOT                            │ RECON · LIVE                                │
│ you ▸ /found cred svc_admin:•••    │ ENGAGEMENT                                  │
│       @ admin.acme.com             │   wave  W2 deep ▸ + re-recon   ●●●◐         │
│                                    │ ─────────────────────────────────────────  │
│ saltpilot ▸ confirming…            │ ENRICHMENT  ← operator finding              │
│  reason: matches the login form    │   + credential  svc_admin @ admin.acme.com  │
│   recon saw; name fits the pattern │     confirmed ✓  (session verified)         │
│  check: authenticated → 200 ✓      │     satisfies →  "valid session"            │
│  confirmed — writing to graph.     │ ─────────────────────────────────────────  │
│                                    │ PATHS UPDATED  (re-derived)                 │
│ saltpilot ▸ that unblocked 2:      │   IDOR /api/v1/users    ○ blocked → ● ready │
│  • IDOR /api/v1/users → now READY  │   auth'd content disc.  skipped → running…  │
│  • re-running auth'd content disc. │     ↳ new: /admin/export  /admin/users      │
│  new chain:                        │ ─────────────────────────────────────────  │
│    creds → IDOR → user PII dump    │ SURFACE BY CATEGORY                         │
│                                    │   ▸ Web    14 hosts · 7 findings  ◆ (+1)    │
│ you ▸ show me the chain            │     AD      1 domain · 1 finding            │
├────────────────────────────────────┴───────────────────────────────────────────────┤
│ › /found <fact>  ·  ask…  ·  /focus web  /deep <host>  /report        [White][⏵]  │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

Reading it as a conversation between the two panes: you `/found` a credential → the Copilot **reasons** then **actively verifies** it (the "both" confirmation) → on success it **writes to the shared graph**, where the credential appears with a `satisfies → "valid session"` link → that satisfied precondition **re-derives feasibility**, so the IDOR candidate flips `○ blocked → ● ready` → the previously-skipped authenticated content discovery **re-runs** (a re-recon sprint) and surfaces new endpoints → the surface count ticks up and a **new attack chain** becomes available. Everything on the right moved because of one fact on the left. Steering (`/deep`) aims the scanners; enrichment (`/found`) feeds the model — this screen is the second one.

### 5.9 Long-haul UX — digests, pause, and shift-handoff

A marathon (and a job spanning several) wears the operator as much as the machine, so the TUI's long-run job is to protect *attention*: surface what changed, never a firehose, and make stopping and resuming clean (Main Proposal §4.2; backend mechanisms in Auto-Recon §8.2 / Copilot §4.4).

- **Digests over firehose.** On a cadence (and on demand via `/digest`), a rollup rather than a running stream: *what changed, what's newly actionable, what needs your decision* since the last digest. Alert batching **widens** as the run lengthens — early on you see more; hours in, only the batched digest and true criticals — so a 24h run doesn't become either a wall of noise or alert-fatigue.
- **"Since you were away."** After a pause, a lock, or a new session, the first thing shown is a summary of what the autonomous side did while you were gone (findings, completed re-recon sprints, candidates that flipped) — so you re-enter with context, not a cold panel.
- **Pause / resume.** `/pause` checkpoints and gracefully quiesces (running scans finish or checkpoint partial state; the cloud session detaches); `/resume` reloads the checkpoint and re-attaches. The header shows a **paused** state. This is the UI over the backend checkpoint/resume — it's what makes "2–3 marathons per job" feel like one continuous engagement.
- **Shift-handoff.** `/handoff` emits a human-readable summary — current state, open threads, candidates in play, suggested next steps — for a later session (or another operator) to pick up cold.
- **Bounded scrollback.** The chat and recon panes cap retained scrollback (older lines page to the transcript on disk, not RAM), so neither the TUI nor the box bloats over a 24h session; full history stays retrievable, just not resident.
- **Sustainable pace, surfaced.** The header shows a **load/thermal** indicator; when the backend caps sustained GPU/CPU to protect a consumer box (Auto-Recon §8.2 pacing), the TUI shows recon is in a paced/monitoring state rather than looking stalled.

```text
┌─ Saltpilot · DIGEST ─────────────[ 14:32 → 18:00 · 3h28m · /handoff /pause ]─┐
│  SINCE 14:32                                                                 │
│  changed      +6 endpoints · 2 services dropped (reconciled) · +1 subdomain  │
│  newly actionable  ● IDOR /api/v1/users ready · ◐ SSRF api.acme.com (needs…) │
│  needs you    2 candidates blocked on a WAF bypass — your call               │
│  recon        saturated on web → monitoring; deep AD sprint running          │
│  reasoner     cloud (V4) · 1 brief fallback at 16:10, recovered              │
│  health       graph hot-set 1.2k nodes (stable) · GPU paced 78% · mem ok     │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Interactions — what happens when you press what

### 6.1 Global keys

| Key | Action |
|---|---|
| `Tab` / `Shift-Tab` | Move focus between panes (chat ↔ recon) |
| `Ctrl-K` | Command palette (fuzzy over all `/commands`) |
| `?` | Help / keybinding cheatsheet overlay |
| `Esc` | Back up one level (asset → category → overview); close overlay |
| `Ctrl-C` | Quit (confirm if recon is running) |
| `PgUp`/`PgDn` | Scroll the focused pane |

### 6.2 Input bar

- Type **prose** + `Enter` → sent to the Copilot (left pane streams the reply, Claude-Code style).
- Type **`/command`** + `Enter` → routed to the engine; result renders inline (left) or updates the panel (right).
- `↑`/`↓` at an empty bar → command/prompt history.
- `Tab` mid-`/command` → autocomplete.

### 6.3 Recon panel — navigation

| Context | Key | Action |
|---|---|---|
| Overview | `j`/`k` or `↑`/`↓` | Move between categories |
| Overview | `Enter` | Focus the selected category (expands) |
| Focus (list) | `j`/`k` | Move between assets |
| Focus (list) | `Enter` | Open asset detail (the learning-doc view) |
| Focus | `Esc` | Collapse back to overview |

### 6.4 Asset actions (in a focused asset)

| Key | Command | Result |
|---|---|---|
| `d` | `/deep <asset>` | Retarget deep recon (W2/W3) at this asset; **bidirectional steering** — the engine concentrates here |
| `s` | `→ send to copilot` | Push the asset + its findings into the Copilot conversation (the breadth→depth handoff, one keystroke) |
| `c` | copy | Copy the asset's primary value (URL/host) to clipboard |
| `n` | `/note` | Attach an operator note (persisted to the graph) |

### 6.5 Commands (engine)

| Command | Effect |
|---|---|
| `/focus <cat>` | Focus a recon category (web/cloud/net/ad/apps/osint) |
| `/deep <host>` | Aim deep recon at a host (also the `d` key) — **steering** |
| `/found <fact>` | Submit a hands-on finding (credential / behavior / new asset) for the Copilot to confirm and fold into the shared model — **enrichment** (§5.8) |
| `/findings` | Jump to the prioritized findings list |
| `/cov` | Open the coverage ledger (§5.6) |
| `/scope` | View / edit engagement scope (re-runs the gate) |
| `/mode red` \| `/mode white` | Switch recon posture; the header + pacing change live |
| `/report` | Generate and preview the report (§5.7) |
| `/digest` | Show the "what changed / newly actionable / needs you" rollup on demand (§5.9) |
| `/pause` \| `/resume` | Checkpoint + quiesce, or reload + re-attach — for multi-session marathons (§5.9) |
| `/handoff` | Emit a shift-handoff summary for a later session/operator (§5.9) |
| `/quit` | Exit (confirm if recon running) |

**Two directions, not to be confused.** `s / send to copilot` pushes a *recon-discovered* asset **into** the Copilot conversation (breadth→depth). `/found` submits *your own* hands-on discovery **into** the shared model via the Copilot's confirm-and-enrich (§5.8). Plain prose works for `/found` too — telling the Copilot "I cracked creds for svc_admin" triggers the same confirm-then-enrich flow; the command is just the explicit form.

### 6.6 Mode switch — what changes visibly

`/mode red` flips the header to **Red-stealth**, recolors the live indicator, and the recon panel begins showing pacing/jitter status; the backend swaps to quiet tooling and low-and-slow timing (Auto-Recon Blueprint §3). `/mode white` reverses it. The switch is live, mid-engagement.

---

## 7. State Transitions

```text
  NEW ENGAGEMENT ──Enter──► PREFLIGHT ──start──► MAIN SPLIT (overview)
                                                   │   ▲
                              /focus <cat> | Enter │   │ Esc
                                                   ▼   │
                                            CATEGORY FOCUS (expanded)
                                                   │   ▲
                                       Enter on asset │   │ Esc
                                                   ▼   │
                                             ASSET DETAIL ──[s]──► (chat, left)

   enrichment (any state):  /found <fact> | prose  ─►  COPILOT CONFIRMS (left)
                            ─► on ✓: graph write ─► candidates re-derive (◐/○ → ●)
                               ─► re-recon sprint ─► PATHS UPDATED (right)   (§5.8)
   overlays (any state):  COVERAGE (/cov) · REPORT (/report) · HELP (?) · PALETTE (Ctrl-K)
   interrupts (any state): CRITICAL ALERT toast  ─ Enter→focus the asset / esc→dismiss
   streaming (always):     findings, wave progress, coverage update the panels live
```

- Recon **streams** into whatever screen is open — focusing a category does not pause the engine; new findings appear in place.
- The Copilot pane is **always live** on the left; the right pane's depth-state (overview / focus / detail) is independent of it, so you can read recon detail while a Copilot reply streams.
- **Enrichment is not a mode you enter** — `/found` (or a prose finding) works from any screen. The confirm runs in the left pane; the right pane's candidates and paths re-derive in place as the fact lands (§5.8). This is the visible form of the enrichment channel (Main Proposal §3.3).

---

## 8. Realistic Notes

- **One terminal, two busy panes.** Keep the split readable at 100–120 cols; below that, focus mode should be able to take the full width (the chat collapses to a status line) so detail still has room.
- **The TUI never blocks on the backend.** Every command is fire-and-forget over IPC; the panel reflects results when events arrive. A slow or busy backend (e.g., the HardwareArbiter making inference wait) shows as a status indicator, never a frozen UI.
- **Reconnect cleanly.** If the backend restarts, the TUI requests a full state snapshot and repaints — the engagement lives in the backend, not the UI.
