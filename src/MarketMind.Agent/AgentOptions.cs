namespace MarketMind.Agent;

/// <summary>
/// Azure OpenAI configuration for the live MarketMind agent. Mirrors the AFCourseSamples/AIConfig.cs
/// convention: AZURE_OPENAI_ENDPOINT + AZURE_OPENAI_API_KEY, model deployment defaulting to gpt-4o.
/// One source of truth for "am I configured?" — the rest of the code never re-reads the environment.
/// </summary>
public sealed class AgentOptions
{
    public string Endpoint { get; init; } = "";
    public string ApiKey { get; init; } = "";
    public string Deployment { get; init; } = DefaultDeployment;

    public const string DefaultDeployment = "gpt-4o";

    /// <summary>True only when both endpoint and key are present; otherwise the agent stays inert.</summary>
    public bool IsConfigured => !string.IsNullOrWhiteSpace(Endpoint) && !string.IsNullOrWhiteSpace(ApiKey);

    /// <summary>Bind from environment variables (or, in a host, from IConfiguration with the same keys).</summary>
    public static AgentOptions FromEnvironment() => new()
    {
        Endpoint = Env("AZURE_OPENAI_ENDPOINT"),
        ApiKey = Env("AZURE_OPENAI_API_KEY"),
        Deployment = FirstNonEmpty(
            Env("AZURE_OPENAI_CHAT_DEPLOYMENT"),
            Env("AZURE_OPENAI_DEPLOYMENT"),
            DefaultDeployment),
    };

    private static string Env(string key) => Environment.GetEnvironmentVariable(key) ?? "";

    private static string FirstNonEmpty(params string[] values)
    {
        foreach (var v in values)
            if (!string.IsNullOrWhiteSpace(v)) return v;
        return DefaultDeployment;
    }
}
