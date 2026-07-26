#!/usr/bin/env bash
# Saltpilot-on-Hermes wiring — reproduces Milestone 0 tasks 0.1 and 0.5.
#
# Installs Hermes Agent, installs this Saltpilot package (so its MCP console scripts exist),
# registers the three Saltpilot MCP servers + the recon skill with Hermes, and points Hermes's
# model endpoint at a local Ollama /v1. Idempotent: safe to re-run.
#
# 0.1  Install Hermes; confirm `hermes` runs; model endpoint -> local Ollama (Foundation-Sec-8B).
# 0.5  Register the skill + MCP servers with Hermes; drive from the `hermes` CLI.
#
# On the reference box, run `ollama serve` with `foundation-sec-8b` pulled so the endpoint below
# serves the real weights. This container has no GPU and the Ollama model registry is blocked, so
# there the endpoint is exercised with a local OpenAI-compatible stub instead (see the repo notes).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${HERMES_VENV:-/opt/hermes-venv}"
LAB="${SALTPILOT_LAB:-$HOME/saltpilot-lab}"
ENGAGEMENT="$LAB/engagement.toml"
DB="$LAB/engagement.sqlite"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434/v1}"
MODEL="${SALTPILOT_MODEL:-foundation-sec-8b}"
export HERMES_ACCEPT_HOOKS=1

echo "==> 1. Hermes Agent + Saltpilot into $VENV"
[ -x "$VENV/bin/hermes" ] || python3 -m venv "$VENV"
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet 'hermes-agent[mcp]'
"$VENV/bin/pip" install --quiet "$REPO"           # provides saltpilot-{scope,graph,recon}-mcp
HERMES="$VENV/bin/hermes"
"$HERMES" --version

echo "==> 2. Lab engagement + graph DB at $LAB"
mkdir -p "$LAB"
[ -f "$ENGAGEMENT" ] || cp "$REPO/engagement.example.toml" "$ENGAGEMENT"
"$VENV/bin/python" - "$ENGAGEMENT" "$DB" <<'PY'
import sys
from saltpilot.config import load_engagement
from saltpilot.store import GraphStore
eng = load_engagement(sys.argv[1])
s = GraphStore(sys.argv[2]); s.init_schema(); s.upsert_engagement(eng)
print("engagement:", eng.id)
PY

echo "==> 3. Register the three Saltpilot MCP servers (remove-then-add = idempotent)"
scope_bin="$VENV/bin/saltpilot-scope-mcp"; graph_bin="$VENV/bin/saltpilot-graph-mcp"; recon_bin="$VENV/bin/saltpilot-recon-mcp"
for name in saltpilot-scope saltpilot-graph saltpilot-recon; do
  "$HERMES" mcp remove "$name" >/dev/null 2>&1 || true
done
yes | "$HERMES" mcp --accept-hooks add saltpilot-scope --connect-timeout 30 \
  --command "$scope_bin" --env "SALTPILOT_ENGAGEMENT=$ENGAGEMENT" 2>/dev/null | grep -E "Connected|Saved" || true
yes | "$HERMES" mcp --accept-hooks add saltpilot-graph --connect-timeout 30 \
  --command "$graph_bin" --env "SALTPILOT_DB=$DB" 2>/dev/null | grep -E "Connected|Saved" || true
yes | "$HERMES" mcp --accept-hooks add saltpilot-recon --connect-timeout 30 \
  --command "$recon_bin" --env "SALTPILOT_ENGAGEMENT=$ENGAGEMENT" "SALTPILOT_DB=$DB" 2>/dev/null | grep -E "Connected|Saved" || true

echo "==> 4. Install the recon skill"
skill_dir="${HERMES_HOME:-$HOME/.hermes}/skills/security/saltpilot-recon"
mkdir -p "$skill_dir"
cp "$REPO/saltpilot/skill/SKILL.md" "$skill_dir/SKILL.md"

echo "==> 5. Point the model endpoint at local Ollama"
"$HERMES" config set model.name "$MODEL" --force >/dev/null
"$HERMES" config set model.base_url "$OLLAMA_URL" --force >/dev/null
"$HERMES" config set model.provider ollama --force >/dev/null
"$HERMES" config set model.api_key ollama --force >/dev/null

echo "==> Done. Verify:"
"$HERMES" mcp list
"$HERMES" skills list | grep -i saltpilot || true
