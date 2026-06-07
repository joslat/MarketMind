using System.ComponentModel;
using System.Text;
using Microsoft.Extensions.AI;
using MarketMind.Engine;

namespace MarketMind.Agent;

/// <summary>
/// MarketMind's deterministic cascade, exposed to the LLM as a single function tool. The agent's LLM
/// ONLY classifies the headline; this tool propagates the impact through the in-proc graph. No static
/// state — the engine is injected, so it composes cleanly and is unit-testable.
/// </summary>
public sealed class CascadeTool
{
    private const int TopN = 15;

    private readonly GraphData _graph;
    private readonly CascadeEngine _engine;

    public CascadeTool(GraphData graph, CascadeEngine engine)
    {
        _graph = graph;
        _engine = engine;
    }

    /// <summary>The tool(s) this class exposes, ready to hand to an agent (inspired by FeatureTools.All).</summary>
    public IList<AITool> AsTools() => [AIFunctionFactory.Create(RunCascade)];

    [Description("Run MarketMind's deterministic cascade for a freshly-classified news event over the " +
                 "company-dependency graph and return the ranked blast radius (winners and losers). You name only " +
                 "the directly-hit company; this tool propagates the impact through suppliers, customers, partners, " +
                 "owners and rivals (0..3 hops, fading each hop).")]
    public string RunCascade(
        [Description("ticker of the directly-hit company, e.g. 'TSMC' — must be a company in the graph")] string ticker,
        [Description("-1 if the news is bad for that company, +1 if good")] int sign,
        [Description("0..1 magnitude of the direct shock")] double severity,
        [Description("true for a sector-wide/macro/policy shock (rivals fall together); false for a firm-specific stumble (rivals can benefit)")] bool contagion)
    {
        ticker = (ticker ?? string.Empty).Trim().ToUpperInvariant();
        if (!_graph.ByTicker.ContainsKey(ticker))
            return $"Unknown ticker '{ticker}'. Pick a company that exists in the graph " +
                   "(e.g. TSMC, NVDA, ASML, AAPL, TSLA, SMIC, AMD, INTC).";

        double sev = Math.Clamp(severity, 0, 1);
        int sg = sign >= 0 ? 1 : -1;
        var seeds = new (string, double)[] { (ticker, sg * sev) };
        var impact = _engine.Cascade(seeds, contagion);

        var ranked = impact
            .OrderByDescending(kv => Math.Abs(kv.Value))
            .ThenBy(kv => kv.Key)
            .Take(TopN)
            .ToList();

        var sb = new StringBuilder();
        sb.AppendLine($"Cascade from {ticker} (sign {sg:+0;-0}, severity {sev:0.00}, " +
                      $"{(contagion ? "CONTAGION" : "SUBSTITUTION")}): {impact.Count} companies in range. " +
                      $"Top {ranked.Count} by |impact|:");
        foreach (var (tk, val) in ranked)
        {
            var company = _graph.ByTicker.GetValueOrDefault(tk);
            string tag = (company?.Tradable ?? false) ? "" : " (conduit — propagates but not price-scored)";
            sb.AppendLine($"  {(val >= 0 ? "+" : "")}{val:0.000}  {tk}  ({company?.Name}){tag}");
        }
        return sb.ToString();
    }
}
