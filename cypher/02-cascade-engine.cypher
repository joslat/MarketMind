// ═══════════════════════════════════════════════════════════════════════
// MARKETMIND — CASCADE ENGINE v3  (directional · macro-seeded · regime-aware)
//
// Mirrors tools/engine.py (the executable reference). The cascade contract:
//   PHASE 0  macro seeder — a country/commodity/theme/condition shock fans OUT
//            into companies by EXPOSURE (seed-only edges), becoming AFFECTS seeds.
//   PHASE 1  structural cascade over the FROZEN whitelist
//            SUPPLIES_TO|PARTNERS_WITH|OWNS|COMPETES_WITH (0..3 hops), with:
//              • DIRECTIONAL SUPPLIES_TO — supplier→customer fSupDown > customer→supplier fSupUp
//              • COMPETES_WITH sign-flip (−fCmp), SUPPRESSED in a contagion regime
//              • per-edge factor × weight × hopDecay, prune |impact| < minImpact (calibrated)
//
// Exposure / context relationships (REVENUE_FROM, OPERATES_IN, EXPOSED_TO_POLICY,
// PRODUCES, CONSUMES, EXPOSED_TO_THEME, CONSTRAINS, LOCATED_IN, IN_SECTOR) are
// SEED-ONLY — they are NEVER inside the variable-length cascade pattern.
//
// PARITY: tools/engine.py is authoritative and unit-testable offline. This Cypher is
// verified against it at DB-load time (the §10.5 top-15-tickers+signs parity test).
// ═══════════════════════════════════════════════════════════════════════

// CALIBRATED defaults below mirror tools/calibrated_weights.json (the parity-verified values, 330/330).
// Earlier this line carried the engine's pre-calibration DEFAULTS (fSupDown 0.70, fCmp 0.45, hopDecay 0.65);
// those diverge from the calibrated run, so a manual Browser run with them would NOT match engine.py.
// :params {newsId:'evt_tsmc_quake_2024', fSupDown:0.6, fSupUp:0.4, fPar:0.5, fOwn:0.55, fCmp:0.35, hopDecay:0.6, minImpact:0.03, fProd:0.6, fCons:0.6, fTheme:0.7, fCondition:0.8, minSeed:0.05, chOperations:1.0, chDemand:0.8, chCurrency:0.6, chPolicy:1.0, domicileDefault:0.4, tradableOnly:true}


// ───────────────────────────────────────────────────────────────────────
// TOOL 0 — PHASE-0 MACRO SEEDER  (turns a macro shock into per-company seeds)
//   Run these for macro-scope events, then feed the seeds into TOOL 1. The MAF/.NET
//   orchestrator unions these with the event's direct AFFECTS hits (engine.py does it
//   in one pass); for the Aura template they can MERGE derived `AFFECTS {derived:true}`.
// ───────────────────────────────────────────────────────────────────────

// 0a — COUNTRY: channelVector (operations/demand/policy) × exposure, summed per company
MATCH (n:NewsEvent {id:$newsId})-[hc:HITS_COUNTRY]->(k:Country)
MATCH (c:Company)-[ex:OPERATES_IN|REVENUE_FROM|EXPOSED_TO_POLICY]->(k)
WITH c, hc, CASE type(ex)
        WHEN 'OPERATES_IN'       THEN coalesce(n.cv_operations, 0.0) * ex.value * $chOperations
        WHEN 'REVENUE_FROM'      THEN coalesce(n.cv_demand, 0.0)     * ex.value * $chDemand
        WHEN 'EXPOSED_TO_POLICY' THEN coalesce(n.cv_policy, 0.0)     * ex.value * $chPolicy
      END AS contrib
WITH c.ticker AS ticker, hc.severity * hc.sign * sum(contrib) AS seed
WHERE abs(seed) >= $minSeed
RETURN ticker, round(seed * 1000) / 1000.0 AS seed, 'country' AS channel
ORDER BY abs(seed) DESC;

// 0b — COMMODITY: producers move WITH the price, consumers AGAINST it (input-cost inversion)
MATCH (n:NewsEvent {id:$newsId})-[ac:AFFECTS_COMMODITY]->(m:Commodity)
MATCH (c:Company)-[ex:PRODUCES|CONSUMES]->(m)
WITH c.ticker AS ticker,
     sum(ac.severity * ac.sign * ex.value *
         CASE type(ex) WHEN 'PRODUCES' THEN $fProd ELSE -$fCons END) AS seed
WHERE abs(seed) >= $minSeed
RETURN ticker, round(seed * 1000) / 1000.0 AS seed, 'commodity' AS channel
ORDER BY abs(seed) DESC;

// 0c — THEME: signed loading × theme shock (narrative / style-factor co-movement)
MATCH (n:NewsEvent {id:$newsId})-[at:AFFECTS_THEME]->(h:Theme)
MATCH (c:Company)-[ex:EXPOSED_TO_THEME]->(h)
WITH c.ticker AS ticker,
     sum(at.severity * at.sign * ex.value * coalesce(ex.sign, 1) * $fTheme) AS seed
WHERE abs(seed) >= $minSeed
RETURN ticker, round(seed * 1000) / 1000.0 AS seed, 'theme' AS channel
ORDER BY abs(seed) DESC;

// 0d — CONDITION: ENACTS/TIGHTENS apply the constraint as-is; LIFTS inverts it.
//      Direction = (lift?-1:+1) × CONSTRAINS.sign (who is hurt/helped); NOT the event sign.
MATCH (n:NewsEvent {id:$newsId})-[act:ENACTS|TIGHTENS|LIFTS]->(d:Condition)-[cn:CONSTRAINS]->(c:Company)
WITH c.ticker AS ticker,
     sum((CASE WHEN type(act) = 'LIFTS' THEN -1 ELSE 1 END)
         * act.severity * cn.value * coalesce(cn.sign, 1) * $fCondition) AS seed
WHERE abs(seed) >= $minSeed
RETURN ticker, round(seed * 1000) / 1000.0 AS seed, 'condition' AS channel
ORDER BY abs(seed) DESC;


// 0e — MATERIALIZE: aggregate ALL macro channels into derived AFFECTS seeds (the Phase-0 pre-pass).
//      Run this for macro/scope events BEFORE TOOL 1 so the cascade has company seeds to start from.
//      Idempotent; clean up afterwards with TOOL 0f. (Mirrors engine.py seed_event.)
MATCH (n:NewsEvent {id:$newsId})
CALL {
  WITH n  // country — operations / demand / currency / policy channels
  MATCH (n)-[hc:HITS_COUNTRY]->(k:Country)<-[ex:OPERATES_IN|REVENUE_FROM|EXPOSED_TO_POLICY]-(c:Company)
  RETURN c, hc.severity * hc.sign * (CASE type(ex)
      WHEN 'OPERATES_IN'       THEN coalesce(n.cv_operations,0.0) * ex.value * $chOperations
      WHEN 'REVENUE_FROM'      THEN coalesce(n.cv_demand,0.0)     * ex.value * $chDemand
                                  + coalesce(n.cv_currency,0.0)   * ex.value * $chCurrency
      WHEN 'EXPOSED_TO_POLICY' THEN coalesce(n.cv_policy,0.0)     * ex.value * $chPolicy END) AS seed
  UNION ALL
  WITH n  // country — domicile-default fallback for in-country names without curated exposure
  MATCH (n)-[hc:HITS_COUNTRY]->(k:Country)<-[:LOCATED_IN]-(c:Company)
  WHERE NOT (c)-[:OPERATES_IN|REVENUE_FROM|EXPOSED_TO_POLICY]->(k)
  RETURN c, hc.severity * hc.sign * coalesce(n.cv_demand,0.5) * $domicileDefault AS seed
  UNION ALL
  WITH n  // commodity — producers same sign, consumers opposite
  MATCH (n)-[ac:AFFECTS_COMMODITY]->(:Commodity)<-[ex:PRODUCES|CONSUMES]-(c:Company)
  RETURN c, ac.severity * ac.sign * ex.value * (CASE type(ex) WHEN 'PRODUCES' THEN $fProd ELSE -$fCons END) AS seed
  UNION ALL
  WITH n  // theme
  MATCH (n)-[at:AFFECTS_THEME]->(:Theme)<-[ex:EXPOSED_TO_THEME]-(c:Company)
  RETURN c, at.severity * at.sign * ex.value * coalesce(ex.sign,1) * $fTheme AS seed
  UNION ALL
  WITH n  // condition — ENACTS/TIGHTENS apply as-is, LIFTS inverts
  MATCH (n)-[act:ENACTS|TIGHTENS|LIFTS]->(:Condition)-[cn:CONSTRAINS]->(c:Company)
  RETURN c, (CASE WHEN type(act)='LIFTS' THEN -1 ELSE 1 END) * act.severity * cn.value * coalesce(cn.sign,1) * $fCondition AS seed
}
WITH n, c, sum(seed) AS s
WHERE abs(s) >= $minSeed AND NOT EXISTS { MATCH (n)-[:AFFECTS]->(c) }   // never overwrite a real hit
MERGE (n)-[a:AFFECTS {derived:true}]->(c)
  SET a.directImpact = abs(s), a.sign = (CASE WHEN s >= 0 THEN 1 ELSE -1 END)
RETURN count(*) AS derivedSeeds;

// 0f — CLEANUP: drop the derived seeds again (run after the cascade if you don't want to persist them)
MATCH (:NewsEvent {id:$newsId})-[a:AFFECTS {derived:true}]->(:Company) DELETE a;


// ───────────────────────────────────────────────────────────────────────
// TOOL 1 — IMPACT CASCADE  (merged · read-only · directional · regime-aware · AURA-READY)
//   ONE self-contained query: folds the direct AFFECTS hits + the Phase-0 macro seeds
//   (country/commodity/theme/condition) into a seed CTE — NO graph mutation — then runs
//   the directional 0..3-hop cascade. Supersedes the 0e→1→0f sequence; mirrors engine.py.
//   $tradableOnly=true  → agent answer (only price-scored companies; hides propagation-only conduits)
//   $tradableOnly=false → full set incl. non-tradable conduits (the UI/export parity set)
// ───────────────────────────────────────────────────────────────────────
MATCH (n:NewsEvent {id:$newsId})
OPTIONAL MATCH (n)-[:AFFECTS]->(hh:Company)
WITH n, collect(hh.sector) AS secs
WITH n, (n.category IN ['macro','sector','geopolitical','fx_monetary','commodity_shock','thematic']
         OR any(x IN secs WHERE size([y IN secs WHERE y = x]) >= 2)) AS contagion
CALL {
  WITH n  // direct company hits
  MATCH (n)-[a:AFFECTS]->(c:Company)
  RETURN c, a.directImpact * coalesce(a.sign, CASE WHEN n.sentiment < 0 THEN -1 ELSE 1 END) AS seed
  UNION ALL
  WITH n  // country: operations / demand / currency / policy
  MATCH (n)-[hc:HITS_COUNTRY]->(k:Country)<-[ex:OPERATES_IN|REVENUE_FROM|EXPOSED_TO_POLICY]-(c:Company)
  RETURN c, hc.severity * hc.sign * (CASE type(ex)
      WHEN 'OPERATES_IN'       THEN coalesce(n.cv_operations,0.0) * ex.value * $chOperations
      WHEN 'REVENUE_FROM'      THEN coalesce(n.cv_demand,0.0) * ex.value * $chDemand
                                  + coalesce(n.cv_currency,0.0) * ex.value * $chCurrency
      WHEN 'EXPOSED_TO_POLICY' THEN coalesce(n.cv_policy,0.0) * ex.value * coalesce(ex.sign,1) * $chPolicy END) AS seed
  UNION ALL
  WITH n  // country: domicile-default fallback (in-country names with no curated exposure)
  MATCH (n)-[hc:HITS_COUNTRY]->(k:Country)<-[:LOCATED_IN]-(c:Company)
  WHERE NOT (c)-[:OPERATES_IN|REVENUE_FROM|EXPOSED_TO_POLICY]->(k)
  RETURN c, hc.severity * hc.sign * coalesce(n.cv_demand,0.5) * $domicileDefault AS seed
  UNION ALL
  WITH n  // commodity: producers same sign, consumers opposite
  MATCH (n)-[ac:AFFECTS_COMMODITY]->(:Commodity)<-[ex:PRODUCES|CONSUMES]-(c:Company)
  RETURN c, ac.severity * ac.sign * ex.value * (CASE type(ex) WHEN 'PRODUCES' THEN $fProd ELSE -$fCons END) AS seed
  UNION ALL
  WITH n  // theme
  MATCH (n)-[at:AFFECTS_THEME]->(:Theme)<-[ex:EXPOSED_TO_THEME]-(c:Company)
  RETURN c, at.severity * at.sign * ex.value * coalesce(ex.sign,1) * $fTheme AS seed
  UNION ALL
  WITH n  // condition (ENACTS/TIGHTENS apply as-is; LIFTS inverts)
  MATCH (n)-[act:ENACTS|TIGHTENS|LIFTS]->(:Condition)-[cn:CONSTRAINS]->(c:Company)
  RETURN c, (CASE WHEN type(act)='LIFTS' THEN -1 ELSE 1 END) * act.severity * cn.value * coalesce(cn.sign,1) * $fCondition AS seed
}
WITH contagion, c AS c0, sum(seed) AS seed0
WHERE abs(seed0) >= $minSeed OR EXISTS { MATCH (:NewsEvent {id:$newsId})-[:AFFECTS]->(c0) }
MATCH p = (c0)-[rels:SUPPLIES_TO|PARTNERS_WITH|OWNS|COMPETES_WITH*0..3]-(c:Company)
WHERE NOT (c = c0 AND size(rels) > 0)   // engine.py visited-set: the seed node is not revisited via a loop
WITH c, contagion, seed0, size(rels) AS hops, rels, nodes(p) AS ns, [x IN nodes(p) | x.ticker] AS chain
WITH c, hops, chain,
     reduce(s = seed0, i IN range(0, size(rels) - 1) |
        s * (CASE type(rels[i])
               WHEN 'SUPPLIES_TO'   THEN (CASE WHEN startNode(rels[i]) = ns[i] THEN $fSupDown ELSE $fSupUp END)
               WHEN 'PARTNERS_WITH' THEN $fPar
               WHEN 'OWNS'          THEN $fOwn
               WHEN 'COMPETES_WITH' THEN (CASE WHEN contagion THEN 0.0 ELSE -$fCmp END)
               ELSE 0.4 END)
          * coalesce(rels[i].criticality, rels[i].strength, (rels[i].pct / 100.0), rels[i].overlap, 0.5)
          * $hopDecay
     ) AS pathImpact
WHERE abs(pathImpact) >= $minImpact
WITH c, pathImpact, hops, chain ORDER BY abs(pathImpact) DESC
WITH c, sum(pathImpact) AS impactRaw, min(hops) AS hop, head(collect(chain)) AS topChain
WITH c, hop, topChain,
     (CASE WHEN impactRaw > 1 THEN 1.0 WHEN impactRaw < -1 THEN -1.0 ELSE impactRaw END) AS impact  // clamp |impact|<=1
WHERE $tradableOnly = false OR coalesce(c.tradable, false) = true
RETURN c.ticker AS ticker, c.name AS name, coalesce(c.tradable, false) AS tradable,
       round(impact * 1000) / 1000.0 AS impact,
       (CASE WHEN impact >= 0 THEN 'gain' ELSE 'loss' END) AS direction,
       hop,
       reduce(s = '', i IN range(0, size(topChain) - 1) |
         s + topChain[i] + (CASE WHEN i < size(topChain) - 1 THEN ' → ' ELSE '' END)) AS path
ORDER BY abs(impact) DESC, ticker
LIMIT 25;


// ───────────────────────────────────────────────────────────────────────
// TOOL 2 — COMPANY DEPENDENCY MAP   :param ticker => 'TSMC'
// ───────────────────────────────────────────────────────────────────────
MATCH (c:Company {ticker:$ticker})
OPTIONAL MATCH (c)-[s:SUPPLIES_TO]->(cust:Company)
OPTIONAL MATCH (sup:Company)-[s2:SUPPLIES_TO]->(c)
OPTIONAL MATCH (c)-[cmp:COMPETES_WITH]-(peer:Company)
OPTIONAL MATCH (owner:Company)-[o:OWNS]->(c)
RETURN c.ticker AS ticker, c.name AS name, c.sector AS sector,
       collect(DISTINCT {to:cust.ticker,  criticality:s.criticality}) AS supplies_to,
       collect(DISTINCT {from:sup.ticker, criticality:s2.criticality}) AS supplied_by,
       collect(DISTINCT {peer:peer.ticker, overlap:cmp.overlap})        AS competes_with,
       collect(DISTINCT {owner:owner.ticker, pct:o.pct})                AS owned_by;


// ───────────────────────────────────────────────────────────────────────
// TOOL 3 — SECTOR EXPOSURE  (how wide does this event reach, by sector)
// ───────────────────────────────────────────────────────────────────────
MATCH (n:NewsEvent {id:$newsId})-[:AFFECTS]->(c0:Company)
MATCH (c0)-[:SUPPLIES_TO|PARTNERS_WITH|OWNS|COMPETES_WITH*0..2]-(c:Company)
RETURN c.sector AS sector,
       count(DISTINCT c) AS companiesReached,
       collect(DISTINCT c.ticker)[0..8] AS sample
ORDER BY companiesReached DESC;


// ───────────────────────────────────────────────────────────────────────
// TOOL 4 — VALIDATE AGAINST HISTORY  (golden-dataset ground truth)
// ───────────────────────────────────────────────────────────────────────
MATCH (n:NewsEvent {id:$newsId})-[:HAS_RECORD]->(ir:ImpactRecord)-[:FOR_COMPANY]->(c:Company)
RETURN c.ticker AS ticker, c.name AS name,
       ir.abnormalReturnPct AS actualAbnormalReturnPct,
       ir.window AS window, ir.filled AS filled
ORDER BY abs(coalesce(ir.abnormalReturnPct,0)) DESC;


// ───────────────────────────────────────────────────────────────────────
// TOOL 5 — ACTIVE CONDITIONS  (the standing state of the world for a company)
// ───────────────────────────────────────────────────────────────────────
MATCH (d:Condition {status:'active'})-[cn:CONSTRAINS]->(c:Company {ticker:$ticker})
RETURN d.id AS condition, d.kind AS kind, d.startDate AS since,
       cn.sign AS effectSign, cn.value AS severity, d.description AS description
ORDER BY abs(cn.value) DESC;


// ───────────────────────────────────────────────────────────────────────
// TOOL 6 — FIND EVENT  (resolve a free-text description to a newsId)   :param query => 'US chip export tightening'
//   The user usually describes an event in WORDS, not by id. Return the matching NewsEvent ids
//   (word-overlap scored, index-free, read-only) so the agent can then call impact_cascade /
//   validate_history / sector_exposure with a real newsId. This is the natural entry point.
// ───────────────────────────────────────────────────────────────────────
WITH [w IN split(toLower($query), ' ') WHERE size(w) >= 3] AS words
MATCH (n:NewsEvent)
WITH n, words, size([w IN words WHERE toLower(n.headline) CONTAINS w
                                      OR toLower(coalesce(n.category,'')) CONTAINS w
                                      OR toLower(n.id) CONTAINS w]) AS hits
WHERE hits > 0
RETURN n.id AS newsId, n.headline AS headline, n.date AS date, n.category AS category, hits
ORDER BY hits DESC, n.date DESC
LIMIT 8;


// ───────────────────────────────────────────────────────────────────────
// VIZ — propagation neighborhood for the web app (switch Browser to Graph view)
// ───────────────────────────────────────────────────────────────────────
MATCH (n:NewsEvent {id:$newsId})-[a:AFFECTS]->(c0:Company)
MATCH p = (c0)-[:SUPPLIES_TO|PARTNERS_WITH|OWNS|COMPETES_WITH*0..3]-(c:Company)
RETURN n, a, p;


// ═══════════════════════════════════════════════════════════════════════
// NOTES
// • Directionality: SUPPLIES_TO is stored supplier-[:SUPPLIES_TO]->customer. Inside the
//   reduce we read startNode(rels[i]) vs nodes(p)[i]: native direction = downstream
//   (supplier shock → customer, $fSupDown); reverse = upstream ($fSupUp < $fSupDown).
// • Macro seeding (TOOL 0) is one-way and damped by exposure; the macro/exposure edges are
//   never traversed company→company, so a Country/Commodity/Theme node cannot collapse
//   same-group pairs to 2 hops (locked principle).
// • Per-path vs per-hop pruning: engine.py prunes during DFS descent; this query prunes whole
//   paths then sums — magnitudes differ slightly, signs/top-ranks match (the parity metric).
// • Self-path artifact: a hit company reached by a short loop sums a minor self-term; acceptable
//   by default, removable with WHERE NOT (c = c0 AND hops > 0).
// ═══════════════════════════════════════════════════════════════════════
