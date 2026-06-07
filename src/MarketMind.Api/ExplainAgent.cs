using MarketMind.Agent;
using MarketMind.Backend;

namespace MarketMind.Api;

/// <summary>
/// The "Explain with AI" agent, selected by the single MARKETMIND_MODE toggle (see <see cref="MarketMindMode"/>):
///   Local → the MAF agent (Microsoft Agent Framework + Azure OpenAI, in-proc engine)
///   Aura  → the hosted Aura agent over its REST endpoint (falls back to MAF if no Aura API key is set)
/// </summary>
public interface IExplainAgent
{
    bool IsLive { get; }
    string Kind { get; }
    Task<string> ExplainAsync(string headlineOrQuestion, CancellationToken ct = default);
}

/// <summary>Local mode: the Microsoft Agent Framework agent (Azure OpenAI).</summary>
public sealed class MafExplainAgent(MarketMindAgent maf) : IExplainAgent
{
    public bool IsLive => maf.IsLive;
    public string Kind => "maf · azure openai + in-proc engine";
    public Task<string> ExplainAsync(string h, CancellationToken ct = default) => maf.AnalyzeAsync(h, ct);
}

/// <summary>Aura mode: the hosted Aura agent over its REST endpoint (needs an Aura API key).</summary>
public sealed class AuraExplainAgent(AuraAgentBackend hosted) : IExplainAgent
{
    public bool IsLive => true;
    public string Kind => "aura · hosted agent (gemini)";
    public async Task<string> ExplainAsync(string h, CancellationToken ct = default) =>
        (await hosted.AskAsync(h, ct).ConfigureAwait(false)).Text;
}
