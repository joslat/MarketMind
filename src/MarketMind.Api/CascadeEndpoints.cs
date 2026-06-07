using MarketMind.Agent;
using MarketMind.Backend;
using MarketMind.Engine;

namespace MarketMind.Api;

/// <summary>The MarketMind HTTP surface — deterministic cascade + the live agent. One method per concern.</summary>
public static class CascadeEndpoints
{
    public static IEndpointRouteBuilder MapMarketMind(this IEndpointRouteBuilder app)
    {
        app.MapGet("/health", () => Results.Ok(new { status = "ok" }));

        // the curated event list (what the frontend / agent can ask about)
        app.MapGet("/api/events", (GraphData g) =>
            g.Events.Select(e => new { e.Id, e.Headline, e.Category, e.Scope, e.Date }));

        // the deterministic blast radius for a known event — runs the impact_cascade Cypher against the
        // Neo4j chosen by MM_MARKETMIND_MODE (Local = Docker DB · Aura = Aura DB), both over the HTTP Query API.
        app.MapGet("/api/cascade/{newsId}", async (
            string newsId, bool? tradableOnly, IMarketMindBackend backend, CancellationToken ct) =>
        {
            try
            {
                var rows = await backend.CascadeAsync(newsId, tradableOnly ?? true, ct);
                return Results.Ok(rows);
            }
            catch (ArgumentException ex)
            {
                return Results.NotFound(new { error = ex.Message });
            }
        });

        // "Explain with AI" for a KNOWN event — the agent chosen by MARKETMIND_MODE (MAF or hosted Aura agent).
        app.MapGet("/api/explain/{newsId}", async (
            string newsId, GraphData g, IExplainAgent agent, CancellationToken ct) =>
        {
            if (!agent.IsLive)
                return Results.Json(new { error = "Agent not configured — set the Azure OpenAI keys (MAF), or the Aura API key for the hosted agent." },
                                    statusCode: StatusCodes.Status503ServiceUnavailable);
            var ev = g.Events.FirstOrDefault(e => e.Id == newsId);
            if (ev is null)
                return Results.NotFound(new { error = $"unknown event '{newsId}'" });
            return Results.Ok(new { answer = await agent.ExplainAsync(ev.Headline, ct), agent = agent.Kind, disclaimer = Disclaimer.Short });
        });

        // the LIVE path: a free-text headline → the mode-selected agent (LLM classifies, the graph propagates)
        app.MapPost("/api/agent", async (HeadlineRequest req, IExplainAgent agent, CancellationToken ct) =>
        {
            if (!agent.IsLive)
                return Results.Json(new { error = "Agent not configured — set the Azure OpenAI keys (MAF), or the Aura API key for the hosted agent." },
                                    statusCode: StatusCodes.Status503ServiceUnavailable);
            if (string.IsNullOrWhiteSpace(req.Headline))
                return Results.BadRequest(new { error = "headline is required" });

            return Results.Ok(new { answer = await agent.ExplainAsync(req.Headline, ct), agent = agent.Kind, disclaimer = Disclaimer.Short });
        });

        return app;
    }
}

/// <summary>POST body for the live-agent endpoint.</summary>
public sealed record HeadlineRequest(string Headline);
