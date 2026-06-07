import { useStore } from "../store";
import Tip from "./Tip";

// Top-bar blast-severity gauge: how hard the event hits, bound to event.severity (0..1).
export default function BlastSeverityGauge() {
  const cascade = useStore((s) => s.cascade);
  if (!cascade) return null;
  const sev = Math.max(0, Math.min(1, cascade.event.severity ?? 0));
  const reached = cascade.meta?.reached ?? cascade.nodes.length;
  const tier = sev >= 0.8 ? "Severe" : sev >= 0.6 ? "High" : sev >= 0.35 ? "Moderate" : "Marginal";
  const tip = (
    <>
      <b>Blast severity</b> — how hard the event hits at the source (0–100%), banded
      Severe / High / Moderate / Marginal. It's the event's own shock magnitude, before the cascade
      fans it out. <b>{reached} in range</b> = how many companies the cascade touches at all.
    </>
  );
  return (
    <Tip tip={tip} pos="bottom" align="right" w={290}>
      <div className="blast-gauge">
        <span className="bg-label">BLAST</span>
        <span className="bg-track"><i style={{ width: `${Math.round(sev * 100)}%` }} className={`tier-${tier.toLowerCase()}`} /></span>
        <span className="bg-tier">{tier} · {reached} in range</span>
      </div>
    </Tip>
  );
}
