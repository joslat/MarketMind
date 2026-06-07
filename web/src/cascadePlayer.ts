import type { MutableRefObject } from "react";
import type { Cascade, CascadeNode } from "./types";

export const STEP = 850; // ms per hop

// honor prefers-reduced-motion: drop particles + pop, keep color/number
export const reducedMotion =
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

interface LedgerRow {
  id: string;
  name: string;
  impact: number;
  direction: "gain" | "loss";
  band: string;
  hop: number;
}

function ledgerThroughHop(cascade: Cascade, hop: number): LedgerRow[] {
  return cascade.nodes
    // non-tradable nodes PROPAGATE but are never price-scored, so they never enter the ranking
    .filter((n) => n.tradable && n.hop <= hop && Math.abs(n.impact) > 0)
    .sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))
    .map((n) => ({ id: n.id, name: n.name, impact: n.impact, direction: n.direction, band: n.band, hop: n.hop }));
}

/**
 * Drive the structure×time wave: at hop h (t = h*STEP) ignite hop-h nodes and
 * emit particles along the links entering hop h. Returns a cancel fn.
 */
export function playCascade(
  cascade: Cascade,
  fgRef: MutableRefObject<any>,
  onLedger: (rows: LedgerRow[]) => void
): () => void {
  cascade.nodes.forEach((n: CascadeNode) => {
    n.__cur = 0;
    n.__ignite = 0;
  });
  cascade.links.forEach((l) => (l.__active = false));

  const timers: number[] = [];
  const maxHop = Math.max(0, cascade.hops.length - 1);

  for (let h = 0; h <= maxHop; h++) {
    timers.push(
      window.setTimeout(() => {
        const ids = new Set(cascade.hops[h] || []);
        cascade.nodes.forEach((n) => {
          if (ids.has(n.id)) n.__ignite = performance.now();
        });
        const entering = cascade.links.filter((l) => l.hop === h);
        entering.forEach((l) => {
          l.__active = true;
          const fg = fgRef.current;
          if (fg && fg.emitParticle && !reducedMotion) {
            try {
              fg.emitParticle(l);
            } catch {
              /* link not yet resolved on first frame — harmless */
            }
          }
        });
        onLedger(ledgerThroughHop(cascade, h));
      }, h * STEP)
    );
  }
  return () => timers.forEach((t) => clearTimeout(t));
}

// ease-out tween of a node's displayed impact toward its final value after ignition
export function tweenedImpact(n: CascadeNode, nowMs: number): number {
  if (!n.__ignite) return 0;
  const k = Math.min(1, (nowMs - n.__ignite) / 650);
  const eased = 1 - Math.pow(1 - k, 3);
  n.__cur = n.impact * eased;
  return n.__cur;
}
