using System.Text.Json;
using MarketMind.Engine;

namespace MarketMind.Backend;

/// <summary>
/// Picks the IMarketMindBackend from the feature flags. BCL-only — no DI container required;
/// in an ASP.NET app, register the result as a singleton (LocalCypherBackend) or scoped (AuraAgentBackend
/// with an injected HttpClient). States: Dev = Local+Local · Hosted = Aura+Aura · Backup = Local+AuraDB.
/// </summary>
public static class MarketMindBackendFactory
{
    /// <summary>
    /// Pick the DATA backend from the single toggle <see cref="MarketMindOptions.Mode"/>. Both modes run the same
    /// <c>impact_cascade</c> Cypher over a Neo4j HTTP Query API — only the target + login differ:
    ///   Local → the marketmind-neo4j Docker container · Aura → the remote Aura graph.
    /// (The hosted Aura <i>agent</i> — natural-language — is wired separately on the API's /api/explain path.)
    ///
    /// The DB-backed backend is wrapped in a <see cref="FallbackBackend"/> so /api/cascade degrades gracefully
    /// to the in-proc <see cref="LocalCypherBackend"/> (identical rows) when the DB is unreachable — the app
    /// runs whether or not Docker/Aura is up and seeded. Aura mode without a DB login falls straight through to
    /// the in-proc engine (with a warning) rather than crashing startup.
    /// </summary>
    public static IMarketMindBackend Create(MarketMindOptions opt, GraphData graph, Weights weights, string root, HttpClient http)
    {
        _ = http ?? throw new ArgumentNullException(nameof(http), "The Query API backends need an HttpClient (inject one, ideally from IHttpClientFactory).");
        var cypher = QueryApiBackend.LoadImpactCascade(root);
        var inProc = new LocalCypherBackend(graph, weights);

        QueryApiBackend? primary = opt.Mode switch
        {
            MarketMindMode.Aura => opt.AuraDbConfigured
                ? new QueryApiBackend(http, opt.AuraQueryUrl, opt.AuraDbUser, opt.AuraDbPassword!, cypher, "aura-db")
                : null,
            _ => new QueryApiBackend(http, opt.LocalQueryUrl, opt.LocalDbUser, opt.LocalDbPassword, cypher, "local-db"),
        };

        if (primary is null)
        {
            Console.Error.WriteLine("WARN: Aura mode selected but no DB login (set MM_NEO4J_ID + MM_NEO4J_PASSWORD) — " +
                                    "serving the deterministic cascade from the in-proc engine instead.");
            return inProc;
        }
        return new FallbackBackend(primary, inProc);
    }

    /// <summary>The offline / parity engine (no DB, no network) — used by the MAF agent's tool and as a fallback.</summary>
    public static IMarketMindBackend CreateInProc(GraphData graph, Weights weights) => new LocalCypherBackend(graph, weights);

    /// <summary>Load the calibrated weights (the parity-verified values) from tools/calibrated_weights.json.</summary>
    public static Weights LoadCalibratedWeights(string root)
    {
        var path = Path.Combine(root, "tools", "calibrated_weights.json");
        var d = new Weights();
        if (!File.Exists(path))
        {
            Console.Error.WriteLine($"WARN: calibrated weights not found at {path} — using PRE-CALIBRATION defaults; " +
                                    "the backend will NOT match engine.py / the Cypher tools. Run tools/calibrate.py.");
            return d;
        }
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        var r = doc.RootElement;
        double G(string k, double def) => r.TryGetProperty(k, out var v) ? v.GetDouble() : def;
        return d with
        {
            FSupDown = G("fSupDown", d.FSupDown),
            FSupUp = G("fSupUp", d.FSupUp),
            FPar = G("fPar", d.FPar),
            FOwn = G("fOwn", d.FOwn),
            FCmp = G("fCmp", d.FCmp),
            HopDecay = G("hopDecay", d.HopDecay),
            MinImpact = G("minImpact", d.MinImpact),
            FProd = G("fProd", d.FProd),
            FCons = G("fCons", d.FCons),
            FTheme = G("fTheme", d.FTheme),
            FCondition = G("fCondition", d.FCondition),
            MinSeed = G("minSeed", d.MinSeed),
            ChOperations = G("chOperations", d.ChOperations),
            ChDemand = G("chDemand", d.ChDemand),
            ChCurrency = G("chCurrency", d.ChCurrency),
            ChPolicy = G("chPolicy", d.ChPolicy),
            DomicileDefault = G("domicileDefault", d.DomicileDefault),
        };
    }
}
