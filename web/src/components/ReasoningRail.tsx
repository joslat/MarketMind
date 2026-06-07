import { useStore } from "../store";
import type { Cascade } from "../types";

function narrate(c: Cascade) {
  const steps: { text: string; dir: "gain" | "loss"; path?: string }[] = [];
  const byImpact = c.nodes.filter((n) => n.tradable).sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));

  const epicenter = c.nodes.filter((n) => n.hop === 0).sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact));
  if (epicenter.length) {
    steps.push({
      text:
        c.event.scope === "company"
          ? `Epicenter: ${epicenter.map((n) => n.id).slice(0, 4).join(", ")} take the direct hit.`
          : `${c.event.scope} shock seeds ${epicenter.length} exposed names one-way, then the structure carries it.`,
      dir: epicenter[0].direction,
    });
  }

  const downstream = byImpact.filter((n) => n.hop >= 1).slice(0, 3);
  downstream.forEach((n) =>
    steps.push({
      text: `${n.name} (${n.id}) ${n.direction === "loss" ? "darkens" : "lifts"} ${(n.impact >= 0 ? "+" : "") + n.impact.toFixed(2)} at hop ${n.hop}.`,
      dir: n.direction,
    })
  );

  // regime beat
  steps.push({
    text:
      c.event.regime === "contagion"
        ? "Regime: CONTAGION — sector-wide shock, rivals fall together (competitor inversion suppressed)."
        : "Regime: SUBSTITUTION — a firm-specific stumble; rivals can benefit (inversion active).",
    dir: c.event.regime === "contagion" ? "loss" : "gain",
  });

  // surprise: a non-obvious deeper mover with opposite sign to the epicenter, or a far hop
  const epiDir = epicenter[0]?.direction;
  const surprise =
    byImpact.find((n) => n.hop >= 2 && epiDir && n.direction !== epiDir) ||
    byImpact.find((n) => n.hop >= 3);
  if (surprise) {
    steps.push({
      text: `Surprise: ${surprise.name} (${surprise.id}) — ${surprise.direction === "gain" ? "benefits" : "exposed"} ${surprise.hop} hops out, the kind of name nobody would have named.`,
      dir: surprise.direction,
    });
  }
  return steps;
}

export default function ReasoningRail() {
  const cascade = useStore((s) => s.cascade);
  if (!cascade) return null;
  const steps = narrate(cascade);
  return (
    <div className="rail-why">
      <h3>Why</h3>
      {steps.map((s, i) => (
        <div className={`rail-step ${s.dir}`} key={i}>
          {s.text}
          {s.path && <div className="path">{s.path}</div>}
        </div>
      ))}
    </div>
  );
}
