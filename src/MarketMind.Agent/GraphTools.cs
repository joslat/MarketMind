using System.ComponentModel;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.AI;
using MarketMind.Engine;

namespace MarketMind.Agent;

/// <summary>
/// Read-only drill-down tools the agent can call for follow-ups (separate from the cascade itself, so
/// each tool class stays single-responsibility): a company's dependency map, and the realized backtest
/// for a KNOWN event. Both are deterministic — they read the graph / golden dataset, never invent.
/// </summary>
public sealed class GraphTools
{
    private readonly GraphData _graph;
    private readonly string _root;

    public GraphTools(GraphData graph, string root)
    {
        _graph = graph;
        _root = root;
    }

    public IList<AITool> AsTools() =>
        [AIFunctionFactory.Create(CompanyDependencyMap), AIFunctionFactory.Create(ValidateHistory)];

    [Description("A company's direct dependencies in the graph: who supplies it, who it supplies, its " +
                 "competitors, and its owners. Use to explain WHY a company is exposed.")]
    public string CompanyDependencyMap([Description("ticker, e.g. 'TSMC' — must exist in the graph")] string ticker)
    {
        ticker = (ticker ?? string.Empty).Trim().ToUpperInvariant();
        if (!_graph.ByTicker.ContainsKey(ticker))
            return $"Unknown ticker '{ticker}'.";

        var suppliedBy = _graph.Edges.Where(e => e.Type == "SUPPLIES_TO" && e.To == ticker).Select(e => e.From);
        var suppliesTo = _graph.Edges.Where(e => e.Type == "SUPPLIES_TO" && e.From == ticker).Select(e => e.To);
        var competes = _graph.Edges.Where(e => e.Type == "COMPETES_WITH" && (e.From == ticker || e.To == ticker))
                                   .Select(e => e.From == ticker ? e.To : e.From);
        var ownedBy = _graph.Edges.Where(e => e.Type == "OWNS" && e.To == ticker).Select(e => e.From);

        var sb = new StringBuilder();
        sb.AppendLine($"{ticker} ({_graph.ByTicker[ticker].Name}) — dependency map:");
        sb.AppendLine($"  supplied by:   {Join(suppliedBy)}");
        sb.AppendLine($"  supplies to:   {Join(suppliesTo)}");
        sb.AppendLine($"  competes with: {Join(competes)}");
        sb.AppendLine($"  owned by:      {Join(ownedBy)}");
        return sb.ToString();
    }

    [Description("The realized backtest for a KNOWN past event: actual abnormal returns per company from " +
                 "Yahoo Finance. Returns a clear 'no data' message for ad-hoc headlines not in the dataset.")]
    public string ValidateHistory([Description("the event id, e.g. 'evt_chip_controls_tighten_2023'")] string newsId)
    {
        var path = Path.Combine(_root, "tools", "golden.json");
        if (!File.Exists(path))
            return "No backtest data available (golden.json not built).";

        using var doc = JsonDocument.Parse(File.ReadAllText(path));
        if (!doc.RootElement.TryGetProperty(newsId ?? string.Empty, out var ev))
            return $"No realized data for '{newsId}' — it is not one of the curated, price-graded events.";

        var rows = new List<(string Ticker, double Abnormal)>();
        foreach (var p in ev.EnumerateObject())
            if (p.Value.TryGetProperty("abn", out var abn))
                rows.Add((p.Name, abn.GetDouble()));

        var sb = new StringBuilder($"Realized abnormal returns for {newsId} (top by |move|, 1-day window):\n");
        foreach (var (tk, abnormal) in rows.OrderByDescending(r => Math.Abs(r.Abnormal)).Take(12))
            sb.AppendLine($"  {(abnormal >= 0 ? "+" : "")}{abnormal * 100:0.0}%  {tk}");
        return sb.ToString();
    }

    private static string Join(IEnumerable<string> tickers)
    {
        var list = tickers.Distinct().ToList();
        return list.Count == 0 ? "—" : string.Join(", ", list);
    }
}
