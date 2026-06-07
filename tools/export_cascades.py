"""
export_cascades.py — run the engine per event and write the UI's cascade JSON
(the cascade JSON contract) to web/public/cascades/<id>.json.

  python tools/export_cascades.py

Each node carries: impact · band (Severe/High/Moderate/Marginal) · direction · hop · confidence ·
lat/lng · path (strongest chain) · and the Time-Machine ground truth `actual` (real abnormal
return %, dir, hit ✓/✗) from golden.json. Each link carries source_ref (provenance).

The product path is MarketMind.Export (.NET) emitting the SAME contract (AGENTS.md §2).
"""
import json
import os
from collections import deque
from engine import EVENTS, COMPANIES, EDGES, ADJ, predicted_impacts, seed_event, _regime, DEFAULT_PARAMS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUTDIR = os.path.join(ROOT, "web", "public", "cascades")
MAX_HOPS = 3
TYPE_ABBR = {"SUPPLIES_TO": "SUP", "PARTNERS_WITH": "PAR", "OWNS": "OWN", "COMPETES_WITH": "CMP"}

params = dict(DEFAULT_PARAMS)
cw = os.path.join(HERE, "calibrated_weights.json")
if os.path.exists(cw):
    params.update(json.load(open(cw, encoding="utf-8")))
golden = json.load(open(os.path.join(HERE, "golden.json"), encoding="utf-8")) if os.path.exists(os.path.join(HERE, "golden.json")) else {}


def band(v):
    a = abs(v)
    return "Severe" if a >= 0.5 else "High" if a >= 0.25 else "Moderate" if a >= 0.1 else "Marginal"


def confidence(hop):
    # heuristic: decays with hop distance (f of hops; edge-weight/agreement terms are future work)
    return round(max(0.15, 1.0 - 0.25 * hop), 2)


def bfs(seed_tickers, reached):
    """min hop + parent(ticker, edge-type) over the cascade adjacency, within `reached`."""
    hop, parent = {}, {}
    q = deque()
    for s in seed_tickers:
        if s in reached:
            hop[s] = 0
            q.append(s)
    while q:
        cur = q.popleft()
        d = hop[cur]
        if d >= MAX_HOPS:
            continue
        for nb, t, _w, _dir in ADJ.get(cur, []):
            if nb in reached and nb not in hop:
                hop[nb] = d + 1
                parent[nb] = (cur, t)
                q.append(nb)
    for tk in reached:
        hop.setdefault(tk, 0)
    return hop, parent


def path_string(tk, parent):
    chain = [tk]
    types = []
    cur = tk
    while cur in parent:
        prev, t = parent[cur]
        types.append(TYPE_ABBR.get(t, "?"))
        chain.append(prev)
        cur = prev
        if len(chain) > 5:
            break
    chain.reverse()
    types.reverse()
    if len(chain) == 1:
        return chain[0]
    parts = [chain[0]]
    for i, t in enumerate(types):
        parts.append(f"—{t}→ {chain[i + 1]}")
    return " ".join(parts)


def export_event(ev, split="TRAIN"):
    imp = predicted_impacts(ev, params)
    seeds = dict(seed_event(ev, params))
    contagion = _regime(ev)
    reached = set(imp) | {s for s in seeds if s in COMPANIES}
    hop, parent = bfs(seeds.keys(), reached)
    g = golden.get(ev["id"], {})

    nodes = []
    for tk in sorted(reached, key=lambda t: (hop.get(t, 0), -abs(imp.get(t, 0.0)), t)):  # ticker = stable tie-break
        c = COMPANIES.get(tk, {})
        v = round(imp.get(tk, 0.0), 4)
        node = {
            "id": tk, "name": c.get("name", tk), "sector": c.get("sector"),
            "country": c.get("country"), "lat": c.get("lat"), "lng": c.get("lng"),
            "tradable": bool(c.get("tradable", False)),
            "impact": v, "band": band(v), "direction": "gain" if v >= 0 else "loss",
            "hop": hop.get(tk, 0), "confidence": confidence(hop.get(tk, 0)),
            "path": path_string(tk, parent),
        }
        if tk in g:  # Time Machine: realized abnormal return
            abn = g[tk]["abn"]
            node["actual"] = round(abn * 100, 2)
            node["actualDir"] = "gain" if abn >= 0 else "loss"
            node["hit"] = (v >= 0) == (abn >= 0)
        nodes.append(node)

    links = []
    for e in EDGES:
        a, b = e["from"], e["to"]
        if a in reached and b in reached:
            ha, hb = hop.get(a, 0), hop.get(b, 0)
            deep = b if hb >= ha else a
            links.append({
                "source": a, "target": b, "type": e["type"], "weight": e["weight"],
                "sign": 1 if imp.get(deep, 0.0) >= 0 else -1,
                "hop": max(ha, hb), "magnitude": round(abs(imp.get(deep, 0.0)), 4),
                "source_ref": e.get("source", "public"),
            })

    maxhop = max([n["hop"] for n in nodes], default=0)
    hops = [[n["id"] for n in nodes if n["hop"] == h] for h in range(maxhop + 1)]

    # event severity = strongest seed/hit; geo = event epicenter or the top hit's HQ
    sev = max([abs(s) for s in seeds.values()] + [h["severity"] for h in ev.get("hits", [])] + [0.0])
    geo = ev.get("geo")
    if not geo and ev.get("hits"):
        top = COMPANIES.get(ev["hits"][0]["ticker"], {})
        if top.get("lat") is not None:
            geo = {"lat": top["lat"], "lng": top["lng"], "zone": top.get("country")}

    return {
        "event": {"id": ev["id"], "headline": ev["headline"], "regime": "contagion" if contagion else "substitution",
                  "scope": ev.get("scope", "company"), "date": ev["date"], "category": ev.get("category"),
                  "severity": round(sev, 2), "geo": geo, "split": split},
        "nodes": nodes, "links": links, "hops": hops,
        "meta": {
            "weights": {k: params[k] for k in ("fSupDown", "fSupUp", "fPar", "fOwn", "fCmp", "hopDecay", "minImpact")},
            "seeds": [{"ticker": t, "seed": round(v, 4)} for t, v in sorted(seeds.items(), key=lambda kv: -abs(kv[1])) if t in COMPANIES],
            "reached": len(nodes), "scored": sum(1 for n in nodes if "actual" in n),
        },
    }


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    index = []
    for i, (eid, ev) in enumerate(EVENTS.items()):
        split = "TEST" if i % 3 == 0 else "TRAIN"   # mirrors tools/calibrate.py held-out split
        data = export_event(ev, split)
        with open(os.path.join(OUTDIR, f"{eid}.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        index.append({"id": eid, "headline": ev["headline"], "date": ev["date"],
                      "regime": data["event"]["regime"], "scope": ev.get("scope", "company"),
                      "severity": data["event"]["severity"], "reached": data["meta"]["reached"]})
        hits = sum(1 for n in data["nodes"] if n.get("hit"))
        scored = data["meta"]["scored"]
        print(f"  {eid:34} {data['event']['regime']:12} reached={data['meta']['reached']:3}  golden-hit={hits}/{scored}")
    index.sort(key=lambda x: x["date"])
    with open(os.path.join(OUTDIR, "index.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, indent=1)
    print(f"wrote {len(index)} cascades + index.json -> web/public/cascades/")


if __name__ == "__main__":
    main()
