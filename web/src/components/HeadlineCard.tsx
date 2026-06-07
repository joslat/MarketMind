import type { Cascade } from "../types";

// Tone restraint: events with real human stakes (disasters, conflict) get a
// one-line note so the market visualization never reads as celebrating a tragedy.
const HUMAN_STAKES = /\b(earthquake|quake|strait|war|conflict|invasion|flood|typhoon|tsunami|attack|disaster)\b/i;

export default function HeadlineCard({ cascade }: { cascade: Cascade }) {
  const e = cascade.event;
  const sensitive = e.category === "geopolitical" || HUMAN_STAKES.test(e.headline);
  return (
    <div className="headline-card">
      <div className="meta">
        {e.date} · {e.category} · {cascade.meta.reached} names reached
      </div>
      <div className="hl">{e.headline}</div>
      {sensitive && (
        <div className="restraint">⚑ A real event with human stakes — we model only the market's structural echo, not its cost in lives.</div>
      )}
    </div>
  );
}
