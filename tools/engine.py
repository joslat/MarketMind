"""
MarketMind cascade engine (Python reference) — v2.

Reads data/*.json (the single source of truth) and implements the cascade contract:
  PHASE 0  macro seeder (one-way): a NewsEvent's macro seeds (country / commodity /
           theme / condition) fan OUT into companies, damped by exposure, becoming
           derived company seeds. (Active only when data/macro.json + event 'seeds' exist.)
  PHASE 1  structural cascade over the FROZEN whitelist
           SUPPLIES_TO|PARTNERS_WITH|OWNS|COMPETES_WITH, 0..3 hops, with:
             - DIRECTIONAL SUPPLIES_TO: supplier->customer fSupDown > customer->supplier fSupUp
             - COMPETES_WITH sign-flip (-fCmp), suppressed in contagion regime
             - per-edge factor * weight * hopDecay, prune |impact| < minImpact (calibrated)

Mirrors cypher/02. Calibrator tunes the SAME params.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

WHITELIST = {"SUPPLIES_TO", "PARTNERS_WITH", "OWNS", "COMPETES_WITH"}  # frozen cascade types


def _load(name, default=None):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


_companies = _load("companies.json")["companies"]
_edges = _load("edges.json")["edges"]
_events = _load("events.json")["events"]
_macro = _load("macro.json", {}) or {}

# ---- public-ish views (kept close to the old API for calibrate.py) ----
COMPANIES = {c["ticker"]: c for c in _companies}
EDGES = _edges
EVENTS = {e["id"]: e for e in _events}

DEFAULT_PARAMS = {
    # Phase 1 (structural)
    "fSupDown": 0.70, "fSupUp": 0.40, "fPar": 0.50, "fOwn": 0.55, "fCmp": 0.45,
    "hopDecay": 0.65, "minImpact": 0.03,
    # Phase 0 (macro seeder)
    "fProd": 0.60, "fCons": 0.60, "fTheme": 0.70, "fCondition": 0.80, "minSeed": 0.05,
    "chOperations": 1.00, "chDemand": 0.80, "chCurrency": 0.60, "chPolicy": 1.00,
    "domicileDefault": 0.40,
}
MAX_HOPS = 3

# ───────────────────────── adjacency (directional-aware) ─────────────────────────
# adj[node] = list of (neighbor, type, weight, node_is_supplier)
def _build_adj():
    a = {}
    for e in _edges:
        t = e["type"]
        if t not in WHITELIST:
            continue
        w = e["weight"] / 100.0 if t == "OWNS" else e["weight"]
        f, to = e["from"], e["to"]
        # from-node is the supplier/owner/origin; to-node is the customer/sub
        a.setdefault(f, []).append((to, t, w, True))
        a.setdefault(to, []).append((f, t, w, False))
    return a


ADJ = _build_adj()


def _type_factor(t, node_is_supplier, p):
    if t == "SUPPLIES_TO":
        return p["fSupDown"] if node_is_supplier else p["fSupUp"]   # directional
    if t == "PARTNERS_WITH":
        return p["fPar"]
    if t == "OWNS":
        return p["fOwn"]
    if t == "COMPETES_WITH":
        return -p["fCmp"]                                            # sign flip
    return 0.4


# ───────────────────────── Phase 1: structural cascade ─────────────────────────
def cascade(seeds, params=DEFAULT_PARAMS, contagion=False):
    """seeds: list of (ticker, signed_value). Returns {ticker: impact}. Directional."""
    p = params
    minI, hop = p["minImpact"], p["hopDecay"]
    impact = {}

    def dfs(node, val, depth, visited):
        impact[node] = impact.get(node, 0.0) + val
        if depth >= MAX_HOPS:
            return
        for nb, t, w, node_is_supplier in ADJ.get(node, []):
            if nb in visited:
                continue
            if contagion and t == "COMPETES_WITH":
                continue  # contagion regime: rivals fall together, no inversion
            f = _type_factor(t, node_is_supplier, p)
            nv = val * f * w * hop
            if abs(nv) < minI:
                continue
            dfs(nb, nv, depth + 1, visited | {nb})

    for tk, v in seeds:
        if tk in ADJ or tk in COMPANIES:
            dfs(tk, v, 0, {tk})
    return {k: v for k, v in impact.items() if abs(v) >= minI}


# ───────────────────────── Phase 0: macro seeder ─────────────────────────
# Build exposure lookups from macro.json.exposureEdges (graceful if absent).
def _exposure_index():
    idx = {
        "REVENUE_FROM": {}, "OPERATES_IN": {}, "EXPOSED_TO_POLICY": {},
        "PRODUCES": {}, "CONSUMES": {}, "EXPOSED_TO_THEME": {}, "CONSTRAINS": {},
    }
    for e in _macro.get("exposureEdges", []):
        rel = e.get("rel")
        if rel in idx:
            idx[rel].setdefault(e["from"], []).append(e)
    # CONSTRAINS is keyed by condition id (from) -> targets
    return idx


EXPO = _exposure_index()


def _company_country_exposure(ticker, code, channel, params):
    """exposure of `ticker` to country `code` for a given channel."""
    def _val(rel):
        for e in EXPO[rel].get(ticker, []):
            if e["to"] == code:
                return e.get("value", 0.0), e.get("sign", 1)
        return None
    if channel == "operations":
        v = _val("OPERATES_IN")
        return v[0] if v else None
    if channel == "demand":
        v = _val("REVENUE_FROM")
        return v[0] if v else None
    if channel == "currency":
        # use the REVENUE_FROM value (same as C#/Cypher). NOTE: no fxSensitivity fallback —
        # it never existed on any edge and diverged from the other two engines; keep all three aligned.
        v = _val("REVENUE_FROM")
        return v[0] if v else None
    if channel == "policy":
        v = _val("EXPOSED_TO_POLICY")
        return v[0] * v[1] if v else None   # value*sign; NO country-agnostic policyBeta fallback (it leaked across countries)
    return None


def seed_event(event, params=DEFAULT_PARAMS):
    """Expand an event into company seeds: direct company hits + Phase-0 macro fan-out."""
    p = params
    seeds = {}

    def add(tk, v):
        seeds[tk] = seeds.get(tk, 0.0) + v

    for h in event.get("hits", []):
        add(h["ticker"], h["sign"] * h["severity"])

    ch_t = {"operations": p["chOperations"], "demand": p["chDemand"],
            "currency": p["chCurrency"], "policy": p["chPolicy"]}
    for s in event.get("seeds", []):
        typ, sid, sign, sev = s["type"], s["id"], s["sign"], s["severity"]
        if typ == "country":
            cv = event.get("channelVector") or {"operations": 0.5, "demand": 0.5}
            for tk in COMPANIES:
                tot = 0.0
                touched = False
                for k, cw in cv.items():
                    if not cw:
                        continue
                    ex = _company_country_exposure(tk, sid, k, p)
                    if ex is None:
                        continue
                    touched = True
                    tot += cw * ex * ch_t.get(k, 0.5)
                if not touched and COMPANIES[tk].get("country") == sid:
                    tot = cv.get("demand", 0.5) * p["domicileDefault"]  # domicile fallback (0.5 only if key absent)
                val = sev * sign * tot
                if abs(val) >= p["minSeed"]:
                    add(tk, val)
        elif typ == "commodity":
            for e in _macro.get("exposureEdges", []):
                if e.get("to") != sid:
                    continue
                if e["rel"] == "PRODUCES":
                    add(e["from"], sign * sev * e.get("value", 0.0) * p["fProd"])
                elif e["rel"] == "CONSUMES":
                    add(e["from"], -sign * sev * e.get("value", 0.0) * p["fCons"])
        elif typ == "theme":
            for e in _macro.get("exposureEdges", []):
                if e.get("rel") == "EXPOSED_TO_THEME" and e.get("to") == sid:
                    add(e["from"], sign * sev * e.get("value", 0.0) * e.get("sign", 1) * p["fTheme"])
        elif typ == "condition":
            # direction comes from conditionAction + the CONSTRAINS sign (who is hurt/helped),
            # NOT the event-seed sign (that would double-count). TIGHTENS/ENACTS apply the
            # constraint as-is; LIFTS inverts it.
            flip = -1 if s.get("conditionAction") == "LIFTS" else 1
            for e in _macro.get("exposureEdges", []):
                if e.get("rel") == "CONSTRAINS" and e.get("from") == sid:
                    add(e["to"], flip * sev * e.get("value", 0.0) * e.get("sign", 1) * p["fCondition"])

    return [(tk, v) for tk, v in seeds.items() if abs(v) >= p["minSeed"] or tk in {h["ticker"] for h in event.get("hits", [])}]


def _regime(event):
    """contagion if macro/sector-wide; else substitution (rivals invert)."""
    cat = event.get("category", "")
    if cat in {"macro", "sector", "geopolitical", "fx_monetary", "commodity_shock", "thematic"}:
        return True
    hits = event.get("hits", [])
    secs = [COMPANIES[h["ticker"]]["sector"] for h in hits if h["ticker"] in COMPANIES]
    return any(secs.count(s) >= 2 for s in set(secs))


def _clamp(v):
    return max(-1.0, min(1.0, v))


def predicted_impacts(event, params=DEFAULT_PARAMS):
    seeds = seed_event(event, params)
    imp = cascade(seeds, params, contagion=_regime(event))
    return {tk: _clamp(v) for tk, v in imp.items()}  # bound |impact| <= 1


def predicted_signs(event, params=DEFAULT_PARAMS):
    imp = predicted_impacts(event, params)
    return {tk: (1 if v > 0 else -1) for tk, v in imp.items() if abs(v) >= params["minImpact"]}


if __name__ == "__main__":
    import sys
    eid = sys.argv[1] if len(sys.argv) > 1 else "evt_tsmc_quake_2024"
    ev = EVENTS[eid]
    print(f"{eid}  ({ev['date']}, {ev.get('category')})  regime={'contagion' if _regime(ev) else 'substitution'}")
    imp = predicted_impacts(ev)
    for tk, v in sorted(imp.items(), key=lambda kv: -abs(kv[1]))[:15]:
        print(f"  {tk:8} {v:+.3f}")
