using MarketMind.Agent;
using MarketMind.Backend;
using MarketMind.Engine;

// Entry point only — compose the dependencies and run. All behaviour lives in MarketMindAgent / CascadeTool.
//   dotnet run --project src/MarketMind.Agent -- "Magnitude 7.4 earthquake halts TSMC chip output in Taiwan"

string root = GraphData.FindRoot();
var graph = GraphData.Load(root);
var weights = MarketMindBackendFactory.LoadCalibratedWeights(root);
var agent = new MarketMindAgent(AgentOptions.FromEnvironment(), graph, weights, root);

string headline = args.Length > 0
    ? string.Join(' ', args)
    : "Magnitude 7.4 earthquake halts TSMC chip output at multiple fabs in Taiwan";

if (!agent.IsLive)
{
    Console.WriteLine("MarketMind.Agent (Microsoft Agent Framework) — NOT configured, running inert.");
    Console.WriteLine($"  graph: {graph.Companies.Count} companies · {graph.Edges.Count} edges · tool 'run_cascade' ready.");
    Console.WriteLine($"  headline that WOULD be analyzed: \"{headline}\"");
    Console.WriteLine("  Set AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY (deployment defaults to gpt-4o) to run live.");
    return;
}

Console.WriteLine($"MarketMind.Agent · headline:\n  \"{headline}\"\n");
Console.WriteLine(await agent.AnalyzeAsync(headline));
