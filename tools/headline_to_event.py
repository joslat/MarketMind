"""
headline_to_event.py — the LIVE path scaffold (U12): turn a real news HEADLINE into a MarketMind
event with an LLM, then run the deterministic cascade on it. This is the "on our own" backend;
the Aura agent is the other backend (its Text2Cypher + system prompt do the same mapping).

Pipeline:  headline --(Azure OpenAI chat, constrained to our vocabulary)--> event JSON
                    --(tools/engine.py, the SAME engine the graph/Cypher use)--> ranked exposure

The LLM ONLY classifies + names the directly-hit node(s); the GRAPH does everything past the headline.
Output is the same event schema as data/events.json, so it can be appended there and seeded permanently.

  python tools/headline_to_event.py --dry-run "Taiwan halts chip output after a major earthquake"
        # build + print the extraction prompt + allowed vocab, NO network
  python tools/headline_to_event.py "Nvidia warns of weak data-center demand for next quarter"
        # call the LLM, validate ids, run the cascade, print the blast radius
  python tools/headline_to_event.py --json "<headline>"     # print only the extracted event JSON

NOTE: this is the offline-friendly LAB preview of the extraction contract. The PRODUCT version of the
live agent is src/MarketMind.Agent (C#, Microsoft Agent Framework) — there the in-proc C# cascade engine
is exposed to the LLM as a `run_cascade` tool, in-process, no Python hop. Same contract, two backends
(plus the hosted Aura agent as the natural-language head).

HUMAN-ONLY prerequisites (not automated): Azure OpenAI CHAT deployment + key (a news API is the
last mile — pipe any real feed's headline string into this tool).
  AZURE_OPENAI_ENDPOINT · AZURE_OPENAI_API_KEY · AZURE_OPENAI_CHAT_DEPLOYMENT (e.g. gpt-4o)
  AZURE_OPENAI_API_VERSION (default 2024-08-01-preview)
"""
import json
import os
import sys
import datetime as dt
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")

CATEGORIES = ["supply_chain_disruption", "demand_surge", "regulatory", "earnings", "macro", "sector",
              "geopolitical", "election_policy", "fx_monetary", "commodity_shock", "thematic"]
SCOPES = ["company", "country", "commodity", "theme", "condition"]


def load(name, default=None):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def vocab():
    companies = load("companies.json")["companies"]
    macro = load("macro.json", {}) or {}
    return {
        "tickers": [c["ticker"] for c in companies],
        "countries": [c["code"] for c in macro.get("countries", [])],
        "commodities": [c["id"] for c in macro.get("commodities", [])],
        "themes": [t["id"] for t in macro.get("themes", [])],
        "conditions": [c["id"] for c in macro.get("conditions", [])],
    }


SCHEMA_HINT = """Return STRICT JSON (no prose) of shape:
{
  "id": "evt_<short_slug>",
  "headline": "<verbatim headline>",
  "date": "YYYY-MM-DD",                     // the reaction trading day; use today if unknown
  "category": one of CATEGORIES,
  "scope": one of SCOPES,                   // "company" if it names companies; else country/commodity/theme/condition
  "channelVector": {"operations":0..1,"demand":0..1,"currency":0..1,"policy":0..1},  // for macro scopes; omit for company
  "hits": [ {"ticker": <one of TICKERS>, "sign": -1|1, "severity": 0..1, "why": "<one line>"} ],
  "seeds":[ {"type":"country|commodity|theme|condition","id":<one of the macro ids>,"sign":-1|1,"severity":0..1,
             "why":"<one line>","conditionAction":"ENACTS|TIGHTENS|LIFTS (condition only)"} ]
}
Rules: use ONLY ids from the provided lists; never invent tickers. Name only the DIRECTLY-hit node(s) —
the graph propagates the rest. sign = +1 good for that name, -1 bad. severity = how hard the direct hit is."""


def build_messages(headline, v):
    sys_prompt = (
        "You are the extraction front-end for MarketMind, a reasoning+exposure engine over a company "
        "dependency graph. Map a financial news headline to a single structured event. You ONLY identify and "
        "classify; the graph does all downstream propagation. Be conservative and honest.\n\n"
        f"CATEGORIES = {CATEGORIES}\nSCOPES = {SCOPES}\n"
        f"TICKERS = {v['tickers']}\nCOUNTRIES = {v['countries']}\nCOMMODITIES = {v['commodities']}\n"
        f"THEMES = {v['themes']}\nCONDITIONS = {v['conditions']}\n\n" + SCHEMA_HINT
    )
    return [{"role": "system", "content": sys_prompt},
            {"role": "user", "content": f"Headline: {headline}"}]


def call_llm(messages):
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_API_KEY")
    deployment = os.environ.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
    version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    if not endpoint or not key or not deployment:
        sys.exit("Set AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY / AZURE_OPENAI_CHAT_DEPLOYMENT "
                 "(or use --dry-run to preview the prompt offline).")
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/chat/completions?api-version={version}"
    body = json.dumps({"messages": messages, "temperature": 0.1,
                       "response_format": {"type": "json_object"}}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "api-key": key})
    try:
        with urllib.request.urlopen(req, timeout=40) as resp:
            payload = json.load(resp)
    except urllib.error.HTTPError as ex:
        sys.exit(f"Azure OpenAI HTTP {ex.code}: {ex.read().decode('utf-8', 'ignore')[:300]}")
    return payload["choices"][0]["message"]["content"]


def validate(ev, v):
    allowed = set(v["tickers"]) | set(v["countries"]) | set(v["commodities"]) | set(v["themes"]) | set(v["conditions"])
    problems = []
    if ev.get("category") not in CATEGORIES:
        problems.append(f"bad category {ev.get('category')}")
    if ev.get("scope") not in SCOPES:
        problems.append(f"bad scope {ev.get('scope')}")
    for h in ev.get("hits", []) or []:
        if h.get("ticker") not in set(v["tickers"]):
            problems.append(f"unknown ticker {h.get('ticker')}")
    for s in ev.get("seeds", []) or []:
        if s.get("id") not in allowed:
            problems.append(f"unknown macro id {s.get('id')}")
    return problems


def main():
    args = [a for a in sys.argv[1:]]
    dry = "--dry-run" in args
    json_only = "--json" in args
    args = [a for a in args if not a.startswith("--")]
    if not args:
        sys.exit('usage: python tools/headline_to_event.py [--dry-run|--json] "<headline>"')
    headline = " ".join(args)
    v = vocab()
    messages = build_messages(headline, v)

    if dry:
        print("DRY RUN — extraction prompt (no network):\n")
        print(messages[0]["content"][:1200] + "\n...")
        print(f"\nUser: {messages[1]['content']}")
        print(f"\nvocab: {len(v['tickers'])} tickers · {len(v['countries'])} countries · "
              f"{len(v['commodities'])} commodities · {len(v['themes'])} themes · {len(v['conditions'])} conditions")
        return

    raw = call_llm(messages)
    try:
        ev = json.loads(raw)
    except json.JSONDecodeError:
        sys.exit(f"LLM did not return JSON:\n{raw[:400]}")
    ev.setdefault("date", dt.date.today().isoformat())
    ev["headline"] = headline

    problems = validate(ev, v)
    if problems:
        print("  ! validation problems (the LLM strayed from the vocabulary):", file=sys.stderr)
        for p in problems:
            print("    - " + p, file=sys.stderr)

    if json_only:
        print(json.dumps(ev, indent=1, ensure_ascii=False))
        return

    print(json.dumps(ev, indent=1, ensure_ascii=False))
    # run the SAME deterministic engine the graph/Cypher use
    try:
        from engine import predicted_impacts, DEFAULT_PARAMS, COMPANIES
    except Exception as ex:
        sys.exit(f"(extracted ok; engine import failed: {ex})")
    imp = predicted_impacts(ev, DEFAULT_PARAMS)
    ranked = sorted(imp.items(), key=lambda kv: -abs(kv[1]))
    print(f"\nBLAST RADIUS — {len(ranked)} companies in range (top 15):")
    for tk, val in ranked[:15]:
        c = COMPANIES.get(tk, {})
        arrow = "▲" if val >= 0 else "▼"
        tag = "" if c.get("tradable") else "  (conduit)"
        print(f"  {arrow} {tk:8} {val:+.3f}{tag}")
    print("\nAppend this event to data/events.json + rerun gen_seed.py to seed it permanently.")


if __name__ == "__main__":
    main()
