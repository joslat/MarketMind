using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;

namespace MarketMind.Backend;

/// <summary>
/// Runs the cascade against a Neo4j graph over its HTTP <b>Query API</b> (<c>/db/{db}/query/v2</c>),
/// authenticating with the ordinary database login (basic auth). One class drives BOTH data modes —
/// only the URL + credentials differ:
///   • Local : the local Neo4j (http://localhost:7474, login from MM_LOCAL_NEO4J_PASSWORD)
///   • Aura  : the remote Aura graph (https://{id}.databases.neo4j.io, the DB login)
/// It executes the exact <c>impact_cascade</c> Cypher the hosted Aura agent registers (from cypher/05),
/// so the rows are identical to the in-proc engine, sign-for-sign — just computed in the DB.
/// </summary>
public sealed class QueryApiBackend : IMarketMindBackend
{
    private readonly HttpClient _http;
    private readonly string _queryUrl;
    private readonly string _cascadeCypher;

    public string Name { get; }

    public QueryApiBackend(HttpClient http, string queryUrl, string user, string password, string cascadeCypher, string name)
    {
        _http = http;
        _queryUrl = queryUrl;
        _cascadeCypher = cascadeCypher;
        Name = name;
        var basic = Convert.ToBase64String(Encoding.ASCII.GetBytes($"{user}:{password}"));
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Basic", basic);
        if (!_http.DefaultRequestHeaders.Accept.Any())
            _http.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
    }

    public async Task<IReadOnlyList<ImpactRow>> CascadeAsync(string newsId, bool tradableOnly = true, CancellationToken ct = default)
    {
        var payload = JsonSerializer.Serialize(new { statement = _cascadeCypher, parameters = new { newsId, tradableOnly } });
        using var req = new HttpRequestMessage(HttpMethod.Post, _queryUrl)
        {
            Content = new StringContent(payload, Encoding.UTF8, "application/json"),
        };
        using var resp = await _http.SendAsync(req, ct).ConfigureAwait(false);
        var raw = await resp.Content.ReadAsStringAsync(ct).ConfigureAwait(false);
        if (!resp.IsSuccessStatusCode)
            throw new HttpRequestException($"Query API ({Name}) returned {(int)resp.StatusCode}: {Truncate(raw, 300)}");
        return ParseRows(raw);
    }

    /// <summary>The Query API runs Cypher only — free-form NL routing is the hosted Aura agent's job.</summary>
    public Task<AgentAnswer> AskAsync(string question, CancellationToken ct = default) =>
        throw new NotSupportedException("QueryApiBackend has no NL router — that is the hosted Aura agent. Use CascadeAsync.");

    // Neo4j Query API v2 shape: { "data": { "fields": [...], "values": [[...],[...]] }, ... }
    private static IReadOnlyList<ImpactRow> ParseRows(string raw)
    {
        using var doc = JsonDocument.Parse(raw);
        var data = doc.RootElement.GetProperty("data");
        var fields = data.GetProperty("fields").EnumerateArray().Select(f => f.GetString()!).ToList();
        int Idx(string n) => fields.IndexOf(n);
        int iT = Idx("ticker"), iN = Idx("name"), iTr = Idx("tradable"), iI = Idx("impact"), iD = Idx("direction"), iH = Idx("hop"), iP = Idx("path");

        var rows = new List<ImpactRow>();
        foreach (var row in data.GetProperty("values").EnumerateArray())
        {
            string S(int i) => i < 0 ? "" : row[i].ValueKind == JsonValueKind.String ? row[i].GetString()! : row[i].ToString();
            rows.Add(new ImpactRow(
                Ticker: S(iT),
                Name: S(iN),
                Tradable: iTr >= 0 && row[iTr].ValueKind == JsonValueKind.True,
                Impact: iI >= 0 ? row[iI].GetDouble() : 0,
                Direction: S(iD),
                Hop: iH >= 0 ? row[iH].GetInt32() : 0,
                Path: S(iP)));
        }
        return rows;
    }

    // Single source of truth: the same inlined-weight impact_cascade body cypher/05 registers as the Aura tool.
    public static string LoadImpactCascade(string root)
    {
        var path = Path.Combine(root, "cypher", "05-aura-tools.cypher");
        var lines = File.ReadAllText(path).Replace("\r\n", "\n").Split('\n');
        var buf = new List<string>();
        bool inTool = false, inHeader = false;
        foreach (var l in lines)
        {
            if (l.StartsWith("// TOOL:")) { inTool = l.Contains("impact_cascade"); inHeader = inTool; continue; }
            if (inHeader) { if (l.StartsWith("// ─") || l.StartsWith("// -")) inHeader = false; continue; }
            if (inTool) { if (l.StartsWith("//")) break; buf.Add(l); }
        }
        var body = string.Join("\n", buf).Trim().TrimEnd(';').Trim();
        if (body.Length == 0) throw new InvalidOperationException($"impact_cascade not found in {path}");
        return body;
    }

    private static string Truncate(string s, int n) => s.Length <= n ? s : s[..n];
}
