# MarketMind — shockwave UI

Cinematic React/Vite front-end that plays a precomputed cascade as a timed "shockwave"
over the dependency graph. No backend — it reads static JSON.

## Run
```bash
# 1) generate the cascade data (from repo root, needs the lab venv with the engine)
python tools/export_cascades.py        # -> web/public/cascades/*.json + index.json

# 2) run the app
cd web
npm install
npm run dev                            # opens http://localhost:5173
```

## What you'll see
- The **graph** settles, then a headline lands and the impact **ripples outward**
  hop-by-hop: particles fire along edges, nodes ignite green (gain) / red (loss), fading per hop.
- The **Impact Ledger** (left) counts up losers/winners by magnitude.
- The **Reasoning rail** (right) narrates the chain + the **regime** (contagion vs substitution).
- The **dock** (bottom) switches events, replays, and shows the calibrated weights.

Try `evt_chip_controls_tighten_2023` (watch **SMIC turn green** as a sanction winner) and
`evt_deepseek_selloff_2025` (a pure AI-capex **theme** shock with no direct company hit).

## Data contract
Each `public/cascades/<id>.json` = `{ event, nodes[], links[], hops[][], meta }`
produced by `tools/export_cascades.py` (the disposable lab bridge;
the product path is `MarketMind.Export` (.NET) emitting the same contract).

## Stack
React 18 · Vite 5 · TypeScript · react-force-graph-2d · Zustand. Color/type tokens per §12.3.
