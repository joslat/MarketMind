using MarketMind.Engine;

namespace MarketMind.Backend;

/// <summary>
/// Deterministic local backend: the in-proc <see cref="CascadeEngine"/> over data/*.json — no DB, no network.
/// This is the BACKUP DEMO path (and the Dev default). Numerically identical to cypher/02 TOOL 1 on every
/// sign (the §10.5 parity gate); the only difference vs the Cypher tool is that Path here is the SHORTEST
/// dependency chain (BFS) rather than the strongest-magnitude chain — same hop, same direction.
///
/// The Neo4j.Driver variant runs the inlined cypher/05 impact_cascade over Bolt; this in-proc
/// version avoids the NuGet dependency so the backup path always builds.
/// </summary>
public sealed class LocalCypherBackend : IMarketMindBackend
{
    private static readonly HashSet<string> Whitelist = new() { "SUPPLIES_TO", "PARTNERS_WITH", "OWNS", "COMPETES_WITH" };

    private readonly GraphData _g;
    private readonly CascadeEngine _engine;
    private readonly Dictionary<string, List<string>> _adj = new();

    public string Name => "local";

    public LocalCypherBackend(GraphData g, Weights w)
    {
        _g = g;
        _engine = new CascadeEngine(g, w);
        foreach (var e in g.Edges)
        {
            if (!Whitelist.Contains(e.Type)) continue;
            Link(e.From, e.To);
            Link(e.To, e.From);
        }
    }

    private void Link(string a, string b)
    {
        if (!_adj.TryGetValue(a, out var l)) { l = new(); _adj[a] = l; }
        l.Add(b);
    }

    public Task<IReadOnlyList<ImpactRow>> CascadeAsync(string newsId, bool tradableOnly = true, CancellationToken ct = default)
    {
        var ev = _g.Events.FirstOrDefault(e => e.Id == newsId)
                 ?? throw new ArgumentException($"unknown newsId '{newsId}'", nameof(newsId));

        var imp = _engine.PredictedImpacts(ev);                 // clamped, pruned
        var seeds = _engine.SeedEvent(ev);
        var (hop, parent) = Bfs(seeds.Keys.Where(t => _g.ByTicker.ContainsKey(t) || _adj.ContainsKey(t)));

        var rows = imp
            .Where(kv => !tradableOnly || (_g.ByTicker.GetValueOrDefault(kv.Key)?.Tradable ?? false))
            .Select(kv =>
            {
                var c = _g.ByTicker.GetValueOrDefault(kv.Key);
                double v = Math.Round(kv.Value, 3);
                return new ImpactRow(
                    kv.Key, c?.Name ?? kv.Key, c?.Tradable ?? false,
                    v, v >= 0 ? "gain" : "loss",
                    hop.GetValueOrDefault(kv.Key, 0), PathTo(kv.Key, parent));
            })
            .OrderByDescending(r => Math.Abs(r.Impact)).ThenBy(r => r.Ticker)
            .Take(25)
            .ToList();

        return Task.FromResult<IReadOnlyList<ImpactRow>>(rows);
    }

    /// <summary>The local engine is deterministic-cascade-only; free-form NL routing is the hosted agent's job.</summary>
    public Task<AgentAnswer> AskAsync(string question, CancellationToken ct = default) =>
        throw new NotSupportedException(
            "LocalCypherBackend has no natural-language router (that is the Aura ReAct agent's role). " +
            "Call CascadeAsync(newsId) for the deterministic cascade, or set MarketMind:Backend=Aura.");

    // ---- shortest-path BFS over the whitelist (undirected), capped at 3 hops ----
    private (Dictionary<string, int> hop, Dictionary<string, string?> parent) Bfs(IEnumerable<string> seedTickers)
    {
        var hop = new Dictionary<string, int>();
        var parent = new Dictionary<string, string?>();
        var q = new Queue<string>();
        foreach (var s in seedTickers)
            if (hop.TryAdd(s, 0)) { parent[s] = null; q.Enqueue(s); }
        while (q.Count > 0)
        {
            var cur = q.Dequeue();
            int d = hop[cur];
            if (d >= 3 || !_adj.TryGetValue(cur, out var nbrs)) continue;
            foreach (var nb in nbrs)
                if (!hop.ContainsKey(nb)) { hop[nb] = d + 1; parent[nb] = cur; q.Enqueue(nb); }
        }
        return (hop, parent);
    }

    private static string PathTo(string ticker, Dictionary<string, string?> parent)
    {
        if (!parent.ContainsKey(ticker)) return ticker;
        var chain = new List<string>();
        string? cur = ticker;
        var guard = 0;
        while (cur is not null && guard++ < 8) { chain.Add(cur); cur = parent.GetValueOrDefault(cur); }
        chain.Reverse();
        return string.Join(" → ", chain);
    }
}
