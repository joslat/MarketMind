using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace MarketMind.Backend;

/// <summary>
/// Calls the hosted Neo4j Aura Agent over HTTPS. Two-step: OAuth client-credentials
/// token from api.neo4j.io, then POST {"input": question} to the copied agent endpoint. The deterministic
/// numbers are recovered from the `cypher_template_tool_result` blocks, not the LLM prose.
///
/// READY but INERT until configured: with no endpoint/credentials it throws a clear, actionable error.
/// The live wiring is a MANUAL walkthrough (provisioning + API keys are human-only).
///
/// The response envelope field names are UNVERIFIED against a live call (no public OpenAPI), so parsing
/// is defensive: anything unrecognised degrades to the prose text rather than throwing.
/// </summary>
public sealed class AuraAgentBackend : IMarketMindBackend
{
    private readonly HttpClient _http;
    private readonly MarketMindOptions _opt;
    private string? _token;
    private DateTimeOffset _tokenExpiry = DateTimeOffset.MinValue;

    public string Name => "aura";

    public AuraAgentBackend(HttpClient http, MarketMindOptions opt)
    {
        _http = http;
        _opt = opt;
    }

    public async Task<IReadOnlyList<ImpactRow>> CascadeAsync(string newsId, bool tradableOnly = true, CancellationToken ct = default)
    {
        // Nudge the ReAct agent to its impact_cascade tool; we then read the structured rows it returns.
        var q = $"Use impact_cascade for newsId '{newsId}' with tradableOnly={tradableOnly.ToString().ToLowerInvariant()}. " +
                "Return the ranked exposures.";
        var answer = await AskAsync(q, ct).ConfigureAwait(false);
        return answer.Rows;
    }

    public async Task<AgentAnswer> AskAsync(string question, CancellationToken ct = default)
    {
        EnsureConfigured();
        var token = await GetTokenAsync(ct).ConfigureAwait(false);

        using var req = new HttpRequestMessage(HttpMethod.Post, _opt.AuraEndpointUrl);
        req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
        req.Headers.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
        req.Content = new StringContent(
            JsonSerializer.Serialize(new { input = question }), Encoding.UTF8, "application/json");

        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var raw = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            throw new HttpRequestException($"Aura agent returned {(int)resp.StatusCode}: {Truncate(raw, 300)}");

        return ParseEnvelope(raw);
    }

    // ---- OAuth client-credentials (Basic clientId:secret) → bearer; cache ~55 min, refresh on expiry ----
    private async Task<string> GetTokenAsync(CancellationToken ct)
    {
        if (_token is not null && DateTimeOffset.UtcNow < _tokenExpiry) return _token;

        using var req = new HttpRequestMessage(HttpMethod.Post, _opt.AuraTokenUrl);
        var basic = Convert.ToBase64String(Encoding.ASCII.GetBytes($"{_opt.AuraClientId}:{_opt.AuraClientSecret}"));
        req.Headers.Authorization = new AuthenticationHeaderValue("Basic", basic);
        req.Content = new FormUrlEncodedContent(new[] { new KeyValuePair<string, string>("grant_type", "client_credentials") });

        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var raw = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            throw new HttpRequestException($"Aura OAuth token returned {(int)resp.StatusCode}: {Truncate(raw, 300)}");

        using var doc = JsonDocument.Parse(raw);
        var r = doc.RootElement;
        _token = r.GetProperty("access_token").GetString();
        int ttl = r.TryGetProperty("expires_in", out var e) && e.TryGetInt32(out var s) ? s : 3600;
        _tokenExpiry = DateTimeOffset.UtcNow.AddSeconds(Math.Max(60, ttl - 300)); // refresh 5 min early
        return _token!;
    }

    // ---- defensive envelope parse: pull tool-result rows + the final text out of content[] ----
    private static AgentAnswer ParseEnvelope(string raw)
    {
        string text = "";
        string? regime = null;
        var rows = new List<ImpactRow>();
        try
        {
            using var doc = JsonDocument.Parse(raw);
            if (doc.RootElement.TryGetProperty("content", out var content) && content.ValueKind == JsonValueKind.Array)
            {
                foreach (var block in content.EnumerateArray())
                {
                    var type = block.TryGetProperty("type", out var t) ? t.GetString() : null;
                    if (type == "text" && block.TryGetProperty("text", out var tx))
                        text += tx.GetString();
                    else if (type is "cypher_template_tool_result" && block.TryGetProperty("output", out var output))
                        rows.AddRange(ReadRows(output));
                }
            }
            else if (doc.RootElement.TryGetProperty("text", out var tx))
            {
                text = tx.GetString() ?? "";
            }
        }
        catch (JsonException)
        {
            text = raw; // not JSON we recognise — surface it rather than throw
        }
        if (rows.Count > 0) regime = null; // regime isn't a projected column; leave to the card/Local backend
        return new AgentAnswer(text.Trim(), rows, regime, "aura");
    }

    private static IEnumerable<ImpactRow> ReadRows(JsonElement output)
    {
        // tolerate output.records[], output.data[], or output itself being an array of row-objects
        JsonElement arr = default;
        bool have =
            (output.ValueKind == JsonValueKind.Array && (arr = output).ValueKind == JsonValueKind.Array) ||
            (output.TryGetProperty("records", out arr) && arr.ValueKind == JsonValueKind.Array) ||
            (output.TryGetProperty("data", out arr) && arr.ValueKind == JsonValueKind.Array);
        if (!have) yield break;

        foreach (var rec in arr.EnumerateArray())
        {
            if (rec.ValueKind != JsonValueKind.Object) continue;
            string? ticker = Str(rec, "ticker");
            if (ticker is null) continue;
            double impact = Num(rec, "impact");
            yield return new ImpactRow(
                ticker, Str(rec, "name") ?? ticker, Bool(rec, "tradable"),
                impact, Str(rec, "direction") ?? (impact >= 0 ? "gain" : "loss"),
                (int)Num(rec, "hop"), Str(rec, "path") ?? ticker);
        }
    }

    private static string? Str(JsonElement o, string k) =>
        o.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.String ? v.GetString() : null;
    private static double Num(JsonElement o, string k) =>
        o.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number ? v.GetDouble() : 0;
    private static bool Bool(JsonElement o, string k) =>
        o.TryGetProperty(k, out var v) && (v.ValueKind == JsonValueKind.True || v.ValueKind == JsonValueKind.False) && v.GetBoolean();

    private void EnsureConfigured()
    {
        if (!_opt.AuraConfigured)
            throw new InvalidOperationException(
                "AuraAgentBackend is not configured. Set MarketMind:AuraEndpointUrl / AuraClientId / AuraClientSecret " +
                "(the live connection is a manual walkthrough). " +
                "Until then use MarketMind:Backend=Local.");
    }

    private static string Truncate(string s, int n) => s.Length <= n ? s : s[..n] + "…";
}
