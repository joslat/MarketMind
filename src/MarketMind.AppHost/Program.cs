// MarketMind.AppHost — .NET Aspire. A single `dotnet run` here launches the whole stack, wired together:
// the Neo4j container, the MarketMind.Api backend, and the React/Vite frontend.
var builder = DistributedApplication.CreateBuilder(args);

static string Env(string k) => Environment.GetEnvironmentVariable(k) ?? "";
// Local Neo4j dev-container password — from MM_LOCAL_NEO4J_PASSWORD, with a throwaway local-dev placeholder otherwise.
var localPw = Env("MM_LOCAL_NEO4J_PASSWORD") is { Length: > 0 } lp ? lp : "neo4j_local_dev";

// Neo4j 5.26 — the local graph database (Browser on 7474, Bolt on 7687).
var neo4j = builder.AddContainer("neo4j", "neo4j", "5.26")
    .WithEnvironment("NEO4J_AUTH", $"neo4j/{localPw}")
    .WithEnvironment("NEO4J_PLUGINS", "[\"apoc\"]")
    .WithEndpoint(name: "http", port: 7474, targetPort: 7474, scheme: "http")
    .WithEndpoint(name: "bolt", port: 7687, targetPort: 7687);

// The backend API (deterministic cascade + the live MAF agent). The toggle flows through: MM_MARKETMIND_MODE=Aura
// serves from the remote Aura graph (Query API, MM_NEO4J_*); Local uses the local Neo4j (MM_LOCAL_NEO4J_PASSWORD).
var api = builder.AddProject<Projects.MarketMind_Api>("api")
    .WithEnvironment("NEO4J_URI", "bolt://localhost:7687")
    .WithEnvironment("NEO4J_USER", "neo4j")
    .WithEnvironment("NEO4J_PASSWORD", localPw)
    .WithEnvironment("MM_LOCAL_NEO4J_PASSWORD", localPw)
    .WithEnvironment("MM_MARKETMIND_MODE", Environment.GetEnvironmentVariable("MM_MARKETMIND_MODE") ?? Environment.GetEnvironmentVariable("MARKETMIND_MODE") ?? "Local")
    .WithEnvironment("MM_NEO4J_ID", Env("MM_NEO4J_ID"))
    .WithEnvironment("MM_NEO4J_PASSWORD", Env("MM_NEO4J_PASSWORD"))
    .WaitFor(neo4j);

// The React/Vite frontend. Aspire injects the dev-server PORT and a service reference to the API
// (npm install + `npm run dev` are handled automatically).
builder.AddViteApp("web", "../../web")
    .WithReference(api)
    .WithEnvironment("VITE_API_URL", api.GetEndpoint("http")) // the browser reads this for "Explain with AI"
    .WaitFor(api)
    .WithExternalHttpEndpoints();

builder.Build().Run();
