using System.Text.Json;

namespace MarketMind.Engine;

public sealed record Company(
    string Ticker, string Name, string Sector, string? Country,
    bool Tradable, string? PriceTicker, string? Benchmark, string? ListedFrom,
    Dictionary<string, double>? Exposure);

public sealed record Edge(string From, string Type, string To, double Weight);

public sealed record Hit(string Ticker, int Sign, double Severity, string? Why);

public sealed record Seed(string Type, string Id, int Sign, double Severity, string? Why, string? ConditionAction);

public sealed record NewsEvent(
    string Id, string Headline, string Date, string? Source, string? Url,
    string Category, string Scope, List<Hit> Hits, List<Seed> Seeds,
    Dictionary<string, double>? ChannelVector);

public sealed record ExposureEdge(string From, string Rel, string To, double Value, int Sign, string? Channel);

public sealed record Condition(string Id, string Kind, string Status);

/// <summary>Loads the MarketMind single source of truth (data/*.json) into memory.</summary>
public sealed class GraphData
{
    public List<Company> Companies { get; } = new();
    public List<Edge> Edges { get; } = new();
    public List<NewsEvent> Events { get; } = new();
    public List<ExposureEdge> ExposureEdges { get; } = new();
    public List<Condition> Conditions { get; } = new();
    public Dictionary<string, Company> ByTicker { get; } = new();

    private static readonly JsonSerializerOptions Opt = new() { PropertyNameCaseInsensitive = true };

    public static string FindRoot(string? start = null)
    {
        var dir = new DirectoryInfo(start ?? Directory.GetCurrentDirectory());
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "data", "companies.json"))) return dir.FullName;
            dir = dir.Parent;
        }
        throw new DirectoryNotFoundException("could not locate repo root (data/companies.json) from " +
            (start ?? Directory.GetCurrentDirectory()));
    }

    private static JsonElement Arr(string path, string key)
    {
        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        return doc.RootElement.GetProperty(key).Clone();
    }

    public static GraphData Load(string root)
    {
        var g = new GraphData();
        var dataDir = Path.Combine(root, "data");

        foreach (var c in Arr(Path.Combine(dataDir, "companies.json"), "companies").EnumerateArray())
        {
            Dictionary<string, double>? exp = c.TryGetProperty("exposure", out var e)
                ? e.Deserialize<Dictionary<string, double>>(Opt) : null;
            var co = new Company(
                c.GetProperty("ticker").GetString()!,
                c.GetProperty("name").GetString()!,
                c.GetProperty("sector").GetString()!,
                c.TryGetProperty("country", out var cc) ? cc.GetString() : null,
                c.GetProperty("tradable").GetBoolean(),
                c.TryGetProperty("priceTicker", out var pt) && pt.ValueKind != JsonValueKind.Null ? pt.GetString() : null,
                c.TryGetProperty("benchmark", out var bm) && bm.ValueKind != JsonValueKind.Null ? bm.GetString() : null,
                c.TryGetProperty("listedFrom", out var lf) ? lf.GetString() : null,
                exp);
            g.Companies.Add(co);
            g.ByTicker[co.Ticker] = co;
        }

        foreach (var x in Arr(Path.Combine(dataDir, "edges.json"), "edges").EnumerateArray())
            g.Edges.Add(new Edge(x.GetProperty("from").GetString()!, x.GetProperty("type").GetString()!,
                x.GetProperty("to").GetString()!, x.GetProperty("weight").GetDouble()));

        foreach (var ev in Arr(Path.Combine(dataDir, "events.json"), "events").EnumerateArray())
        {
            var hits = new List<Hit>();
            if (ev.TryGetProperty("hits", out var hs))
                foreach (var h in hs.EnumerateArray())
                    hits.Add(new Hit(h.GetProperty("ticker").GetString()!, h.GetProperty("sign").GetInt32(),
                        h.GetProperty("severity").GetDouble(), h.TryGetProperty("why", out var w) ? w.GetString() : null));
            var seeds = new List<Seed>();
            if (ev.TryGetProperty("seeds", out var ss))
                foreach (var s in ss.EnumerateArray())
                    seeds.Add(new Seed(s.GetProperty("type").GetString()!, s.GetProperty("id").GetString()!,
                        s.GetProperty("sign").GetInt32(), s.GetProperty("severity").GetDouble(),
                        s.TryGetProperty("why", out var w) ? w.GetString() : null,
                        s.TryGetProperty("conditionAction", out var ca) ? ca.GetString() : null));
            Dictionary<string, double>? cv = ev.TryGetProperty("channelVector", out var c2)
                ? c2.Deserialize<Dictionary<string, double>>(Opt) : null;
            g.Events.Add(new NewsEvent(
                ev.GetProperty("id").GetString()!, ev.GetProperty("headline").GetString()!,
                ev.GetProperty("date").GetString()!, ev.TryGetProperty("source", out var sr) ? sr.GetString() : null,
                ev.TryGetProperty("url", out var u) ? u.GetString() : null, ev.GetProperty("category").GetString()!,
                ev.TryGetProperty("scope", out var sc) ? sc.GetString()! : "company", hits, seeds, cv));
        }

        var macroPath = Path.Combine(dataDir, "macro.json");
        if (File.Exists(macroPath))
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(macroPath));
            var root2 = doc.RootElement;
            if (root2.TryGetProperty("exposureEdges", out var ee))
                foreach (var x in ee.EnumerateArray())
                    g.ExposureEdges.Add(new ExposureEdge(
                        x.GetProperty("from").GetString()!, x.GetProperty("rel").GetString()!,
                        x.GetProperty("to").GetString()!, x.TryGetProperty("value", out var v) ? v.GetDouble() : 0,
                        x.TryGetProperty("sign", out var sg) ? sg.GetInt32() : 1,
                        x.TryGetProperty("channel", out var ch) ? ch.GetString() : null));
            if (root2.TryGetProperty("conditions", out var cs))
                foreach (var x in cs.EnumerateArray())
                    g.Conditions.Add(new Condition(x.GetProperty("id").GetString()!,
                        x.GetProperty("kind").GetString()!, x.GetProperty("status").GetString()!));
        }
        return g;
    }
}
