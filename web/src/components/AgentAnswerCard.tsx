import { useStore } from "../store";
import type { Cascade } from "../types";

// The compact "Blast Radius card" — the format the Aura Agent replies with (the primary agent surface),
// mirrored here so the web app and the agent answer look like one product.
export default function AgentAnswerCard() {
  const cascade = useStore((s) => s.cascade);
  if (!cascade) return null;
  const e = cascade.event;
  // non-tradable conduits propagate but are never scored — rank only price-scored companies
  const ranked = cascade.nodes.filter((n) => n.tradable).sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));
  const top = ranked[0];
  const top5 = ranked.slice(0, 5);
  // the "surprise" = the strongest mover that's 2+ hops out (the non-obvious one)
  const surprise = ranked.find((n) => n.hop >= 2) ?? ranked.find((n) => n.hop >= 1) ?? top;

  return (
    <div className="agent-card">
      <div className="agent-h">
        <span className="agent-badge">◈ BLAST RADIUS</span>
        <span className={`regime ${e.regime}`}>{e.regime === "contagion" ? "◍ CONTAGION" : "◐ SUBSTITUTION"}</span>
      </div>
      <div className="agent-verdict">
        <b>{ranked.length}</b> in range · <b>{top?.band}</b> at hop {top?.hop} · severity {e.severity}
      </div>
      <div className="agent-top">
        {top5.map((n) => (
          <div key={n.id} className={`agent-row ${n.direction}`}>
            <span className="tk">{n.id}</span>
            <span className="b">{n.band}</span>
            <span className="v">{n.impact >= 0 ? "+" : ""}{n.impact.toFixed(2)}</span>
          </div>
        ))}
      </div>
      <div className="agent-path">
        <span className="lbl">path</span> {surprise.path}
      </div>
      <div className="agent-conf">
        confidence {Math.round((top?.confidence ?? 0) * 100)}% at the epicenter, decaying per hop ·{" "}
        <span className="honest">reach + the explained path, not a price call</span>
      </div>
    </div>
  );
}
