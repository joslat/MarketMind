namespace MarketMind.Engine;

public sealed record Weights(
    double FSupDown = 0.70, double FSupUp = 0.40, double FPar = 0.50, double FOwn = 0.55, double FCmp = 0.45,
    double HopDecay = 0.65, double MinImpact = 0.03,
    double FProd = 0.60, double FCons = 0.60, double FTheme = 0.70, double FCondition = 0.80, double MinSeed = 0.05,
    double ChOperations = 1.0, double ChDemand = 0.8, double ChCurrency = 0.6, double ChPolicy = 1.0,
    double DomicileDefault = 0.40);

/// <summary>
/// Deterministic cascade engine (C# port of tools/engine.py — the parity reference).
/// PHASE 0 macro seeder (one-way) then PHASE 1 directional structural cascade.
/// </summary>
public sealed class CascadeEngine
{
    private const int MaxHops = 3;
    private static readonly HashSet<string> Whitelist = new() { "SUPPLIES_TO", "PARTNERS_WITH", "OWNS", "COMPETES_WITH" };
    private static readonly HashSet<string> ContagionCats = new()
        { "macro", "sector", "geopolitical", "fx_monetary", "commodity_shock", "thematic" };

    private readonly GraphData _g;
    private readonly Weights _w;
    // adjacency: node -> list of (neighbor, type, weight, nodeIsSupplier)
    private readonly Dictionary<string, List<(string nb, string type, double w, bool fromIsSupplier)>> _adj = new();

    public CascadeEngine(GraphData g, Weights w)
    {
        _g = g; _w = w;
        foreach (var e in g.Edges)
        {
            if (!Whitelist.Contains(e.Type)) continue;
            double wt = e.Type == "OWNS" ? e.Weight / 100.0 : e.Weight;
            Add(e.From, (e.To, e.Type, wt, true));
            Add(e.To, (e.From, e.Type, wt, false));
        }
    }

    private void Add(string k, (string, string, double, bool) v)
    {
        if (!_adj.TryGetValue(k, out var l)) { l = new(); _adj[k] = l; }
        l.Add(v);
    }

    private double TypeFactor(string type, bool fromIsSupplier) => type switch
    {
        "SUPPLIES_TO" => fromIsSupplier ? _w.FSupDown : _w.FSupUp,
        "PARTNERS_WITH" => _w.FPar,
        "OWNS" => _w.FOwn,
        "COMPETES_WITH" => -_w.FCmp,
        _ => 0.4,
    };

    // ---- PHASE 1: structural cascade ----
    public Dictionary<string, double> Cascade(IEnumerable<(string tk, double val)> seeds, bool contagion)
    {
        var impact = new Dictionary<string, double>();
        void Dfs(string node, double val, int depth, HashSet<string> visited)
        {
            impact[node] = impact.GetValueOrDefault(node) + val;
            if (depth >= MaxHops || !_adj.TryGetValue(node, out var nbrs)) return;
            foreach (var (nb, type, w, fromIsSupplier) in nbrs)
            {
                if (visited.Contains(nb)) continue;
                if (contagion && type == "COMPETES_WITH") continue;
                double nv = val * TypeFactor(type, fromIsSupplier) * w * _w.HopDecay;
                if (Math.Abs(nv) < _w.MinImpact) continue;
                Dfs(nb, nv, depth + 1, new HashSet<string>(visited) { nb });
            }
        }
        foreach (var (tk, val) in seeds)
            if (_adj.ContainsKey(tk) || _g.ByTicker.ContainsKey(tk))
                Dfs(tk, val, 0, new HashSet<string> { tk });
        return impact.Where(kv => Math.Abs(kv.Value) >= _w.MinImpact).ToDictionary(kv => kv.Key, kv => kv.Value);
    }

    // ---- PHASE 0: macro seeder ----
    public Dictionary<string, double> SeedEvent(NewsEvent ev)
    {
        var seeds = new Dictionary<string, double>();
        void Add(string tk, double v) => seeds[tk] = seeds.GetValueOrDefault(tk) + v;

        foreach (var h in ev.Hits) Add(h.Ticker, h.Sign * h.Severity);

        var ch = new Dictionary<string, double> {
            ["operations"] = _w.ChOperations, ["demand"] = _w.ChDemand,
            ["currency"] = _w.ChCurrency, ["policy"] = _w.ChPolicy };

        foreach (var s in ev.Seeds)
        {
            switch (s.Type)
            {
                case "country":
                    var cv = ev.ChannelVector ?? new() { ["operations"] = 0.5, ["demand"] = 0.5 };
                    foreach (var c in _g.Companies)
                    {
                        double tot = 0; bool touched = false;
                        foreach (var (k, cw) in cv)
                        {
                            if (cw == 0) continue;
                            double? ex = CountryExposure(c.Ticker, s.Id, k);
                            if (ex is null) continue;
                            touched = true;
                            tot += cw * ex.Value * ch.GetValueOrDefault(k, 0.5);
                        }
                        if (!touched && c.Country == s.Id)
                            tot = (cv.GetValueOrDefault("demand", 0.5)) * _w.DomicileDefault;
                        double val = s.Severity * s.Sign * tot;
                        if (Math.Abs(val) >= _w.MinSeed) Add(c.Ticker, val);
                    }
                    break;
                case "commodity":
                    foreach (var e in _g.ExposureEdges)
                    {
                        if (e.To != s.Id) continue;
                        if (e.Rel == "PRODUCES") Add(e.From, s.Sign * s.Severity * e.Value * _w.FProd);
                        else if (e.Rel == "CONSUMES") Add(e.From, -s.Sign * s.Severity * e.Value * _w.FCons);
                    }
                    break;
                case "theme":
                    foreach (var e in _g.ExposureEdges)
                        if (e.Rel == "EXPOSED_TO_THEME" && e.To == s.Id)
                            Add(e.From, s.Sign * s.Severity * e.Value * e.Sign * _w.FTheme);
                    break;
                case "condition":
                    int flip = s.ConditionAction == "LIFTS" ? -1 : 1;
                    foreach (var e in _g.ExposureEdges)
                        if (e.Rel == "CONSTRAINS" && e.From == s.Id)
                            Add(e.To, flip * s.Severity * e.Value * e.Sign * _w.FCondition);
                    break;
            }
        }

        var hitTickers = ev.Hits.Select(h => h.Ticker).ToHashSet();
        return seeds.Where(kv => Math.Abs(kv.Value) >= _w.MinSeed || hitTickers.Contains(kv.Key))
                    .ToDictionary(kv => kv.Key, kv => kv.Value);
    }

    private double? CountryExposure(string ticker, string code, string channel)
    {
        double? Val(string rel)
        {
            foreach (var e in _g.ExposureEdges)
                if (e.From == ticker && e.Rel == rel && e.To == code) return e.Value;
            return null;
        }
        return channel switch
        {
            "operations" => Val("OPERATES_IN"),
            "demand" => Val("REVENUE_FROM"),
            "currency" => Val("REVENUE_FROM"),
            // value*sign; NO country-agnostic policyBeta fallback (it leaked across countries)
            "policy" => _g.ExposureEdges
                .Where(e => e.From == ticker && e.Rel == "EXPOSED_TO_POLICY" && e.To == code)
                .Select(e => (double?)(e.Value * e.Sign)).FirstOrDefault(),
            _ => null,
        };
    }

    public bool Regime(NewsEvent ev)
    {
        if (ContagionCats.Contains(ev.Category)) return true;
        var secs = ev.Hits.Select(h => _g.ByTicker.GetValueOrDefault(h.Ticker)?.Sector).Where(s => s != null).ToList();
        return secs.Any(s => secs.Count(x => x == s) >= 2);
    }

    public Dictionary<string, double> PredictedImpacts(NewsEvent ev)
    {
        var imp = Cascade(SeedEvent(ev).Select(kv => (kv.Key, kv.Value)), Regime(ev));
        return imp.ToDictionary(kv => kv.Key, kv => Math.Clamp(kv.Value, -1.0, 1.0));
    }
}
