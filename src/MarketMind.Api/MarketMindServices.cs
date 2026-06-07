using MarketMind.Agent;
using MarketMind.Backend;
using MarketMind.Engine;

namespace MarketMind.Api;

/// <summary>
/// DI registration for MarketMind. The graph + calibrated weights load once at startup and are shared
/// (singletons) by the backend and the live agent — one source of truth, no per-request reload.
///
/// The IMarketMindBackend (the /api/cascade data path) is chosen by MM_MARKETMIND_MODE:
///   MM_MARKETMIND_MODE unset|Local -> QueryApiBackend over the LOCAL Neo4j (Docker container, HTTP Query API)
///   MM_MARKETMIND_MODE=Aura        -> QueryApiBackend over the remote Aura graph (same Query API, DB login)
/// Both run the identical impact_cascade Cypher (cypher/05) — only the URL + login differ, so the API serves
/// the same rows whether the math runs on the Docker DB or on Aura. Flip one env var, no code change.
/// </summary>
public static class MarketMindServices
{
    public static IServiceCollection AddMarketMind(this IServiceCollection services)
    {
        var root = GraphData.FindRoot();
        var graph = GraphData.Load(root);
        var weights = MarketMindBackendFactory.LoadCalibratedWeights(root);
        var options = MarketMindOptions.FromEnvironment();

        services.AddSingleton(graph);
        services.AddSingleton(weights);
        services.AddSingleton(options);
        services.AddHttpClient();   // IHttpClientFactory for the Aura paths; harmless no-op on the Local path

        // ───────────── THE TOGGLE (MARKETMIND_MODE) wires BOTH halves here, in one place ─────────────
        //   DATA  : Local = local Docker Neo4j (HTTP Query API)  · Aura = remote Aura graph (HTTP Query API)
        //   AGENT : Local = MAF (Azure OpenAI)        · Aura = hosted Aura agent (→ MAF if no Aura API key)

        // 1) data backend (CascadeAsync) — the /api/cascade rows. Both modes hit a Neo4j Query API over HTTP.
        services.AddSingleton<IMarketMindBackend>(sp =>
        {
            var http = sp.GetRequiredService<IHttpClientFactory>().CreateClient("mm-db");
            return MarketMindBackendFactory.Create(options, graph, weights, root, http);
        });

        // 2) explain agent (/api/explain, /api/agent) — natural-language narration
        services.AddSingleton(_ => new MarketMindAgent(AgentOptions.FromEnvironment(), graph, weights, root));
        services.AddSingleton<IExplainAgent>(sp =>
        {
            if (options.Mode == MarketMindMode.Aura && options.AuraConfigured)   // hosted agent only if its API key is set
            {
                var http = sp.GetRequiredService<IHttpClientFactory>().CreateClient("aura-agent");
                return new AuraExplainAgent(new AuraAgentBackend(http, options));
            }
            return new MafExplainAgent(sp.GetRequiredService<MarketMindAgent>());   // Local, or Aura without an API key
        });
        return services;
    }
}
