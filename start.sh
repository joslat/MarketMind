#!/usr/bin/env bash
# ── MarketMind — launch the whole stack with .NET Aspire ────────────────────────────────────────
# Brings up: the Neo4j container + the MarketMind.Api backend + the React/Vite frontend, wired together,
# with the Aspire dashboard. Prefers the `aspire` CLI if installed; otherwise falls back to `dotnet run`.
#
#   ./start.sh
#
# Set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY first to enable the live agent (/api/agent +
# the "Explain with AI" button). Needs Docker running for the Neo4j container.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
APPHOST="src/MarketMind.AppHost"

# Docker is needed for the Neo4j container — warn but don't hard-fail (the in-proc engine works without it).
if ! docker info >/dev/null 2>&1; then
  echo "⚠  Docker is not reachable — the Neo4j container won't start. Start Docker Desktop, or proceed:"
  echo "   the API + frontend still run (the deterministic in-proc engine needs no DB)."
fi

# Live agent is optional — it lights up only when Azure OpenAI keys are present.
if [[ -n "${AZURE_OPENAI_ENDPOINT:-}" && -n "${AZURE_OPENAI_API_KEY:-}" ]]; then
  echo "✓  Azure OpenAI configured — the live agent (/api/agent + 'Explain with AI') is enabled."
else
  echo "ℹ  No Azure OpenAI keys — deterministic paths work; the live agent stays inert (set the keys to enable it)."
fi

# Prefer the Aspire CLI (richer dashboard + run tooling); fall back to the always-present dotnet path.
if command -v aspire >/dev/null 2>&1; then
  echo "▶  aspire run  ($APPHOST)"
  cd "$APPHOST"
  exec aspire run
else
  echo "▶  dotnet run --project $APPHOST   (tip: install the Aspire CLI — 'dotnet tool install -g aspire.cli' — for 'aspire run')"
  exec dotnet run --project "$APPHOST"
fi
