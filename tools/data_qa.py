"""
data_qa.py — gate the data/ source files against the §6.7 checklist.

Exit code 0 only if every REQUIRED (offline) check passes; non-zero otherwise.
Network/DB checks are tiered so the offline gate is runnable anywhere:

  python tools/data_qa.py                 # offline structural + count gate (REQUIRED)
  python tools/data_qa.py --online        # + yfinance row coverage (needs yfinance, network)
  python tools/data_qa.py --neo4j         # + load generated seed on Neo4j (needs neo4j driver + a DB)
  python tools/data_qa.py --all           # everything

§6.7 checklist coverage:
  [REQUIRED] every edge/event ticker exists · no dup tickers · no self-edges · weights in range
  [REQUIRED] each event date is a trading day
  [REQUIRED] >=12 events, >=45 companies, >=75 edges, all 4 inter-company rel types
  [online]   golden.json has the directly-hit company (needs rebuilt golden.json)
  [online]   every tradable company returns >=250 yfinance rows (2023-09..2024-12)
  [neo4j]    gen_seed.py output loads with zero Cypher errors on a clean DB
"""
import json
import os
import sys
import datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

# §6.2 base 7 sectors + user-requested extensions (energy = power/utilities/grid/fuel;
# healthcare = medtech/genomics/pharma) so the cascade can reach related macro channels.
SECTORS = {"semis", "cloud", "ai", "internet", "hardware", "automotive", "finance",
           "energy", "healthcare", "materials"}
CATEGORIES = {"supply_chain_disruption", "demand_surge", "regulatory", "earnings", "macro", "sector",
              # macro/exogenous categories
              "geopolitical", "election_policy", "fx_monetary", "commodity_shock", "thematic"}
TYPE_RANGE = {  # weight property bounds per relationship type
    "SUPPLIES_TO": (0.0, 1.0),
    "PARTNERS_WITH": (0.0, 1.0),
    "OWNS": (0.0, 100.0),
    "COMPETES_WITH": (0.0, 1.0),
}
INTER_COMPANY_TYPES = set(TYPE_RANGE)

# macro/exposure edges (seed-only; NEVER in the cascade whitelist). value bounds per rel.
MACRO_REL_RANGE = {
    "REVENUE_FROM": (0.0, 1.0), "OPERATES_IN": (0.0, 1.0), "EXPOSED_TO_POLICY": (-1.0, 1.0),
    "PRODUCES": (0.0, 1.0), "CONSUMES": (0.0, 1.0), "EXPOSED_TO_THEME": (0.0, 1.0),
    "CONSTRAINS": (0.0, 1.0),
}

# NYSE full-day closures 2024 (weekday holidays) — used for the trading-day check.
NYSE_HOLIDAYS_2024 = {
    "2024-01-01", "2024-01-15", "2024-02-19", "2024-03-29", "2024-05-27",
    "2024-06-19", "2024-07-04", "2024-09-02", "2024-11-28", "2024-12-25",
}

PRICE_START, PRICE_END = "2023-09-01", "2024-12-31"
MIN_ROWS = 250
# priceTickers that legitimately listed/spun-off INSIDE the price window, so thin
# history is expected, not a data error (warn, don't fail). They are still scoreable
# for events after their listing date.
RECENT_LISTINGS = {"GEV", "TEM", "285A.T", "SNDK"}  # GE Vernova (Apr'24), Tempus (Jun'24), Kioxia (Dec'24), SanDisk (Feb'25)

# ── result accumulation ──────────────────────────────────────────────────
PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results = []  # (tier, status, name, detail)


def record(tier, status, name, detail=""):
    results.append((tier, status, name, detail))
    glyph = {PASS: "[ OK ]", FAIL: "[FAIL]", SKIP: "[skip]"}[status]
    line = f"  {glyph} {name}"
    if detail:
        line += f" — {detail}"
    print(line)


def load(name):
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


# ── REQUIRED offline checks ──────────────────────────────────────────────
def check_companies(companies):
    tickers = [c["ticker"] for c in companies]
    dups = sorted({t for t in tickers if tickers.count(t) > 1})
    record("required", FAIL if dups else PASS, "no duplicate company tickers",
           f"dups: {dups}" if dups else f"{len(tickers)} unique")

    bad_sector = [c["ticker"] for c in companies if c.get("sector") not in SECTORS]
    record("required", FAIL if bad_sector else PASS, f"every sector in the {len(SECTORS)}-sector enum",
           f"bad: {bad_sector}" if bad_sector else "ok")

    bad_country = [c["ticker"] for c in companies
                   if not (isinstance(c.get("country"), str) and len(c["country"]) == 2 and c["country"].isupper())]
    record("required", FAIL if bad_country else PASS, "country is ISO-3166 alpha-2",
           f"bad: {bad_country}" if bad_country else "ok")

    # tradable companies must have a priceTicker + a benchmark; non-tradable must not be price-scored
    bad_trade = []
    for c in companies:
        if c.get("tradable"):
            if not c.get("priceTicker") or not c.get("benchmark"):
                bad_trade.append(c["ticker"] + " (missing priceTicker/benchmark)")
        else:
            if c.get("benchmark") is not None:
                bad_trade.append(c["ticker"] + " (non-tradable should not have a benchmark)")
    record("required", FAIL if bad_trade else PASS, "tradable<->priceTicker/benchmark consistent",
           "; ".join(bad_trade) if bad_trade else "ok")
    return set(tickers)


def check_edges(edges, tickers):
    missing = sorted({e["from"] for e in edges if e["from"] not in tickers}
                     | {e["to"] for e in edges if e["to"] not in tickers})
    record("required", FAIL if missing else PASS, "every edge ticker exists in companies",
           f"missing: {missing}" if missing else f"{len(edges)} edges")

    self_loops = [f"{e['from']}-{e['type']}-{e['to']}" for e in edges if e["from"] == e["to"]]
    record("required", FAIL if self_loops else PASS, "no self-edges",
           f"{self_loops}" if self_loops else "ok")

    bad_type = sorted({e["type"] for e in edges if e["type"] not in INTER_COMPANY_TYPES})
    record("required", FAIL if bad_type else PASS, "every edge type is a known relationship",
           f"bad: {bad_type}" if bad_type else "ok")

    out_of_range = []
    for e in edges:
        lo, hi = TYPE_RANGE.get(e["type"], (None, None))
        if lo is None:
            continue
        w = e.get("weight")
        if not isinstance(w, (int, float)) or not (lo <= w <= hi):
            out_of_range.append(f"{e['from']}-{e['type']}-{e['to']}={w}")
    record("required", FAIL if out_of_range else PASS, "edge weights in range for their type",
           "; ".join(out_of_range) if out_of_range else "ok")

    # exact duplicate (from,type,to); plus reverse duplicate for the undirected COMPETES_WITH
    directed_seen, dups = set(), []
    cmp_pairs, cmp_dups = set(), []
    for e in edges:
        key = (e["from"], e["type"], e["to"])
        if key in directed_seen:
            dups.append("-".join(key))
        directed_seen.add(key)
        if e["type"] == "COMPETES_WITH":
            pair = frozenset((e["from"], e["to"]))
            if pair in cmp_pairs:
                cmp_dups.append(f"{e['from']}~{e['to']}")
            cmp_pairs.add(pair)
    record("required", FAIL if dups else PASS, "no duplicate directed edges",
           f"{dups}" if dups else "ok")
    record("required", FAIL if cmp_dups else PASS, "no reverse-duplicate COMPETES_WITH pairs",
           f"{cmp_dups}" if cmp_dups else "ok")

    present_types = {e["type"] for e in edges}
    missing_types = sorted(INTER_COMPANY_TYPES - present_types)
    record("required", FAIL if missing_types else PASS, "all 4 inter-company rel types present",
           f"missing: {missing_types}" if missing_types else "SUPPLIES_TO/PARTNERS_WITH/OWNS/COMPETES_WITH")


def is_trading_day(date_str):
    try:
        d = dt.date.fromisoformat(date_str)
    except ValueError:
        return False, "not ISO yyyy-mm-dd"
    if d.weekday() >= 5:
        return False, "weekend"
    if date_str in NYSE_HOLIDAYS_2024:
        return False, "NYSE holiday"
    return True, "weekday"


def check_events(events, tickers):
    ids = [ev["id"] for ev in events]
    dup_ids = sorted({i for i in ids if ids.count(i) > 1})
    record("required", FAIL if dup_ids else PASS, "no duplicate event ids",
           f"{dup_ids}" if dup_ids else f"{len(ids)} unique")

    bad_cat = [ev["id"] for ev in events if ev.get("category") not in CATEGORIES]
    record("required", FAIL if bad_cat else PASS, "every event category in enum",
           f"{bad_cat}" if bad_cat else "ok")

    not_trading = []
    for ev in events:
        ok, why = is_trading_day(ev.get("date", ""))
        if not ok:
            not_trading.append(f"{ev['id']}({ev.get('date')}:{why})")
    record("required", FAIL if not_trading else PASS, "each event date is a trading day",
           "; ".join(not_trading) if not_trading else "ok")

    bad_hits = []
    for ev in events:
        hits = ev.get("hits") or []
        if not hits and not (ev.get("seeds") or []):
            bad_hits.append(f"{ev['id']}: no company hits and no macro seeds")
        for h in hits:
            if h.get("ticker") not in tickers:
                bad_hits.append(f"{ev['id']}: ticker {h.get('ticker')} missing")
            if h.get("sign") not in (-1, 1):
                bad_hits.append(f"{ev['id']}: bad sign {h.get('sign')}")
            sev = h.get("severity")
            if not isinstance(sev, (int, float)) or not (0.0 <= sev <= 1.0):
                bad_hits.append(f"{ev['id']}: bad severity {sev}")
            if not h.get("why"):
                bad_hits.append(f"{ev['id']}: missing why for {h.get('ticker')}")
    record("required", FAIL if bad_hits else PASS, "event hits valid (ticker/sign/severity/why)",
           "; ".join(bad_hits) if bad_hits else "ok")


def check_macro(events, tickers):
    """Validate data/macro.json (seed-only layer) + event macro-seed references."""
    path = os.path.join(DATA, "macro.json")
    if not os.path.exists(path):
        record("required", SKIP, "macro layer (macro.json)", "absent — structural-only graph")
        return
    m = json.load(open(path, encoding="utf-8"))
    country_codes = {c["code"] for c in m.get("countries", [])}
    commodity_ids = {c["id"] for c in m.get("commodities", [])}
    theme_ids = {t["id"] for t in m.get("themes", [])}
    condition_ids = {c["id"] for c in m.get("conditions", [])}
    node_ids = country_codes | commodity_ids | theme_ids | condition_ids
    COUNTRY_RELS = {"REVENUE_FROM", "OPERATES_IN", "EXPOSED_TO_POLICY"}

    bad = []
    for e in m.get("exposureEdges", []):
        rel, a, b, v = e.get("rel"), e.get("from"), e.get("to"), e.get("value")
        lo, hi = MACRO_REL_RANGE.get(rel, (None, None))
        if lo is None:
            bad.append(f"unknown rel {rel}"); continue
        if not isinstance(v, (int, float)) or not (lo <= v <= hi):
            bad.append(f"{a}-{rel}-{b}={v} out of [{lo},{hi}]")
        if rel == "CONSTRAINS":
            if a not in condition_ids: bad.append(f"CONSTRAINS from non-condition {a}")
            if b not in tickers: bad.append(f"CONSTRAINS to non-company {b}")
        elif rel in COUNTRY_RELS:
            if a not in tickers: bad.append(f"{rel} from non-company {a}")
            if b not in country_codes: bad.append(f"{rel} to non-country {b}")
        else:  # PRODUCES/CONSUMES -> commodity; EXPOSED_TO_THEME -> theme
            if a not in tickers: bad.append(f"{rel} from non-company {a}")
            target = commodity_ids if rel in ("PRODUCES", "CONSUMES") else theme_ids
            if b not in target: bad.append(f"{rel} to bad node {b}")
    record("required", FAIL if bad else PASS, "macro.json exposure edges valid",
           "; ".join(bad[:6]) if bad else f"{len(m.get('exposureEdges', []))} seed-only edges ok")

    # condition well-formedness
    bad_cond = [c.get("id") for c in m.get("conditions", [])
                if c.get("status") not in ("active", "lifted") or not c.get("startDate")]
    record("required", FAIL if bad_cond else PASS, "conditions well-formed",
           f"{bad_cond}" if bad_cond else f"{len(condition_ids)} conditions")

    # event macro-seed references resolve
    bad_seed = []
    for ev in events:
        for s in ev.get("seeds", []) or []:
            if s.get("id") not in node_ids:
                bad_seed.append(f"{ev['id']}->{s.get('id')}")
    record("required", FAIL if bad_seed else PASS, "event macro-seeds resolve to macro nodes",
           "; ".join(bad_seed) if bad_seed else "ok")


def check_counts(companies, edges, events):
    record("required", FAIL if len(companies) < 45 else PASS, ">=45 companies", f"{len(companies)}")
    record("required", FAIL if len(edges) < 75 else PASS, ">=75 edges", f"{len(edges)}")
    record("required", FAIL if len(events) < 12 else PASS, ">=12 events", f"{len(events)}")


# ── online: golden.json directly-hit coverage ────────────────────────────
def check_golden(events, tradable):
    path = os.path.join(HERE, "golden.json")
    if not os.path.exists(path):
        record("online", SKIP, "golden.json directly-hit coverage",
               "golden.json absent — run build_golden_dataset.py")
        return
    golden = json.load(open(path, encoding="utf-8"))  # keyed by event id (long)
    missing = []
    n_ok = 0
    for ev in events:
        entry = golden.get(ev["id"])
        if not entry:
            missing.append(f"{ev['id']}:no-entry")
            continue
        # only tradable directly-hit tickers are expected in the price-scored set
        gaps = [h["ticker"] for h in ev["hits"] if h["ticker"] in tradable and h["ticker"] not in entry]
        if gaps:
            missing.append(f"{ev['id']}:{gaps}")
        else:
            n_ok += 1
    record("online", FAIL if missing else PASS, "golden.json has directly-hit companies",
           "; ".join(missing) if missing else f"all {n_ok} events: every tradable directly-hit company scored")


# ── online: yfinance row coverage ────────────────────────────────────────
def check_yfinance(companies, enabled):
    if not enabled:
        record("online", SKIP, "tradable companies have >=250 yfinance rows", "pass --online to run")
        return
    try:
        import yfinance as yf
    except ImportError:
        record("online", SKIP, "tradable companies have >=250 yfinance rows",
               "yfinance not installed (pip install yfinance)")
        return
    pts = sorted({c["priceTicker"] for c in companies if c.get("tradable") and c.get("priceTicker")})
    print(f"    downloading {len(pts)} symbols {PRICE_START}..{PRICE_END} ...")
    raw = yf.download(pts, start=PRICE_START, end=PRICE_END, auto_adjust=True, progress=False)
    close = raw["Close"] if "Close" in raw else raw
    thin, young = [], []
    for sym in pts:
        try:
            n = int(close[sym].dropna().shape[0]) if len(pts) > 1 else int(close.dropna().shape[0])
        except Exception:
            n = 0
        if n < MIN_ROWS:
            # a known recent listing is expected-thin even at 0 rows (listed after the window);
            # a NON-recent symbol returning 0 is a genuinely bad/dead ticker → hard fail.
            (young if sym in RECENT_LISTINGS else thin).append(f"{sym}={n}")
    detail = f"all {len(pts)} symbols ok" if not thin else "; ".join(thin)
    if young:
        detail += f"  (recent listings, expected-thin: {'; '.join(young)})"
    record("online", FAIL if thin else PASS, "tradable companies have >=250 yfinance rows", detail)


# ── neo4j: load the generated seed ───────────────────────────────────────
def check_neo4j(enabled):
    if not enabled:
        record("neo4j", SKIP, "generated seed loads with zero Cypher errors",
               "pass --neo4j (needs neo4j driver + NEO4J_URI/USER/PASSWORD) or load it manually")
        return
    seed = os.path.join(ROOT, "cypher", "01-marketmind-seed.cypher")
    if not os.path.exists(seed):
        record("neo4j", FAIL, "generated seed loads with zero Cypher errors",
               "cypher/01-marketmind-seed.cypher missing — run gen_seed.py first")
        return
    try:
        from neo4j import GraphDatabase
    except ImportError:
        record("neo4j", SKIP, "generated seed loads with zero Cypher errors",
               "neo4j driver not installed (pip install neo4j)")
        return
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD")
    if not pw:
        record("neo4j", SKIP, "generated seed loads with zero Cypher errors", "set NEO4J_PASSWORD")
        return
    text = open(seed, encoding="utf-8").read()
    stmts = [s.strip() for s in text.split(";") if s.strip() and not all(
        ln.strip().startswith("//") or not ln.strip() for ln in s.splitlines())]
    try:
        drv = GraphDatabase.driver(uri, auth=(user, pw))
        with drv.session() as sess:
            for s in stmts:
                sess.run(s)
        drv.close()
        record("neo4j", PASS, "generated seed loads with zero Cypher errors", f"{len(stmts)} statements")
    except Exception as ex:
        record("neo4j", FAIL, "generated seed loads with zero Cypher errors", str(ex).splitlines()[0])


def main():
    argv = set(sys.argv[1:])
    online = "--online" in argv or "--all" in argv
    neo4j = "--neo4j" in argv or "--all" in argv

    companies = load("companies.json")["companies"]
    edges = load("edges.json")["edges"]
    events = load("events.json")["events"]

    print("REQUIRED — structural & counts (offline)")
    tickers = check_companies(companies)
    check_edges(edges, tickers)
    check_events(events, tickers)
    check_macro(events, tickers)
    check_counts(companies, edges, events)

    print("\nEXTENDED — price/DB tiers")
    check_golden(events, {c["ticker"] for c in companies if c.get("tradable")})
    check_yfinance(companies, online)
    check_neo4j(neo4j)

    req_fail = [r for r in results if r[0] == "required" and r[1] == FAIL]
    ext_fail = [r for r in results if r[0] != "required" and r[1] == FAIL]
    n_pass = sum(1 for r in results if r[1] == PASS)
    n_skip = sum(1 for r in results if r[1] == SKIP)

    print("\n" + "=" * 60)
    print(f"PASS={n_pass}  FAIL={len(req_fail) + len(ext_fail)}  SKIP={n_skip}")
    if req_fail:
        print("RED — required checks failed:")
        for _, _, name, detail in req_fail:
            print(f"   - {name}: {detail}")
        sys.exit(1)
    if ext_fail:
        print("RED — an enabled extended check failed:")
        for _, _, name, detail in ext_fail:
            print(f"   - {name}: {detail}")
        sys.exit(1)
    print("GREEN — required (offline) gate passed.")
    if n_skip:
        print(f"       ({n_skip} extended checks skipped — run --online / --neo4j for the full §6.7 gate.)")
    sys.exit(0)


if __name__ == "__main__":
    main()
