"""
merge_expansion.py — deterministically merge verified workflow proposals into data/*.json.

The graph-expansion workflow returns { domains:[{companies,edges,...}], events:{events,...} }.
Save that JSON to data/_expansion_raw.json, then run this. It is CONSERVATIVE:
adds only clearly-valid, non-duplicate items and prints everything it skipped, so the
curated + validated invariant holds. data_qa.py is still the gate afterwards.

  python tools/merge_expansion.py [path-to-raw.json]

Dedup rules:
  • company: unique ticker; existing/core wins, collisions skipped + reported
  • SUPPLIES_TO/PARTNERS_WITH/OWNS: unique (from,type,to)
  • COMPETES_WITH: unique unordered pair (no reverse duplicate)
  • edge endpoints must exist in the merged company set; weights must be in range
  • event: new id; every hit ticker must exist; category in enum
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

TYPE_RANGE = {"SUPPLIES_TO": (0.0, 1.0), "PARTNERS_WITH": (0.0, 1.0),
              "OWNS": (0.0, 100.0), "COMPETES_WITH": (0.0, 1.0)}
CATEGORIES = {"supply_chain_disruption", "demand_surge", "regulatory", "earnings", "macro", "sector"}
EVENT_FIELDS = ("id", "headline", "date", "source", "url", "category", "hits")
HIT_FIELDS = ("ticker", "sign", "severity", "why")


def load(name):
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


def save(name, obj):
    with open(os.path.join(DATA, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def main():
    raw_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(DATA, "_expansion_raw.json")
    raw = json.load(open(raw_path, encoding="utf-8"))

    cj = load("companies.json")
    ej = load("edges.json")
    vj = load("events.json")
    companies, edges, events = cj["companies"], ej["edges"], vj["events"]

    tickers = {c["ticker"] for c in companies}
    directed = {(e["from"], e["type"], e["to"]) for e in edges}
    cmp_pairs = {frozenset((e["from"], e["to"])) for e in edges if e["type"] == "COMPETES_WITH"}
    event_ids = {ev["id"] for ev in events}

    skipped = {"companies": [], "edges": [], "events": []}
    added = {"companies": 0, "edges": 0, "events": 0}

    domains = raw.get("domains", [])

    # ---- pass 1: companies ----
    for d in domains:
        for c in d.get("companies", []) or []:
            tk = c.get("ticker")
            if not tk or tk in tickers:
                skipped["companies"].append(f"{tk} ({d.get('domain')}): duplicate/empty")
                continue
            row = {k: c.get(k) for k in ("ticker", "name", "sector", "country", "tradable", "priceTicker", "benchmark")}
            if c.get("tradable") and (not c.get("priceTicker") or not c.get("benchmark")):
                skipped["companies"].append(f"{tk}: tradable but missing priceTicker/benchmark")
                continue
            companies.append(row)
            tickers.add(tk)
            added["companies"] += 1

    # ---- pass 2: edges (endpoints now known) ----
    def add_edge(e, dom):
        ty = e.get("type")
        a, b, w = e.get("from"), e.get("to"), e.get("weight")
        if a not in tickers or b not in tickers:
            skipped["edges"].append(f"{a}-{ty}-{b} ({dom}): endpoint missing")
            return
        if a == b:
            skipped["edges"].append(f"{a}-{ty}-{b}: self-loop")
            return
        lo, hi = TYPE_RANGE.get(ty, (None, None))
        if lo is None or not isinstance(w, (int, float)) or not (lo <= w <= hi):
            skipped["edges"].append(f"{a}-{ty}-{b}={w}: bad type/weight")
            return
        if (a, ty, b) in directed:
            skipped["edges"].append(f"{a}-{ty}-{b}: duplicate")
            return
        if ty == "COMPETES_WITH" and frozenset((a, b)) in cmp_pairs:
            skipped["edges"].append(f"{a}~{b}: duplicate COMPETES pair")
            return
        edges.append({"from": a, "type": ty, "to": b, "weight": round(float(w), 2),
                      "source": e.get("source", "public")})
        directed.add((a, ty, b))
        if ty == "COMPETES_WITH":
            cmp_pairs.add(frozenset((a, b)))
        added["edges"] += 1

    for d in domains:
        for e in d.get("edges", []) or []:
            add_edge(e, d.get("domain"))

    # ---- events ----
    ev_block = (raw.get("events") or {}).get("events", []) or []
    for ev in ev_block:
        eid = ev.get("id")
        if not eid or eid in event_ids:
            skipped["events"].append(f"{eid}: duplicate/empty")
            continue
        if ev.get("category") not in CATEGORIES:
            skipped["events"].append(f"{eid}: bad category {ev.get('category')}")
            continue
        hits = ev.get("hits") or []
        bad = [h.get("ticker") for h in hits if h.get("ticker") not in tickers]
        if not hits or bad:
            skipped["events"].append(f"{eid}: missing hit tickers {bad}")
            continue
        clean = {k: ev.get(k) for k in EVENT_FIELDS}
        clean["hits"] = [{k: h.get(k) for k in HIT_FIELDS} for h in hits]
        events.append(clean)
        event_ids.add(eid)
        added["events"] += 1

    # refresh the sectors list in companies _meta
    cj.setdefault("_meta", {})["sectors"] = sorted({c["sector"] for c in companies})

    save("companies.json", cj)
    save("edges.json", ej)
    save("events.json", vj)

    print(f"added: companies={added['companies']} edges={added['edges']} events={added['events']}")
    print(f"totals: companies={len(companies)} edges={len(edges)} events={len(events)}")
    for kind in ("companies", "edges", "events"):
        if skipped[kind]:
            print(f"\nskipped {kind} ({len(skipped[kind])}):")
            for s in skipped[kind]:
                print(f"  - {s}")


if __name__ == "__main__":
    main()
