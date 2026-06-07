import { useEffect, useState } from "react";
import { useStore } from "../store";
import type { Cascade } from "../types";

// The backend base URL: injected by Aspire (VITE_API_URL), or the API's standalone default.
const API = (import.meta.env.VITE_API_URL as string | undefined) || "http://localhost:5179";

// U10 — "what you're seeing", in plain English. The DEFAULT text is generated DETERMINISTICALLY from the
// cascade (a template, not an LLM) so it always works offline. "Explain with AI" upgrades THIS SAME card to
// a live LLM read via the agent/API — clearly badged so the two sources are never confused.
function explain(c: Cascade): string[] {
  const ev = c.event;
  const tradable = c.nodes.filter((n) => n.tradable);
  const byImpact = [...tradable].sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));
  const epicenter = c.nodes.filter((n) => n.hop === 0);
  const losers = byImpact.filter((n) => n.direction === "loss").slice(0, 3);
  const winners = byImpact.filter((n) => n.direction === "gain").slice(0, 2);
  const surprise = byImpact.find((n) => n.hop >= 2) ?? winners.find((n) => n.hop >= 1);
  const reached = c.meta?.reached ?? tradable.length;
  const paras: string[] = [];

  paras.push(
    `The news: "${ev.headline}". ` +
      (ev.scope === "company"
        ? `It lands directly on ${epicenter.map((n) => n.id).slice(0, 3).join(", ")}, `
        : `It's a ${ev.scope}-level shock that seeds the most exposed companies first, `) +
      `and MarketMind follows it through the dependency graph to ${reached} companies in range.`
  );

  paras.push(
    ev.regime === "contagion"
      ? `This is a CONTAGION event — a broad sector or macro shock. Rivals don't benefit here; they fall together, so the whole neighbourhood darkens at once.`
      : `This is a SUBSTITUTION event — a company-specific stumble. That can actually help direct rivals, who pick up the slack, so a few names turn green even as the epicenter drops.`
  );

  if (losers.length) {
    const top = losers[0];
    paras.push(
      `Hardest hit: ${losers.map((n) => n.id).join(", ")}. Take ${top.id} — the impact reaches it along ${top.path || top.id}, fading at each hop, because a supplier's pain is only partly its customer's pain.`
    );
  }

  if (surprise && surprise.direction === "gain") {
    paras.push(
      `The non-obvious read: ${surprise.name} (${surprise.id}), ${surprise.hop} hop${surprise.hop === 1 ? "" : "s"} out, actually benefits — exactly the kind of name a headline would never mention.`
    );
  } else if (winners.length) {
    paras.push(`Quiet winners: ${winners.map((n) => n.id).join(", ")} — they gain ground while rivals stumble.`);
  }

  paras.push(
    `Read this as exposure and the explained path, not a price call. The bands are relative structural exposure; the Time Machine shows what actually happened, our misses included.`
  );
  return paras;
}

export default function ExplainerCard() {
  const cascade = useStore((s) => s.cascade);
  const eventId = useStore((s) => s.eventId);
  const [ai, setAi] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setAi(null);
    setError(null);
  }, [eventId]); // reset whenever the event changes

  if (!cascade) return null;
  const paras = explain(cascade);

  const askAI = async () => {
    if (!eventId) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/api/explain/${eventId}`);
      if (!r.ok) throw new Error(r.status === 503 ? "agent-off" : `http-${r.status}`);
      const j = await r.json();
      setAi(j.answer ?? "");
    } catch {
      setError("Live AI needs the backend running (Aspire / MarketMind.Api). Showing the auto-summary.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="explainer panel">
      <h3>
        Plain English · what you're seeing
        <span className={`xp-src ${ai ? "ai" : ""}`}>{ai ? "live AI" : "auto-summary · not AI"}</span>
      </h3>
      <div className="explainer-body">
        {ai
          ? ai.split("\n").map((l) => l.trim()).filter(Boolean).map((line, i) => <p key={i}>{line}</p>)
          : paras.map((p, i) => <p key={i}>{p}</p>)}
        {error && <p className="xp-err">{error}</p>}
      </div>
      <div className="explainer-foot">
        {ai ? (
          <a className="xp-btn" onClick={() => setAi(null)}>↺ back to auto-summary</a>
        ) : (
          <a className="xp-btn" onClick={askAI}>{loading ? "thinking…" : "✨ Explain with AI"}</a>
        )}
        <span className="xp-note"> auto-summary = deterministic from the graph · AI = the live agent</span>
      </div>
    </div>
  );
}
