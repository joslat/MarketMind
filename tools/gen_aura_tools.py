"""
gen_aura_tools.py — emit cypher/05-aura-tools.cypher: the 5 Cypher-Template tool bodies
ready to paste into the Neo4j Aura Agent console, with the calibrated weights INLINED.

WHY THIS EXISTS:
  An Aura Cypher-Template tool parameter is only name+type+description — there is NO default-value
  mechanism. So the ~17 calibrated weights CANNOT be tool parameters (as an earlier design wrongly assumed).
  They must be baked into the query body as literal constants. This generator reads cypher/02
  (the canonical engine) + tools/calibrated_weights.json (the canonical, parity-verified values)
  and inlines every $weight, leaving ONLY the genuine inputs ($newsId / $ticker / $tradableOnly).

  Single source of truth stays cypher/02 + calibrated_weights.json — never hand-edit cypher/05.

  python tools/gen_aura_tools.py            # writes cypher/05-aura-tools.cypher
  python tools/gen_aura_tools.py --check    # parse + report, do not write

Parity note: the INLINED-weight impact_cascade is what must be parity-tested on Aura
(tools/parity_neo4j.py passes the same calibrated values explicitly, so the inlined body is
numerically identical to the verified 330/330 run).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "cypher", "02-cascade-engine.cypher")
OUT = os.path.join(ROOT, "cypher", "05-aura-tools.cypher")
WEIGHTS = os.path.join(HERE, "calibrated_weights.json")

# tool id (as written in the `// TOOL N —` headers of cypher/02) -> registration metadata
TOOLS = {
    "1": {
        "name": "impact_cascade",
        "params": "newsId:string (required), tradableOnly:Boolean",
        "desc": ("THE headline tool. Given a newsId, returns the ranked signed exposure across the "
                 "dependency graph (winners/losers), each with its strongest path, hop distance, and "
                 "regime-aware direction. Use for ANY 'what does this event do to the market / who is "
                 "affected / blast radius' question. tradableOnly=true hides non-tradable conduits."),
    },
    "2": {
        "name": "company_dependency_map",
        "params": "ticker:string (required)",
        "desc": "A single company's suppliers, customers, competitors, and owners. Use to explain WHY a name is exposed.",
    },
    "3": {
        "name": "sector_exposure",
        "params": "newsId:string (required)",
        "desc": "How wide an event reaches, aggregated by sector (companiesReached + a sample). Use for 'how broad is this'.",
    },
    "4": {
        "name": "validate_history",
        "params": "newsId:string (required)",
        "desc": ("The honest backtest: realized abnormal returns per company for an event (ground truth). "
                 "Use when asked 'did this actually happen / how did it really move / is this validated'."),
    },
    "5": {
        "name": "active_conditions",
        "params": "ticker:string (required)",
        "desc": "The standing sanctions / export controls currently constraining a company. Use for 'what rules affect X'.",
    },
    "6": {
        "name": "find_event",
        "params": "query:string (required)",
        "desc": ("Resolve a free-text description or keywords (e.g. 'US chip export tightening') to the "
                 "matching news event(s), returning each newsId + headline + date. ALWAYS call this FIRST "
                 "to get a newsId when the user describes an event in words rather than giving an id — then "
                 "pass that newsId to impact_cascade / validate_history / sector_exposure."),
    },
}
GENUINE_PARAMS = {"newsId", "ticker", "tradableOnly", "query"}  # everything else must be inlined


def fmt(v):
    return "%g" % v  # 1.0->'1', 0.6->'0.6', 0.35->'0.35', 0.03->'0.03'


def extract_statements(text):
    """Walk cypher/02; return {tool_id: [statements]} for the `// TOOL N —` sections (comments stripped)."""
    tool_re = re.compile(r"^//\s*TOOL\s+(\S+)\s*[—-]")
    reset_re = re.compile(r"^//\s*(VIZ|NOTES)\b")
    tools, cur, buf = {}, None, []
    for line in text.splitlines():
        s = line.strip()
        m = tool_re.match(s)
        if m:
            cur = m.group(1)
            continue
        if reset_re.match(s):
            cur = None
            continue
        if s.startswith("//") or not s:
            continue
        buf.append(line)
        if s.endswith(";"):
            if cur is not None:
                tools.setdefault(cur, []).append("\n".join(buf).rstrip())
            buf = []
    return tools


def inline_weights(stmt, weights):
    for key, val in weights.items():
        stmt = re.sub(r"\$" + re.escape(key) + r"(?![A-Za-z0-9_])", fmt(val), stmt)
    # strip the trailing ';' (Aura tool body is a single statement, no terminator needed)
    return stmt.rstrip().rstrip(";").rstrip()


def remaining_params(stmt):
    return sorted(set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", stmt)))


def build():
    weights = json.load(open(WEIGHTS, encoding="utf-8"))
    text = open(SRC, encoding="utf-8").read()
    sections = extract_statements(text)

    problems, blocks = [], []
    for tid, meta in TOOLS.items():
        stmts = sections.get(tid)
        if not stmts:
            problems.append(f"TOOL {tid} ({meta['name']}): not found in cypher/02")
            continue
        if len(stmts) != 1:
            problems.append(f"TOOL {tid} ({meta['name']}): expected 1 statement, found {len(stmts)}")
        body = inline_weights(stmts[0], weights)
        left = [p for p in remaining_params(body) if p not in GENUINE_PARAMS]
        if left:
            problems.append(f"TOOL {tid} ({meta['name']}): un-inlined params remain: {left}")
        blocks.append((meta, body))

    return weights, blocks, problems


def render(weights, blocks):
    wl = ", ".join(f"{k}={fmt(v)}" for k, v in weights.items())
    L = ["// " + "=" * 71,
         "// MARKETMIND — AURA AGENT CYPHER-TEMPLATE TOOLS  (GENERATED by tools/gen_aura_tools.py)",
         "// DO NOT HAND-EDIT. Source of truth: cypher/02-cascade-engine.cypher + tools/calibrated_weights.json",
         "//",
         "// Paste each body below into a Cypher-Template tool in the Aura Agent console.",
         "// The calibrated weights are INLINED as literals because Aura tool params carry no default value;",
         "// expose ONLY the parameters listed per tool. All bodies are READ-ONLY (no MERGE/DELETE).",
         "//",
         f"// Inlined weights (from calibrated_weights.json): {wl}",
         "// " + "=" * 71,
         ""]
    for meta, body in blocks:
        L.append("// " + "─" * 67)
        L.append(f"// TOOL: {meta['name']}")
        L.append(f"// Parameters: {meta['params']}")
        L.append(f"// Description: {meta['desc']}")
        L.append("// " + "─" * 67)
        L.append(body + ";")
        L.append("")
    return "\n".join(L)


def main():
    weights, blocks, problems = build()
    for p in problems:
        print("  ! " + p)
    if problems:
        raise SystemExit("gen_aura_tools: refusing to write — fix the issues above.")
    print(f"parsed {len(blocks)} tools; all weights inlined; only {sorted(GENUINE_PARAMS)} remain as params.")
    if "--check" in sys.argv:
        print("--check: not writing.")
        return
    text = render(weights, blocks)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text + "\n")
    print(f"wrote {os.path.relpath(OUT, ROOT)}  ({text.count(chr(10)) + 1} lines)")


if __name__ == "__main__":
    main()
