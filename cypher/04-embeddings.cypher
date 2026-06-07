// ═══════════════════════════════════════════════════════════════════════
// MARKETMIND — NEWSEVENT EMBEDDINGS + VECTOR INDEX  (for the similar_events tool)
//   Run after cypher/01. Populate the embeddings with tools/embed_events.py (Azure OpenAI
//   text-embedding-3-small, 1536 dims), then this index powers precedent retrieval:
//   "the closest past event — here's the blast radius it threw and how prices moved".
//   STRETCH per plan §11.1; the structural Cypher-Template tools are the must.
// ═══════════════════════════════════════════════════════════════════════

// ---------- 1. the vector index (Neo4j 5.13+) ----------
CREATE VECTOR INDEX newsEventEmbedding IF NOT EXISTS
FOR (n:NewsEvent) ON (n.embedding)
OPTIONS { indexConfig: {
  `vector.dimensions`: 1536,
  `vector.similarity_function`: 'cosine'
}};

// ---------- 2. (tools/embed_events.py writes n.embedding per NewsEvent via) ----------
//   MATCH (n:NewsEvent {id:$id}) CALL db.create.setNodeVectorProperty(n, 'embedding', $vec) RETURN n.id;

// ───────────────────────────────────────────────────────────────────────
// TOOL 6 — similar_events(queryEmbedding, k)   the Vector tool
//   The agent embeds the user's headline/text to $queryEmbedding, then:
// ───────────────────────────────────────────────────────────────────────
CALL db.index.vector.queryNodes('newsEventEmbedding', $k, $queryEmbedding)
YIELD node AS e, score
OPTIONAL MATCH (e)-[:HAS_RECORD]->(ir:ImpactRecord {filled:true})-[:FOR_COMPANY]->(c:Company)
WITH e, score, collect({ticker:c.ticker, abnormalReturnPct:ir.abnormalReturnPct})[0..6] AS realized
RETURN e.id AS id, e.headline AS headline, e.date AS date, e.category AS category,
       round(score * 1000) / 1000.0 AS similarity,
       realized   // how the closest analog actually moved — memory + base rate in one card
ORDER BY score DESC;
