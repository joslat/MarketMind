namespace MarketMind.Engine;

/// <summary>
/// The single source-of-truth not-financial-advice disclaimer. Wired into every runtime surface
/// (agent system prompt, API response envelopes, README banner, UI) so the honesty claim is on the
/// record wherever output reaches a user. MarketMind models EXPOSURE + explained impact paths — it does
/// NOT predict prices. (The Apache-2.0 warranty disclaimer covers liability; this covers the separate
/// "not investment advice" layer it does not.)
/// </summary>
public static class Disclaimer
{
    /// <summary>One-liner for compact surfaces (agent closing line, API envelope field).</summary>
    public const string Short =
        "Research & education only — exposure, not prediction. Not investment advice; do not use on its own to trade.";

    /// <summary>The full statement (README banner, DISCLAIMER.md, API root).</summary>
    public const string Full =
        "MarketMind is a research & education project. It models EXPOSURE and explained impact paths through a " +
        "curated dependency graph — it does NOT predict prices and is NOT investment advice. On a held-out test " +
        "of 27 events it showed no demonstrated next-day directional edge (it ties a whole-sector baseline; ~47%, " +
        "within noise of chance). Its validated value is reach (surfacing non-headline movers) and an auditable " +
        "reasoning path — not a trading signal. Do not use MarketMind, on its own, to make buy or sell decisions. " +
        "Provided AS-IS, no warranty, no liability.";
}
