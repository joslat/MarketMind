"""
parity_neo4j.py — §10.5 parity gate for the SHIPPED merged read-only impact_cascade
(cypher/02 TOOL 1): one self-contained query (Phase-0 seeds folded into a CTE, no graph
mutation) must agree with tools/engine.py on the top-15 tickers + signs, on EVERY event
incl. macro. This is the exact query an Aura Cypher-Template tool registers.

Run (Neo4j container 'marketmind-neo4j' loaded):  python tools/parity_neo4j.py
"""
import json
import os
import subprocess
import sys
from engine import EVENTS, predicted_impacts, DEFAULT_PARAMS

HERE = os.path.dirname(os.path.abspath(__file__))
P = dict(DEFAULT_PARAMS)
cw = os.path.join(HERE, "calibrated_weights.json")
if os.path.exists(cw):
    P.update(json.load(open(cw, encoding="utf-8")))
P["tradableOnly"] = False  # compare the FULL set (engine.py returns all reached, incl. non-tradable conduits)

# the merged read-only cascade, trimmed to RETURN ticker + impact (clean parsing)
TOOL1 = """
MATCH (n:NewsEvent {id:$newsId})
OPTIONAL MATCH (n)-[:AFFECTS]->(hh:Company)
WITH n, collect(hh.sector) AS secs
WITH n, (n.category IN ['macro','sector','geopolitical','fx_monetary','commodity_shock','thematic']
         OR any(x IN secs WHERE size([y IN secs WHERE y=x])>=2)) AS contagion
CALL {
  WITH n
  MATCH (n)-[a:AFFECTS]->(c:Company)
  RETURN c, a.directImpact*coalesce(a.sign, CASE WHEN n.sentiment<0 THEN -1 ELSE 1 END) AS seed
  UNION ALL
  WITH n
  MATCH (n)-[hc:HITS_COUNTRY]->(k:Country)<-[ex:OPERATES_IN|REVENUE_FROM|EXPOSED_TO_POLICY]-(c:Company)
  RETURN c, hc.severity*hc.sign*(CASE type(ex)
     WHEN 'OPERATES_IN' THEN coalesce(n.cv_operations,0.0)*ex.value*$chOperations
     WHEN 'REVENUE_FROM' THEN coalesce(n.cv_demand,0.0)*ex.value*$chDemand + coalesce(n.cv_currency,0.0)*ex.value*$chCurrency
     WHEN 'EXPOSED_TO_POLICY' THEN coalesce(n.cv_policy,0.0)*ex.value*coalesce(ex.sign,1)*$chPolicy END) AS seed
  UNION ALL
  WITH n
  MATCH (n)-[hc:HITS_COUNTRY]->(k:Country)<-[:LOCATED_IN]-(c:Company)
  WHERE NOT (c)-[:OPERATES_IN|REVENUE_FROM|EXPOSED_TO_POLICY]->(k)
  RETURN c, hc.severity*hc.sign*coalesce(n.cv_demand,0.5)*$domicileDefault AS seed
  UNION ALL
  WITH n
  MATCH (n)-[ac:AFFECTS_COMMODITY]->(:Commodity)<-[ex:PRODUCES|CONSUMES]-(c:Company)
  RETURN c, ac.severity*ac.sign*ex.value*(CASE type(ex) WHEN 'PRODUCES' THEN $fProd ELSE -$fCons END) AS seed
  UNION ALL
  WITH n
  MATCH (n)-[at:AFFECTS_THEME]->(:Theme)<-[ex:EXPOSED_TO_THEME]-(c:Company)
  RETURN c, at.severity*at.sign*ex.value*coalesce(ex.sign,1)*$fTheme AS seed
  UNION ALL
  WITH n
  MATCH (n)-[act:ENACTS|TIGHTENS|LIFTS]->(:Condition)-[cn:CONSTRAINS]->(c:Company)
  RETURN c, (CASE WHEN type(act)='LIFTS' THEN -1 ELSE 1 END)*act.severity*cn.value*coalesce(cn.sign,1)*$fCondition AS seed
}
WITH contagion, c AS c0, sum(seed) AS seed0
WHERE abs(seed0) >= $minSeed OR EXISTS { MATCH (:NewsEvent {id:$newsId})-[:AFFECTS]->(c0) }
MATCH p = (c0)-[rels:SUPPLIES_TO|PARTNERS_WITH|OWNS|COMPETES_WITH*0..3]-(c:Company)
WHERE NOT (c = c0 AND size(rels) > 0)
WITH c, contagion, seed0, size(rels) AS hops, rels, nodes(p) AS ns
WITH c, reduce(s=seed0, i IN range(0,size(rels)-1) | s*(CASE type(rels[i])
        WHEN 'SUPPLIES_TO' THEN (CASE WHEN startNode(rels[i])=ns[i] THEN $fSupDown ELSE $fSupUp END)
        WHEN 'PARTNERS_WITH' THEN $fPar WHEN 'OWNS' THEN $fOwn
        WHEN 'COMPETES_WITH' THEN (CASE WHEN contagion THEN 0.0 ELSE -$fCmp END) ELSE 0.4 END)
      * coalesce(rels[i].criticality, rels[i].strength, (rels[i].pct/100.0), rels[i].overlap, 0.5)*$hopDecay) AS pathImpact
WHERE abs(pathImpact) >= $minImpact
WITH c, sum(pathImpact) AS impactRaw
WITH c, (CASE WHEN impactRaw>1 THEN 1.0 WHEN impactRaw<-1 THEN -1.0 ELSE impactRaw END) AS impact
WHERE $tradableOnly = false OR coalesce(c.tradable,false)=true
RETURN c.ticker AS ticker, round(impact*1000)/1000.0 AS impact ORDER BY abs(impact) DESC;
"""

PKEYS = ["fSupDown", "fSupUp", "fPar", "fOwn", "fCmp", "hopDecay", "minImpact",
         "fProd", "fCons", "fTheme", "fCondition", "minSeed",
         "chOperations", "chDemand", "chCurrency", "chPolicy", "domicileDefault", "tradableOnly"]


def _fmt(v):
    return ("true" if v else "false") if isinstance(v, bool) else str(v)


def _shell_cmd():
    """Build the cypher-shell invocation.

    Local dev (default): exec cypher-shell inside the 'marketmind-neo4j' Docker container.
    Aura/remote parity-gate: set NEO4J_URI=neo4j+s://<dbid>.databases.neo4j.io (+ NEO4J_USER/NEO4J_PASSWORD)
    and this dials the remote. By default it still uses the container's cypher-shell as the *client* (it is
    guaranteed present and can connect out to Aura); set NEO4J_LOCAL_SHELL=1 to use a cypher-shell already on
    your PATH instead. This is the §10.5 gate the Aura walkthrough runs against the live instance.
    """
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD") or os.environ.get("MM_LOCAL_NEO4J_PASSWORD") or "neo4j_local_dev"
    uri = os.environ.get("NEO4J_URI")
    if uri:
        client = [] if os.environ.get("NEO4J_LOCAL_SHELL") else ["docker", "exec", "-i", "marketmind-neo4j"]
        return client + ["cypher-shell", "-a", uri, "-u", user, "-p", pw]
    return ["docker", "exec", "-i", "marketmind-neo4j", "cypher-shell", "-u", user, "-p", pw]


def run_cypher(news_id):
    args = _shell_cmd() + ["--format", "plain", "-P", f"newsId => '{news_id}'"]
    for k in PKEYS:
        args += ["-P", f"{k} => {_fmt(P[k])}"]
    out = subprocess.run(args, input=TOOL1, capture_output=True, text=True)
    res = {}
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("ticker") or "," not in line:
            continue
        tk, _, val = line.partition(",")
        try:
            res[tk.strip().strip('"')] = float(val)
        except ValueError:
            pass
    if not res and out.stderr.strip():
        print("   cypher error:", out.stderr.splitlines()[-1][:140])
    return res


def top15_signs(impacts):
    return {tk: (1 if v >= 0 else -1) for tk, v in sorted(impacts.items(), key=lambda kv: -abs(kv[1]))[:15]}


events = list(EVENTS.keys())
target = os.environ.get("NEO4J_URI", "<local docker: marketmind-neo4j>")
print(f"§10.5 parity — merged read-only impact_cascade (Neo4j) vs engine.py, {len(events)} events")
print(f"  target: {target}\n")
exact = signs_total = signs_ok = 0
empty_cy = 0   # events where Neo4j returned NOTHING but engine.py expected rows (load/connection failure)
for eid in events:
    cy = top15_signs(run_cypher(eid))
    py = top15_signs(predicted_impacts(EVENTS[eid], P))
    if not cy and py:
        empty_cy += 1
    common = set(cy) & set(py)
    ok = sum(1 for t in common if cy[t] == py[t])
    signs_total += len(common)
    signs_ok += ok
    same = set(cy) == set(py)
    if same and ok == len(common):
        exact += 1
    flag = "OK  " if same and ok == len(common) else ("EMPTY" if not cy and py else "DIFF")
    extra = "" if same else f"  net-only={sorted(set(cy)-set(py))} py-only={sorted(set(py)-set(cy))}"
    print(f"  [{flag}] {eid:34} signs {ok}/{len(common)} agree{extra}")

covered = len(events) - empty_cy
# Real gate: zero sign disagreements AND every event actually returned Cypher rows (an empty result set
# must NOT read as PASS — that hid a "target not loaded / wrong creds" failure). signs_total>0 guards 0/0.
passed = signs_ok == signs_total and signs_total > 0 and empty_cy == 0
print(f"\nPARITY: signs {signs_ok}/{signs_total} agree ({100*signs_ok//max(1,signs_total)}%); "
      f"{exact}/{len(events)} identical top-15 set; {covered}/{len(events)} events returned Neo4j rows.")
if empty_cy:
    print(f"RESULT: FAIL — Neo4j returned NO rows for {empty_cy}/{len(events)} events. "
          f"Is the target loaded (cypher/01+03) and are the creds right? target={target}")
elif passed:
    print("RESULT: §10.5 PASS — shipped Cypher matches engine.py on every sign.")
else:
    print("RESULT: sign disagreements above — investigate (NOT expected).")
sys.exit(0 if passed else 1)   # non-zero on any sign mismatch OR empty/zero-coverage result
