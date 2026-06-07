import { useStore } from "../store";
import type { Cascade, CascadeLink } from "../types";

// Reconstruct the per-hop math along a node's strongest path (drill-down):
//   seed × [ factor(type,direction) × weight × hopDecay ] per hop → strongest-path contribution.
// The engine SUMS over all paths and clamps |impact|≤1, so this is the dominant path, not the only one.
function linkBetween(c: Cascade, a: string, b: string): CascadeLink | undefined {
  return c.links.find((l) => {
    const s = (l.source as any).id ?? l.source;
    const t = (l.target as any).id ?? l.target;
    return (s === a && t === b) || (s === b && t === a);
  });
}

function factorOf(type: string, supplierToCustomer: boolean, w: Record<string, number>, contagion: boolean) {
  switch (type) {
    case "SUPPLIES_TO": return supplierToCustomer ? (w.fSupDown ?? 0.6) : (w.fSupUp ?? 0.4);
    case "PARTNERS_WITH": return w.fPar ?? 0.5;
    case "OWNS": return w.fOwn ?? 0.55;
    case "COMPETES_WITH": return contagion ? 0 : -(w.fCmp ?? 0.35); // sign-flip, suppressed in contagion
    default: return 0.4;
  }
}

export default function DrillDownCard() {
  const cascade = useStore((s) => s.cascade);
  const selected = useStore((s) => s.selected);
  const setSelected = useStore((s) => s.setSelected);
  if (!cascade || !selected) return null;

  const node = cascade.nodes.find((n) => n.id === selected);
  if (!node) return null;

  const chain = node.path ? node.path.split(" → ").map((s) => s.trim()) : [selected];
  const w = cascade.meta?.weights ?? {};
  const hopDecay = w.hopDecay ?? 0.6;
  const contagion = cascade.event.regime === "contagion";
  const seed = cascade.nodes.find((n) => n.id === chain[0]);

  let running = seed?.impact ?? node.impact;
  const rows = [];
  for (let i = 0; i < chain.length - 1; i++) {
    const a = chain[i], b = chain[i + 1];
    const l = linkBetween(cascade, a, b);
    const type = l?.type ?? "—";
    const sId = l ? ((l.source as any).id ?? l.source) : a;
    const supplierToCustomer = sId === a; // traversing the stored supplier→customer direction
    const weight = type === "OWNS" ? (l?.weight ?? 0) / 100 : (l?.weight ?? 0.5);
    const factor = factorOf(type, supplierToCustomer, w, contagion);
    const mult = factor * weight * hopDecay;
    running *= mult;
    rows.push({ a, b, type, weight: l?.weight ?? 0, factor, mult, running });
  }

  return (
    <div className="drill">
      <div className="drill-head">
        <span className="drill-title">◇ DRILL-DOWN · {node.id}</span>
        <span className="drill-sub">{node.band} · conf {Math.round((node.confidence ?? 0) * 100)}% · hop {node.hop}</span>
        <a className="drill-x" onClick={() => setSelected(null)} title="close">×</a>
      </div>

      {chain.length <= 1 ? (
        <div className="drill-direct">Direct hit at the epicenter — no upstream path. Final impact{" "}
          <b className={node.direction}>{node.impact >= 0 ? "+" : ""}{node.impact.toFixed(3)}</b>.</div>
      ) : (
        <div className="drill-chain">
          <div className="drill-seed">
            <b>{chain[0]}</b> seed <span className={(seed?.direction) ?? "loss"}>
              {(seed?.impact ?? 0) >= 0 ? "+" : ""}{(seed?.impact ?? node.impact).toFixed(3)}</span>
          </div>
          {rows.map((r, i) => (
            <div className="drill-hop" key={i}>
              <span className="dh-edge">└ {r.type}<i>w={r.weight}{r.type === "OWNS" ? "%" : ""}</i></span>
              <span className="dh-math">×{r.factor.toFixed(2)} · ×{(cascade.meta?.weights?.hopDecay ?? 0.6).toFixed(2)} decay</span>
              <span className="dh-to">→ <b>{r.b}</b></span>
              <span className={`dh-run ${r.running >= 0 ? "gain" : "loss"}`}>
                {r.running >= 0 ? "+" : ""}{r.running.toFixed(3)}</span>
            </div>
          ))}
        </div>
      )}

      <div className="drill-final">
        Final <b className={node.direction}>{node.impact >= 0 ? "+" : ""}{node.impact.toFixed(3)}</b>
        <span className="drill-note">strongest path shown; the engine sums all paths and clamps |impact|≤1</span>
      </div>
      {node.actual !== undefined && (
        <div className="drill-actual">
          realized <b className={(node.actual ?? 0) >= 0 ? "gain" : "loss"}>
            {(node.actual ?? 0) >= 0 ? "+" : ""}{node.actual}%</b> · {node.hit ? "✓ direction right" : "✗ direction missed"}
        </div>
      )}
    </div>
  );
}
