"""
embed_events.py — populate NewsEvent.embedding for the `similar_events` Vector tool.

For every NewsEvent in data/events.json it builds a compact embed text
(headline + category + scope + the directly-hit tickers/sectors), calls Azure OpenAI
`text-embedding-3-small` (1536 dims), and writes the vector onto the Neo4j node via
`db.create.setNodeVectorProperty`. The vector index itself is created by cypher/04-embeddings.cypher
(run that FIRST). This is a STRETCH tool — the structural Cypher-Template tools are the must.

  python tools/embed_events.py --dry-run     # build + print embed texts, NO network/DB (offline-safe)
  python tools/embed_events.py --check        # report which env vars are set/missing, exit
  python tools/embed_events.py                # embed all events -> write to Neo4j (needs keys + DB)
  python tools/embed_events.py --cache-only    # write embeddings to tools/_embeddings.json, skip Neo4j

HUMAN-ONLY prerequisites (provisioning is not automated):
  Azure OpenAI:  AZURE_OPENAI_ENDPOINT   e.g. https://my-aoai.openai.azure.com
                 AZURE_OPENAI_API_KEY
                 AZURE_OPENAI_EMBED_DEPLOYMENT  (default: text-embedding-3-small)
                 AZURE_OPENAI_API_VERSION       (default: 2024-02-01)
  Neo4j (Local Docker OR Aura — same scripts):
                 NEO4J_URI  (default bolt://localhost:7687)  ·  NEO4J_USER (default neo4j)  ·  NEO4J_PASSWORD

The embedding text is deterministic, so a re-run with the same model reproduces the same vectors.
"""
import json
import os
import sys
import urllib.request
import urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
EMBED_DIMS = 1536  # must match cypher/04 vector.dimensions


def load(name):
    with open(os.path.join(DATA, name), "r", encoding="utf-8") as f:
        return json.load(f)


def embed_text(ev, companies):
    """headline + category + scope + the directly-hit tickers and their sectors."""
    by_ticker = {c["ticker"]: c for c in companies}
    hits = ev.get("hits") or []
    tickers = [h["ticker"] for h in hits]
    sectors = sorted({by_ticker[t]["sector"] for t in tickers if t in by_ticker})
    seed_ids = [s["id"] for s in (ev.get("seeds") or [])]
    parts = [
        ev["headline"],
        f"category: {ev.get('category')}",
        f"scope: {ev.get('scope', 'company')}",
    ]
    if tickers:
        parts.append("companies: " + ", ".join(tickers))
    if sectors:
        parts.append("sectors: " + ", ".join(sectors))
    if seed_ids:
        parts.append("macro: " + ", ".join(seed_ids))
    return " | ".join(parts)


# ── Azure OpenAI embeddings (direct REST — no SDK dependency) ────────────────
def azure_config():
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    key = os.environ.get("AZURE_OPENAI_API_KEY")
    deployment = os.environ.get("AZURE_OPENAI_EMBED_DEPLOYMENT", "text-embedding-3-small")
    version = os.environ.get("AZURE_OPENAI_API_VERSION", "2024-02-01")
    return endpoint, key, deployment, version


def embed_one(text, cfg):
    endpoint, key, deployment, version = cfg
    url = f"{endpoint.rstrip('/')}/openai/deployments/{deployment}/embeddings?api-version={version}"
    body = json.dumps({"input": text}).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST",
                                 headers={"Content-Type": "application/json", "api-key": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    vec = payload["data"][0]["embedding"]
    if len(vec) != EMBED_DIMS:
        raise SystemExit(f"embedding dim {len(vec)} != expected {EMBED_DIMS} — check the deployment model "
                         f"(cypher/04 indexes {EMBED_DIMS}-dim cosine).")
    return vec


# ── Neo4j write ──────────────────────────────────────────────────────────────
def write_neo4j(records):
    try:
        from neo4j import GraphDatabase
    except ImportError:
        sys.exit("neo4j driver not installed — run:  pip install neo4j  (or use --cache-only)")
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    pw = os.environ.get("NEO4J_PASSWORD")
    if not pw:
        sys.exit("set NEO4J_PASSWORD (the local dev password or your Aura instance password)")
    cy = ("MATCH (n:NewsEvent {id:$id}) "
          "CALL db.create.setNodeVectorProperty(n, 'embedding', $vec) RETURN n.id AS id")
    drv = GraphDatabase.driver(uri, auth=(user, pw))
    written = 0
    with drv.session() as sess:
        for eid, vec in records:
            res = sess.run(cy, id=eid, vec=vec).single()
            if res is None:
                print(f"    warn: {eid} not found in DB (load cypher/01 first) — skipped")
            else:
                written += 1
    drv.close()
    print(f"wrote {written}/{len(records)} embeddings to {uri}")


def main():
    argv = set(sys.argv[1:])
    dry_run = "--dry-run" in argv
    check = "--check" in argv
    cache_only = "--cache-only" in argv

    events = load("events.json")["events"]
    companies = load("companies.json")["companies"]
    texts = [(ev["id"], embed_text(ev, companies)) for ev in events]

    if check:
        endpoint, key, deployment, version = azure_config()
        print("Azure OpenAI:")
        print(f"  AZURE_OPENAI_ENDPOINT          {'set' if endpoint else 'MISSING'}")
        print(f"  AZURE_OPENAI_API_KEY           {'set' if key else 'MISSING'}")
        print(f"  AZURE_OPENAI_EMBED_DEPLOYMENT  {deployment}")
        print(f"  AZURE_OPENAI_API_VERSION       {version}")
        print("Neo4j:")
        print(f"  NEO4J_URI                      {os.environ.get('NEO4J_URI', 'bolt://localhost:7687')}")
        print(f"  NEO4J_USER                     {os.environ.get('NEO4J_USER', 'neo4j')}")
        print(f"  NEO4J_PASSWORD                 {'set' if os.environ.get('NEO4J_PASSWORD') else 'MISSING'}")
        print(f"\n{len(texts)} events ready to embed. Run --dry-run to preview the texts.")
        return

    if dry_run:
        print(f"DRY RUN — {len(texts)} embed texts (no network/DB):\n")
        for eid, t in texts:
            print(f"  {eid}\n      {t}\n")
        print(f"Each will be embedded to a {EMBED_DIMS}-dim vector (text-embedding-3-small). "
              f"Run cypher/04 first, then `python tools/embed_events.py` to write them.")
        return

    cfg = azure_config()
    if not cfg[0] or not cfg[1]:
        sys.exit("AZURE_OPENAI_ENDPOINT / AZURE_OPENAI_API_KEY not set — run --check, or --dry-run to preview offline.")

    print(f"Embedding {len(texts)} events via Azure OpenAI ({cfg[2]}) ...")
    records = []
    for eid, t in texts:
        try:
            vec = embed_one(t, cfg)
        except urllib.error.HTTPError as ex:
            sys.exit(f"Azure OpenAI HTTP {ex.code} for {eid}: {ex.read().decode('utf-8', 'ignore')[:200]}")
        records.append((eid, vec))
        print(f"  embedded {eid}  ({len(vec)} dims)")

    cache_path = os.path.join(HERE, "_embeddings.json")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump({eid: vec for eid, vec in records}, f)
    print(f"cached vectors -> {os.path.relpath(cache_path, ROOT)}")

    if cache_only:
        print("--cache-only: skipping Neo4j write.")
        return
    write_neo4j(records)
    print("done. `similar_events` (cypher/04 TOOL 6) is now live.")


if __name__ == "__main__":
    main()
