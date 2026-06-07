# MarketMind

### When the news names one company, who *else* just moved — and who quietly won?

A US export ban hit the chip sector. Every name went red. One went green — **SMIC**, a Chinese foundry the *same
sanction protects*. Nobody typed its name; the graph found it.

MarketMind is a **graph-native news-impact reasoning engine** on Neo4j. Drop a market event onto a curated
company-dependency graph — suppliers, customers, partners, owners, rivals, and the standing sanctions over all of
them — and it traces who *else* is in the blast radius: how hard they're hit, along what path, and which way they
move. It reasons about **exposure, not price.**

> **This repository is the reasoning *substrate*, not a trading system.** The graph, the cascade engine, and the
> honest validation harness are all here. There is no live-news pipeline, no strategy, no position sizing, and no
> P&L-tuned weights — none of that is in this repo. It's the explainable core; the alpha (if any) is built above
> it, privately. That separation is exactly what makes this safe to open-source.

**It is NOT a price predictor**, and it says so: on a held-out backtest, next-day direction is ≈ a coin flip
(it ties a whole-sector baseline). Its validated value is **reach** — surfacing ~20% of the movers the headline
never named (vs 0% for a headline-only reader) — and an **auditable path** for every one. See
[`DISCLAIMER.md`](DISCLAIMER.md).

---

## The graph (small and deliberately curated)

Small on purpose — **104 companies · 257 dependency edges · 27 events** — every edge hand-vetted. One rule makes it
work: only **four** `Company→Company` edge types ever propagate — `SUPPLIES_TO`, `COMPETES_WITH` (sign-flipping),
`OWNS`, `PARTNERS_WITH`. Everything else (countries, commodities, themes, **standing sanctions**) only *seeds* the
shock and is never traversed company-to-company. A standing `Condition` node carries a **signed** constraint
(− for the firms it hurts, + for the domestic one it protects) — tighten it once and the whole sector re-prices,
beneficiary included. That's the SMIC-green mechanism.

Full write-up: [`docs/schema-and-data.md`](docs/schema-and-data.md).

## The engine, in three languages at parity

The directional, regime-aware cascade is implemented identically in **Python** (`tools/engine.py`), **Cypher**
(`cypher/02`, surfaced as the Aura agent tools in `cypher/05`), and **C#** (`src/MarketMind.Engine`) — checked
sign-for-sign by `tools/parity_neo4j.py` and `MarketMind.Export`. The honest backtest harness (`tools/calibrate.py`)
is included so you can reproduce the negative result yourself.

---

## Quickstart

**See it move (the web app):**
```bash
cd web && npm install && npm run dev          # → http://localhost:5173  (runs off the shipped cascade feed)
```

**Run the engine / check parity (no DB needed):**
```bash
dotnet run --project src/MarketMind.Export     # C# engine ≡ Python reference, sign-for-sign
python tools/engine.py                         # the Python reference cascade
python tools/data_qa.py                         # the data-integrity gate
```

**Run the whole stack (.NET Aspire):** `./start.sh` (Neo4j container + API + web).
The app has one feature toggle — `MM_MARKETMIND_MODE = Local | Aura` (see `src/MarketMind.Backend/MarketMindMode.cs`):
Local = the local **Docker** Neo4j over its Query API; Aura = the hosted Neo4j **Aura** graph. Either works —
but the DB starts empty, so **seed it first**: see [**Database**](#database--run-it-against-docker-neo4j-or-aura) below.

**Use it as a Neo4j Aura Agent:** the complete production agent — name · description · system prompt · all its
tools — is exported as one importable file, [`cypher/MarketMind.json`](cypher/MarketMind.json). Load `cypher/01`
into an AuraDB instance, then **import `cypher/MarketMind.json` into a Neo4j Aura Agent** (the counterpart to the
console's *export as json*) and point it at the graph. The individual Cypher-Template tool bodies (calibrated
weights inlined) are also in [`cypher/05-aura-tools.cypher`](cypher/05-aura-tools.cypher) if you'd rather register
them by hand.

> **Note on data:** the realized-returns dataset (`tools/golden.json` / `cypher/03`) is **not** distributed
> (it's Yahoo/`yfinance`-derived — their ToS prohibit redistribution). Regenerate it locally with
> `tools/build_golden_dataset.py` from a price source of your choosing; the builder ships, its output does not.

---

## Database — run it against Docker Neo4j *or* Aura

`/api/cascade` runs the **same** `impact_cascade` Cypher (`cypher/05`) over a Neo4j **HTTP Query API** in both
modes — only the target URL and login change. The one switch is `MM_MARKETMIND_MODE`:

| Mode | `/api/cascade` data source | Login env vars | Default |
|---|---|---|---|
| `Local` *(default)* | local **Docker** Neo4j — `http://localhost:7474` | `MM_LOCAL_NEO4J_PASSWORD` (user `neo4j`) | `neo4j_local_dev` |
| `Aura` | hosted **Aura** graph — `https://<dbid>.databases.neo4j.io` | `MM_NEO4J_ID` + `MM_NEO4J_PASSWORD` | — |

The rows are identical sign-for-sign to the in-proc engine either way — the math just runs in the DB.

### A) Local — Docker Neo4j
```bash
# 1) start Neo4j 5.26 + APOC (name & password match the tools and the AppHost defaults)
docker run -d --name marketmind-neo4j -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/neo4j_local_dev -e NEO4J_PLUGINS='["apoc"]' neo4j:5.26

# 2) load the graph — companies · edges · events · conditions · ImpactRecord skeletons
docker exec -i marketmind-neo4j cypher-shell -u neo4j -p neo4j_local_dev < cypher/01-marketmind-seed.cypher

# 3) (optional) realized-return values + vector index
docker exec -i marketmind-neo4j cypher-shell -u neo4j -p neo4j_local_dev < cypher/03-fill-impactrecords.cypher  # if regenerated — see the data note above
docker exec -i marketmind-neo4j cypher-shell -u neo4j -p neo4j_local_dev < cypher/04-embeddings.cypher          # optional vector index

# 4) run (Local is the default mode) and sanity-check
./start.sh
python tools/parity_neo4j.py          # confirms the DB rows == the Python reference, sign-for-sign
```
> `./start.sh` (Aspire) also starts a Neo4j container but does **not** auto-load the seed — run step 2 against
> whichever local instance you use. If you only need the cascade without a DB, the in-proc path needs nothing:
> `dotnet run --project src/MarketMind.Export`.

### B) Aura — hosted Neo4j
```bash
# 1) load the SAME seed into your AuraDB instance — Aura Browser (paste cypher/01) or cypher-shell:
cat cypher/01-marketmind-seed.cypher | cypher-shell -a neo4j+s://<dbid>.databases.neo4j.io -u neo4j -p '<db-password>'

# 2) point the app at it and flip the toggle
export MM_MARKETMIND_MODE=Aura
export MM_NEO4J_ID=<dbid>            # the AuraDB id (it doubles as the Query-API user)
export MM_NEO4J_PASSWORD=<db-password>
./start.sh
```
Setting up the hosted **Aura Agent** (the natural-language `/api/explain` head) is a separate, manual console
step — import [`cypher/MarketMind.json`](cypher/MarketMind.json) (or register the `cypher/05` tool bodies by
hand). The DB-backed `/api/cascade` above needs only the DB login, not the agent.

### Configuration (environment variables)

| Var | Used by | Meaning |
|---|---|---|
| `MM_MARKETMIND_MODE` | API · Export | `Local` (Docker) or `Aura` (hosted). Default `Local`. |
| `MM_LOCAL_NEO4J_PASSWORD` | API · AppHost | Local Docker DB password (user `neo4j`). Default `neo4j_local_dev`. |
| `MM_LOCAL_QUERY_URL` | API | Override the local Query API URL. Default `http://localhost:7474/db/neo4j/query/v2`. |
| `MM_NEO4J_ID` / `MM_NEO4J_PASSWORD` | API | AuraDB id + password (used in `Aura` mode). |
| `AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` | API · Agent | Enable the live MAF "Explain with AI" agent (optional). |
| `AURA_ENDPOINT_URL` / `AURA_CLIENT_ID` / `AURA_CLIENT_SECRET` | API | Hosted Aura *agent* channel (optional; manual setup). |

---

## Layout
```
src/        the .NET stack — Engine · Backend (the Local↔Aura toggle) · Agent (MAF) · Api · Export · AppHost
web/        the cinematic React/Vite app (shockwave graph, map, "time machine", drill-down)
cypher/     01 seed · 02 cascade engine · 04 vector index · 05 Aura tool bodies · MarketMind.json (importable Aura agent)
tools/      engine.py · calibrate.py (the honest harness) · parity_neo4j.py · the generators · the dataset builder
data/       the curated graph (CC-BY-4.0)
docs/       the schema & data explainer
```

## License
- **Code** — Apache-2.0 ([`LICENSE`](LICENSE))
- **Data & docs** — CC-BY-4.0 ([`LICENSE-DATA`](LICENSE-DATA)) · attribution: *Jose Luis Latorre Millas / MarketMind*
- See [`NOTICE`](NOTICE) for provenance and [`DISCLAIMER.md`](DISCLAIMER.md) — **not investment advice.**

*Reasoning and exposure, not prediction — with the validation kept in the open.*
