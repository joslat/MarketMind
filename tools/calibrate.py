"""
calibrate.py v2 — tune the cascade weights on a TRAIN split, report OUT-OF-SAMPLE on TEST
vs naive baselines, honestly (the validation contract).

Ground truth = sign of the real abnormal return (data via build_golden_dataset.py -> golden.json,
keyed by event id, each name scored vs its LOCAL benchmark).

Honesty contract:
  • EVENT-TIME VALIDITY — a company only scores an event if it has a golden observation
    (i.e. it was listed and had price history); pre-listing names are never a "miss".
  • COHORTS — CORE = full-window tradables (stable n) carries the HEADLINE precision;
    FULL = whole graph used only for reach/coverage. Every number prints (cohort, n).
  • NON-HEADLINE — the real test: did the GRAPH (not the headline) call the companies nobody named?
  • BASELINES + ABLATIONS — headline-only, whole-sector; COMPETES-off and force-substitution.

Run:  python tools/build_golden_dataset.py   (first, builds golden.json)
      python tools/calibrate.py
"""
import json
import os
import itertools
from engine import COMPANIES, EVENTS, predicted_impacts, DEFAULT_PARAMS, cascade, seed_event, _regime

HERE = os.path.dirname(os.path.abspath(__file__))
golden = json.load(open(os.path.join(HERE, "golden.json"), encoding="utf-8"))

MOVE_THRESH = 0.004        # 0.4% abnormal move = a "clear" directional signal
CORE_CUTOFF = "2023-06-01"  # listedFrom on/before this => full-window CORE cohort

EVENT_IDS = [e["id"] for e in EVENTS.values()] if isinstance(EVENTS, dict) else []
EVENT_IDS = list(EVENTS.keys())
# deterministic split: every 3rd event (by file order) held out for TEST
TEST = [eid for i, eid in enumerate(EVENT_IDS) if i % 3 == 0]
TRAIN = [eid for eid in EVENT_IDS if eid not in TEST]

# CORE cohort = tradable names with full-window history (no/old listedFrom)
def _is_core(tk):
    c = COMPANIES.get(tk, {})
    if not c.get("tradable"):
        return False
    lf = c.get("listedFrom")
    return (lf is None) or (lf <= CORE_CUTOFF)
CORE = {tk for tk in COMPANIES if _is_core(tk)}


def ground_truth(eid):
    g = golden.get(eid, {})
    return {tk: (1 if d["abn"] > 0 else -1) for tk, d in g.items() if abs(d["abn"]) >= MOVE_THRESH}


def headline_set(eid):
    return {h["ticker"] for h in EVENTS[eid].get("hits", [])}


# ---- predictors: ticker -> predicted sign ----
def pred_graph(eid, params):
    imp = predicted_impacts(EVENTS[eid], params)
    return {tk: (1 if v > 0 else -1) for tk, v in imp.items() if abs(v) >= params["minImpact"]}


def pred_graph_noCompetes(eid, params):
    p = dict(params); p["fCmp"] = 0.0
    return pred_graph(eid, p)


def pred_graph_noRegime(eid, params):
    ev = EVENTS[eid]
    imp = cascade(seed_event(ev, params), params, contagion=False)  # force substitution
    return {tk: (1 if v > 0 else -1) for tk, v in imp.items() if abs(v) >= params["minImpact"]}


def pred_headline(eid, params=None):
    return {h["ticker"]: h["sign"] for h in EVENTS[eid].get("hits", [])}


def pred_sector(eid, params=None):
    """whole-sector baseline: every company in a directly-hit sector moves with that hit's sign."""
    hit_sectors = {}
    for h in EVENTS[eid].get("hits", []):
        sec = COMPANIES.get(h["ticker"], {}).get("sector")
        if sec:
            hit_sectors[sec] = h["sign"]
    return {tk: hit_sectors[meta["sector"]] for tk, meta in COMPANIES.items() if meta.get("sector") in hit_sectors}


def score(events, predictor, params, cohort=None, non_headline=False):
    correct = tot = 0
    for eid in events:
        gt = ground_truth(eid)
        hl = headline_set(eid)
        pred = predictor(eid, params)
        for tk, g in gt.items():
            if cohort is not None and tk not in cohort:
                continue
            if non_headline and tk in hl:
                continue
            if tk not in pred:        # graph made no confident call → not counted (precision, not recall)
                continue
            tot += 1
            if pred[tk] == g:
                correct += 1
    return correct, tot


def coverage(events, predictor, params, cohort=None, non_headline=False):
    """fraction of real clear movers the predictor made ANY confident call on."""
    reached = movers = 0
    for eid in events:
        gt = ground_truth(eid)
        hl = headline_set(eid)
        pred = predictor(eid, params)
        for tk in gt:
            if cohort is not None and tk not in cohort:
                continue
            if non_headline and tk in hl:
                continue
            movers += 1
            if tk in pred:
                reached += 1
    return reached, movers


def pct(c, t):
    return f"{100 * c / t:5.1f}% ({c}/{t})" if t else "  n/a (0)"


def line(name, events, predictor, params, cohort):
    c1, t1 = score(events, predictor, params, cohort, non_headline=False)
    c2, t2 = score(events, predictor, params, cohort, non_headline=True)
    cov, mv = coverage(events, predictor, params, cohort, non_headline=True)
    print(f"  {name:18} all={pct(c1, t1)}   non-headline={pct(c2, t2)}   nh-coverage={pct(cov, mv)}")


# ---- grid search on TRAIN: maximize non-headline confident precision on CORE ----
grid = {
    "fSupDown": [0.6, 0.7], "fSupUp": [0.3, 0.4], "fCmp": [0.35, 0.45, 0.55],
    "hopDecay": [0.6, 0.7], "minImpact": [0.03, 0.05],
}
best = None
for fsd, fsu, fc, hd, mi in itertools.product(*grid.values()):
    p = dict(DEFAULT_PARAMS, fSupDown=fsd, fSupUp=fsu, fCmp=fc, hopDecay=hd, minImpact=mi)
    a_nh, t_nh = score(TRAIN, pred_graph, p, CORE, non_headline=True)
    a_all, t_all = score(TRAIN, pred_graph, p, CORE, non_headline=False)
    key = (round(a_nh / t_nh, 4) if t_nh else 0, round(a_all / t_all, 4) if t_all else 0, t_nh)
    if best is None or key > best[0]:
        best = (key, p)
P = best[1]
json.dump(P, open(os.path.join(HERE, "calibrated_weights.json"), "w"), indent=1)

print(f"\nCohorts: CORE={len(CORE)} full-window tradables; FULL={sum(1 for c in COMPANIES.values() if c.get('tradable'))} tradables")
print(f"Split: TRAIN={len(TRAIN)} events, TEST={len(TEST)} events (held out)  ·  move-threshold |abn|>={MOVE_THRESH*100:.1f}%")
print("Calibrated weights:", {k: round(P[k], 3) for k in ("fSupDown", "fSupUp", "fPar", "fOwn", "fCmp", "hopDecay", "minImpact")})

for label, events in [("TRAIN", TRAIN), ("TEST (held out)", TEST)]:
    print(f"\n=== {label} — CORE cohort ===")
    line("graph (tuned)", events, pred_graph, P, CORE)
    line("headline-only", events, pred_headline, P, CORE)
    line("whole-sector", events, pred_sector, P, CORE)
    print(f"  -- ablations --")
    line("graph: COMPETES off", events, pred_graph_noCompetes, P, CORE)
    line("graph: force-substitution", events, pred_graph_noRegime, P, CORE)

# ---- regime breakdown: does the graph's edge live in firm-specific (substitution) events? ----
print("\n=== Regime breakdown (graph, non-headline, CORE) ===")
for label, events in [("ALL (TRAIN+TEST)", TRAIN + TEST), ("TEST only", TEST)]:
    subst = [e for e in events if not _regime(EVENTS[e])]
    cont = [e for e in events if _regime(EVENTS[e])]
    cs, ts = score(subst, pred_graph, P, CORE, non_headline=True)
    cc, tc = score(cont, pred_graph, P, CORE, non_headline=True)
    print(f"  {label:18} substitution={pct(cs, ts)} ({len(subst)} ev)   contagion={pct(cc, tc)} ({len(cont)} ev)")

print("\nThe number that matters: graph vs baselines on NON-HEADLINE movers, on TEST, CORE cohort.")
print("(precision = of the confident calls the graph made, how many were directionally right;")
print(" coverage = of the real movers, how many the graph flagged at all.)")
