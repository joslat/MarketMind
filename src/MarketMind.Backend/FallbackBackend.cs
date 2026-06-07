using System.Net.Sockets;

namespace MarketMind.Backend;

/// <summary>
/// Wraps a primary (DB-backed) <see cref="IMarketMindBackend"/> with an in-proc fallback so /api/cascade
/// never hard-fails when the database is unreachable (not started, not seeded yet, network blip). The
/// fallback (<see cref="LocalCypherBackend"/>) runs the SAME calibrated engine, so the rows are identical
/// sign-for-sign — only the source differs.
///
/// Fallback fires ONLY on transport/connectivity failures (connection refused, DNS, timeout). Real domain
/// or configuration errors — an unknown event, an HTTP 401/500 from a misconfigured DB — propagate
/// unchanged, so a genuine misconfiguration still surfaces instead of being silently masked.
/// </summary>
public sealed class FallbackBackend : IMarketMindBackend
{
    private readonly IMarketMindBackend _primary;
    private readonly IMarketMindBackend _fallback;
    private int _warned;

    public FallbackBackend(IMarketMindBackend primary, IMarketMindBackend fallback)
    {
        _primary = primary;
        _fallback = fallback;
    }

    /// <summary>The primary's name — "local-db" or "aura-db" — so the UI badge still reflects the intended target.</summary>
    public string Name => _primary.Name;

    public async Task<IReadOnlyList<ImpactRow>> CascadeAsync(string newsId, bool tradableOnly = true, CancellationToken ct = default)
    {
        try
        {
            return await _primary.CascadeAsync(newsId, tradableOnly, ct).ConfigureAwait(false);
        }
        catch (Exception ex) when (!ct.IsCancellationRequested && IsTransport(ex))
        {
            if (Interlocked.Exchange(ref _warned, 1) == 0)
                Console.Error.WriteLine(
                    $"WARN: data backend '{_primary.Name}' unreachable ({ex.GetType().Name}: {ex.Message}). " +
                    "Falling back to the in-proc engine — identical rows, no DB. Start/seed the database to use it directly.");
            return await _fallback.CascadeAsync(newsId, tradableOnly, ct).ConfigureAwait(false);
        }
    }

    /// <summary>Natural-language routing is the primary's job (the hosted Aura agent); the in-proc engine has no router.</summary>
    public Task<AgentAnswer> AskAsync(string question, CancellationToken ct = default) => _primary.AskAsync(question, ct);

    // A connection-level failure (the DB is down/unreachable) — NOT an HTTP status error, which carries a
    // real server response and should surface. Walk the inner-exception chain to catch wrapped socket errors.
    private static bool IsTransport(Exception ex)
    {
        for (Exception? e = ex; e is not null; e = e.InnerException)
            if (e is SocketException or TaskCanceledException or TimeoutException)
                return true;
        return false;
    }
}
