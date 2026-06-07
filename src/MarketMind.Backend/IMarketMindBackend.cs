namespace MarketMind.Backend;

/// <summary>One ranked exposure row — the unit the Blast Radius card renders (matches cypher/02 TOOL 1 projection).</summary>
public sealed record ImpactRow(
    string Ticker, string Name, bool Tradable,
    double Impact, string Direction, int Hop, string Path);

/// <summary>
/// A structured agent answer. The deterministic numbers come from <see cref="Rows"/> (the
/// cypher_template_tool_result), NOT from the prose: render the card from Rows,
/// use <see cref="Text"/> only as the narration. <see cref="Source"/> = "local" | "aura".
/// </summary>
public sealed record AgentAnswer(
    string Text, IReadOnlyList<ImpactRow> Rows, string? Regime, string Source);

/// <summary>What the UI / Export / Agent head all call. One graph, two heads.</summary>
public interface IMarketMindBackend
{
    /// <summary>Deterministic cascade for an event — the headline tool. Always available on both backends.</summary>
    Task<IReadOnlyList<ImpactRow>> CascadeAsync(
        string newsId, bool tradableOnly = true, CancellationToken ct = default);

    /// <summary>
    /// Free-form question. The Aura backend routes it through the hosted ReAct agent (Gemini orchestration);
    /// the Local backend has no NL router and throws <see cref="NotSupportedException"/> — use CascadeAsync.
    /// </summary>
    Task<AgentAnswer> AskAsync(string question, CancellationToken ct = default);

    /// <summary>"local" or "aura" — which head answered (for the UI badge + telemetry).</summary>
    string Name { get; }
}

public enum BackendKind { Local, Aura }
public enum Neo4jTarget { Local, Aura }

/// <summary>
/// Feature flags. Bind them with <see cref="FromEnvironment"/> (env vars) or, in an ASP.NET host, from the
/// IConfiguration "MarketMind" section; the factory picks the implementation:
///   Dev        = Local  + Local   · Hosted = Aura + Aura
///   Backup demo = Local backend + Aura DB (our deterministic engine over cloud data if the agent misbehaves).
/// NOTE: the web app is a static-cascade cinema with NO runtime backend toggle — the Local↔Aura switch is a
/// .NET/agent concern only (the primary surface is the hosted Aura agent, not the web).
/// </summary>
public sealed class MarketMindOptions
{
    /// <summary>THE feature toggle (see <see cref="MarketMindMode"/>) — read from MARKETMIND_MODE.</summary>
    public MarketMindMode Mode { get; set; } = MarketMindMode.Local;

    public BackendKind Backend { get; set; } = BackendKind.Local;
    public Neo4jTarget Neo4jTarget { get; set; } = Neo4jTarget.Local;

    // ---- Aura agent (channel a: HTTPS to api.neo4j.io + the copied agent endpoint) ----
    public string? AuraTokenUrl { get; set; } = "https://api.neo4j.io/oauth/token";
    public string? AuraEndpointUrl { get; set; }   // opaque — copy from the console (External Access)
    public string? AuraClientId { get; set; }
    public string? AuraClientSecret { get; set; }

    // ---- Neo4j DB (channel b: Bolt over neo4j+s://) — for the Neo4j.Driver LocalCypherBackend variant ----
    public string? Neo4jUri { get; set; } = "bolt://localhost:7687";
    public string? Neo4jUser { get; set; } = "neo4j";
    public string? Neo4jPassword { get; set; }

    // ---- Aura DB over the HTTP Query API (the Aura-mode DATA path) ----
    // Auth is the ordinary database login — NO Aura API key needed. On these instances the dbid doubles as the
    // username (e.g. an 8-char dbid). Read from MM_NEO4J_ID / MM_NEO4J_PASSWORD (or derived from NEO4J_URI / NEO4J_PASSWORD).
    public string? AuraDbId { get; set; }
    public string? AuraDbPassword { get; set; }
    public string AuraDbUser => AuraDbId ?? "neo4j";
    public string AuraQueryUrl => $"https://{AuraDbId}.databases.neo4j.io/db/{AuraDbId}/query/v2";
    public bool AuraDbConfigured => !string.IsNullOrWhiteSpace(AuraDbId) && !string.IsNullOrWhiteSpace(AuraDbPassword);

    // ---- Local DB over the Query API (the Local-mode data path = the marketmind-neo4j Docker container) ----
    // Defaults match the dev seed scripts / AppHost; override with MM_LOCAL_QUERY_URL / MM_LOCAL_NEO4J_USER / MM_LOCAL_NEO4J_PASSWORD.
    public string LocalQueryUrl { get; set; } = "http://localhost:7474/db/neo4j/query/v2";
    public string LocalDbUser { get; set; } = "neo4j";
    public string LocalDbPassword { get; set; } = "neo4j_local_dev";   // throwaway local-dev default; override with MM_LOCAL_NEO4J_PASSWORD

    /// <summary>True only when the Aura agent channel has an endpoint + client credentials.</summary>
    public bool AuraConfigured =>
        !string.IsNullOrWhiteSpace(AuraEndpointUrl) &&
        !string.IsNullOrWhiteSpace(AuraClientId) &&
        !string.IsNullOrWhiteSpace(AuraClientSecret);

    /// <summary>
    /// Bind the flags + secrets from environment variables — the "simple trigger + configuration" switch.
    /// Flip <c>MARKETMIND_BACKEND=Aura</c> to route to the hosted agent; with no Aura creds the AuraAgentBackend
    /// stays inert (throws a clear error at call time), so the flag is always safe to set. Recognised vars:
    ///   MARKETMIND_BACKEND = Local|Aura        (default Local)
    ///   MARKETMIND_NEO4J_TARGET = Local|Aura   (default Local; the Bolt-over-Aura backend variant is not yet built)
    ///   AURA_ENDPOINT_URL / AURA_CLIENT_ID / AURA_CLIENT_SECRET / AURA_TOKEN_URL   (the hosted-agent channel)
    ///   NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD   (the Bolt channel, for the Neo4j.Driver variant)
    /// In an ASP.NET app, bind the same names from IConfiguration instead; this BCL reader needs no host.
    /// </summary>
    public static MarketMindOptions FromEnvironment()
    {
        static string? E(string k) => Environment.GetEnvironmentVariable(k);
        static T Enum<T>(string? v, T def) where T : struct =>
            System.Enum.TryParse<T>(v, ignoreCase: true, out var r) ? r : def;

        var o = new MarketMindOptions
        {
            Backend = Enum(E("MARKETMIND_BACKEND"), BackendKind.Local),
            Neo4jTarget = Enum(E("MARKETMIND_NEO4J_TARGET"), Neo4jTarget.Local),
            AuraEndpointUrl = E("AURA_ENDPOINT_URL"),
            AuraClientId = E("AURA_CLIENT_ID"),
            AuraClientSecret = E("AURA_CLIENT_SECRET"),
        };
        if (E("AURA_TOKEN_URL") is { Length: > 0 } tok) o.AuraTokenUrl = tok;
        if (E("NEO4J_URI") is { Length: > 0 } uri) o.Neo4jUri = uri;
        if (E("NEO4J_USER") is { Length: > 0 } usr) o.Neo4jUser = usr;
        if (E("NEO4J_PASSWORD") is { Length: > 0 } pw) o.Neo4jPassword = pw;

        // THE toggle. MM_MARKETMIND_MODE (the MM_-prefixed name) wins; MARKETMIND_MODE and legacy
        // MARKETMIND_BACKEND=Aura are accepted too.
        o.Mode = Enum(E("MM_MARKETMIND_MODE") ?? E("MARKETMIND_MODE"),
                      o.Backend == BackendKind.Aura ? MarketMindMode.Aura : MarketMindMode.Local);
        // Aura-DB (Query API) login: prefer MM_NEO4J_*, else derive from the NEO4J_* / Aura URI.
        o.AuraDbId = E("MM_NEO4J_ID") is { Length: > 0 } id ? id : DeriveDbId(o.Neo4jUri);
        o.AuraDbPassword = E("MM_NEO4J_PASSWORD") is { Length: > 0 } dpw ? dpw : o.Neo4jPassword;
        // Local-DB (Docker) overrides.
        if (E("MM_LOCAL_QUERY_URL") is { Length: > 0 } lq) o.LocalQueryUrl = lq;
        if (E("MM_LOCAL_NEO4J_USER") is { Length: > 0 } lu) o.LocalDbUser = lu;
        if (E("MM_LOCAL_NEO4J_PASSWORD") is { Length: > 0 } lpw) o.LocalDbPassword = lpw;
        return o;
    }

    /// <summary>Pull the Aura dbid out of a neo4j+s://{id}.databases.neo4j.io URI (null if not an Aura URI).</summary>
    private static string? DeriveDbId(string? uri)
    {
        if (string.IsNullOrEmpty(uri)) return null;
        var m = System.Text.RegularExpressions.Regex.Match(uri, @"//([a-z0-9]+)\.databases\.neo4j\.io");
        return m.Success ? m.Groups[1].Value : null;
    }
}
