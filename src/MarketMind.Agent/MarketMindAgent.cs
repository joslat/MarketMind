using Azure;
using Azure.AI.OpenAI;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using MarketMind.Engine;

namespace MarketMind.Agent;

/// <summary>
/// The MarketMind live agent (Microsoft Agent Framework). One contract with the hosted Aura agent:
/// the LLM only classifies + names the directly-hit company; the in-proc cascade engine (the
/// <see cref="CascadeTool"/>) does everything downstream. Reusable from the console entry point and
/// from the API. The underlying <see cref="AIAgent"/> is built lazily on first use.
/// </summary>
public sealed class MarketMindAgent
{
    private readonly AgentOptions _options;
    private readonly IList<AITool> _tools;
    private AIAgent? _agent;

    public MarketMindAgent(AgentOptions options, GraphData graph, Weights weights, string root)
    {
        _options = options;
        var cascade = new CascadeTool(graph, new CascadeEngine(graph, weights));
        var graphTools = new GraphTools(graph, root);
        _tools = [.. cascade.AsTools(), .. graphTools.AsTools()];
    }

    /// <summary>True when Azure OpenAI credentials are present; otherwise <see cref="AnalyzeAsync"/> throws.</summary>
    public bool IsLive => _options.IsConfigured;

    /// <summary>Classify a headline with the LLM, run the cascade tool, and return the narrated Blast Radius.</summary>
    public async Task<string> AnalyzeAsync(string headline, CancellationToken ct = default)
    {
        if (!IsLive)
            throw new InvalidOperationException(
                "MarketMindAgent is not configured — set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY.");

        _agent ??= Build();
        var prompt = $"News headline: {headline}\n" +
                     "Identify the directly-hit company, classify the shock, call run_cascade, then give the Blast Radius card.";
        var response = await _agent.RunAsync(prompt, cancellationToken: ct).ConfigureAwait(false);
        return response.ToString() ?? string.Empty;
    }

    private AIAgent Build() =>
        new AzureOpenAIClient(new Uri(_options.Endpoint), new AzureKeyCredential(_options.ApiKey))
            .GetChatClient(_options.Deployment)
            .AsIChatClient()
            .AsAIAgent(
                instructions: AgentInstructions.Core,
                name: AgentInstructions.AgentName,
                tools: _tools);
}
