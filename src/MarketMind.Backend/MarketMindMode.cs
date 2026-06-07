namespace MarketMind.Backend;

/// <summary>
/// ─────────────────────────────  THE FEATURE TOGGLE  ─────────────────────────────
/// One environment variable — <c>MM_MARKETMIND_MODE</c> — flips the whole application between two modes.
/// This enum is the single, central switch. Nothing else needs editing to change where MarketMind runs;
/// the factory (data) and the API composition (agent) both read it and wire the matching pieces.
///
///   Local : the local Neo4j (marketmind-neo4j Docker) over its Query API  +  the MAF agent (Azure OpenAI)
///   Aura  : the REMOTE Aura graph over its Query API                       +  the hosted Aura Agent       [cloud]
///
/// Both modes run the SAME impact_cascade Cypher over a Neo4j HTTP Query API — only the URL + DB login differ.
/// Wiring map (so you only ever look in two places):
///   • data backend  (CascadeAsync) → MarketMindBackendFactory.Create   : Local = local Docker DB · Aura = remote Aura DB  (both QueryApiBackend)
///   • explain agent (/api/explain) → MarketMindServices.AddMarketMind  : Local = MAF · Aura = hosted Aura agent (falls back to MAF if no Aura API key)
///
/// Set it with:  setx MM_MARKETMIND_MODE Aura   (or Local).  Default = Local.  (MARKETMIND_MODE is also accepted.)
/// Local mode needs the container running:  docker start marketmind-neo4j.
/// ────────────────────────────────────────────────────────────────────────────────
/// </summary>
public enum MarketMindMode
{
    /// <summary>The local Neo4j (marketmind-neo4j Docker) over its Query API + the MAF (Azure OpenAI) agent.</summary>
    Local,

    /// <summary>The remote Aura graph over its Query API (DB login) + the hosted Aura agent.</summary>
    Aura,
}
