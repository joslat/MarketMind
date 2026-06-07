import { useEffect, useMemo, useRef, useState } from "react";
import type { MutableRefObject } from "react";
import ForceGraph2D from "react-force-graph-2d";
import type { Cascade, CascadeNode } from "../types";
import { tweenedImpact, reducedMotion } from "../cascadePlayer";
import { useStore } from "../store";
import { project, drawBasemap, REGIONS } from "../basemap";

const GAIN = "#3fb950";
const LOSS = "#ff4d4f";
const DORMANT = "#5a6472";
const FLARE = "#f5f7fa";
const SELECT = "#ffd24d";        // drill-down selection / strongest-path highlight
const CONF_LOW = 0.45;           // below this, direction is uncertain -> render hollow

function lerpColor(mag: number, gain: boolean) {
  // dormant -> gain/loss as magnitude grows
  if (mag < 0.02) return DORMANT;
  return gain ? GAIN : LOSS;
}

// the strongest-path chain of a node, as a set of unordered "A|B" edge keys (for highlight/isolate)
function pairKey(a: string, b: string) {
  return a < b ? `${a}|${b}` : `${b}|${a}`;
}

export default function GraphCanvas({
  cascade,
  fgRef,
  geo = false,
  onNodeClick,
}: {
  cascade: Cascade;
  fgRef: MutableRefObject<any>;
  geo?: boolean;
  onNodeClick?: (n: CascadeNode) => void;
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 800, h: 600 });
  const selected = useStore((s) => s.selected);
  const setSelected = useStore((s) => s.setSelected);

  // GRAPH <-> MAP: pin nodes to their projected lat/lng (geo) or release to the force layout.
  // MAP de-overlap (U2): companies in the same city project to one point, so we spread co-located
  // nodes in a deterministic phyllotaxis (sunflower) spiral around the city centroid — legible,
  // still in-metro, and stable for screenshots.
  useEffect(() => {
    if (geo) {
      const groups = new Map<string, any[]>();
      cascade.nodes.forEach((n: any) => {
        if (n.lat == null || n.lng == null) { n.fx = undefined; n.fy = undefined; return; }
        const [x, y] = project(n.lng, n.lat);
        const key = `${Math.round(x / 2)}_${Math.round(y / 2)}`;   // ~same city
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key)!.push(n);
      });
      const GOLDEN = Math.PI * (3 - Math.sqrt(5));
      groups.forEach((members) => {
        members.sort((a, b) => (a.id < b.id ? -1 : 1));            // deterministic placement
        members.forEach((n, i) => {
          const [px, py] = project(n.lng, n.lat);
          if (members.length === 1) { n.fx = px; n.fy = py; return; }
          const rr = 3.6 * Math.sqrt(i);                           // sunflower radius
          n.fx = px + rr * Math.cos(i * GOLDEN);
          n.fy = py + rr * Math.sin(i * GOLDEN);
        });
      });
    } else {
      cascade.nodes.forEach((n: any) => { n.fx = undefined; n.fy = undefined; });
    }
    fgRef.current?.d3ReheatSimulation?.();
    const t = setTimeout(() => fgRef.current?.zoomToFit?.(700, geo ? 40 : 70), 480);
    return () => clearTimeout(t);
  }, [geo, cascade, fgRef]);

  const data = useMemo(() => ({ nodes: cascade.nodes, links: cascade.links }), [cascade]);

  // strongest-path of the drilled-in node: the chain of edge keys + the node set on it (for isolate/highlight)
  const { pathPairs, pathNodes } = useMemo(() => {
    const pairs = new Set<string>();
    const nodes = new Set<string>();
    if (selected) {
      const node = cascade.nodes.find((n) => n.id === selected);
      const chain = node?.path ? node.path.split(" → ").map((s) => s.trim()) : [];
      chain.forEach((t) => nodes.add(t));
      for (let i = 0; i < chain.length - 1; i++) pairs.add(pairKey(chain[i], chain[i + 1]));
      nodes.add(selected);
    }
    return { pathPairs: pairs, pathNodes: nodes };
  }, [selected, cascade]);

  const onPath = (l: any) => {
    const s = l.source.id ?? l.source;
    const t = l.target.id ?? l.target;
    return pathPairs.has(pairKey(s, t));
  };

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    const t = setTimeout(() => fgRef.current?.zoomToFit?.(600, 70), 450);
    return () => clearTimeout(t);
  }, [cascade, fgRef, size.w, size.h]);

  return (
    <div ref={wrapRef} className="graph-wrap" style={{ width: "100%", height: "100%" }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={data}
        backgroundColor="#0a0e14"
        width={size.w}
        height={size.h}
        cooldownTicks={Infinity}
        d3AlphaDecay={0.04}
        d3VelocityDecay={0.35}
        nodeRelSize={4}
        linkCurvature={geo ? 0.12 : 0}  /* gentler arcs so links hug the geography (U: map polish) */
        onRenderFramePre={(ctx: CanvasRenderingContext2D) => {
          if (geo) drawBasemap(ctx);
        }}
        onRenderFramePost={(ctx: CanvasRenderingContext2D, scale: number) => {
          if (!geo) return;
          // region labels (faint, geo-biased read)
          ctx.font = `600 ${10 / scale}px Inter, sans-serif`;
          ctx.fillStyle = "rgba(125,138,160,0.5)";
          ctx.textAlign = "center";
          REGIONS.forEach((rg) => {
            const [x, y] = project(rg.lng, rg.lat);
            ctx.fillText(rg.label, x, y);
          });
          // epicenter detonation pulse
          const g = cascade.event.geo;
          if (g) {
            const [x, y] = project(g.lng, g.lat);
            const t = (performance.now() % 1600) / 1600;
            ctx.strokeStyle = `rgba(245,247,250,${0.5 * (1 - t)})`;
            ctx.lineWidth = 1.5 / scale;
            ctx.beginPath();
            ctx.arc(x, y, 4 + t * 22, 0, 2 * Math.PI);
            ctx.stroke();
            ctx.fillStyle = "#f5f7fa";
            ctx.beginPath();
            ctx.arc(x, y, 2.4, 0, 2 * Math.PI);
            ctx.fill();
          }
        }}
        nodeLabel={(n: any) =>
          `${n.id} · ${n.name}\n${n.band} (${n.impact >= 0 ? "+" : ""}${n.impact.toFixed(3)}) · hop ${n.hop} · conf ${Math.round((n.confidence ?? 0) * 100)}%\n${n.path}` +
          (n.actual !== undefined ? `\nactual ${n.actual >= 0 ? "+" : ""}${n.actual}%  ${n.hit ? "✓" : "✗"}` : "")}
        linkLabel={(l: any) =>
          `${(l.source.id ?? l.source)} —${l.type}→ ${(l.target.id ?? l.target)} · w=${l.weight} · source: ${l.source_ref ?? "public"}`}
        onNodeClick={(n: any) => onNodeClick?.(n)}
        onBackgroundClick={() => setSelected(null)}
        linkColor={(l: any) => {
          if (selected) return onPath(l) ? "rgba(255,210,77,0.85)" : "rgba(28,37,51,0.5)"; // isolate the drilled path
          if (!l.__active) return "#1c2533";
          return l.sign >= 0 ? "rgba(63,185,80,0.55)" : "rgba(255,77,79,0.55)";
        }}
        linkWidth={(l: any) => {
          if (selected) return onPath(l) ? 2.2 : 0.3;
          return l.__active ? 0.5 + l.magnitude * 4 : 0.4;
        }}
        // dashed = speculative far-hop propagation (confidence decays with distance); solid = direct/near
        linkLineDash={(l: any) => (l.hop >= 2 ? [3, 3] : null)}
        // U9: a CONTINUOUS, slow, admirable flow of impact along active links (more on the drilled path).
        linkDirectionalParticles={(l: any) => (l.__active ? (selected ? (onPath(l) ? 4 : 0) : 3) : 0)}
        linkDirectionalParticleWidth={(l: any) => (3.5 + l.magnitude * 7) / (1 + l.hop * 0.25)}
        linkDirectionalParticleSpeed={(l: any) => 0.006 / (1 + l.hop * 0.4)} // slow — watch it travel, slower each hop out
        linkDirectionalParticleColor={(l: any) => (l.sign >= 0 ? GAIN : LOSS)}
        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, scale: number) => {
          const now = performance.now();
          const cur = tweenedImpact(node as CascadeNode, now);
          const mag = Math.abs(cur);
          const gain = cur >= 0;
          // non-tradable nodes are CONDUITS: they propagate impact but are never price-scored,
          // so they render neutral (no green/red, no glow) — never as a "winner/loser".
          const conduit = !node.tradable;
          const col = conduit ? DORMANT : lerpColor(mag, gain);

          // ignition pop (scale 1 -> 1.6 -> 1.1 over ~320ms)
          let pop = 1;
          if (node.__ignite && !reducedMotion) {
            const e = (now - node.__ignite) / 320;
            if (e < 1) pop = 1 + Math.sin(Math.min(1, e) * Math.PI) * 0.6;
            else pop = 1.1;
          }
          // ~half the previous size (U3): less clutter, force-layout spacing unchanged
          const r = (1.3 + mag * 4.5 + (node.hop === 0 ? 1 : 0)) * pop;

          // drill-down isolate: dim everything not on the selected node's strongest path
          const dim = selected != null && !pathNodes.has(node.id);
          ctx.save();
          if (dim) ctx.globalAlpha = 0.22;

          // confidence: below CONF_LOW the DIRECTION is uncertain -> render HOLLOW
          const lowConf = !conduit && (node.confidence ?? 1) < CONF_LOW;

          // glow bloom (scored, confident companies only — uncertain names don't get a confident halo)
          if (!conduit && !lowConf && mag > 0.04) {
            const g = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, r * 3.2);
            g.addColorStop(0, gain ? "rgba(63,185,80,0.40)" : "rgba(255,77,79,0.40)");
            g.addColorStop(1, "rgba(0,0,0,0)");
            ctx.fillStyle = g;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r * 3.2, 0, 2 * Math.PI);
            ctx.fill();
          }

          // node body — solid when confident; hollow (faint fill + dashed ring) when direction is uncertain
          ctx.beginPath();
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
          if (lowConf) {
            ctx.fillStyle = gain ? "rgba(63,185,80,0.18)" : "rgba(255,77,79,0.18)";
            ctx.fill();
            ctx.setLineDash([2.5, 2.5]);
            ctx.strokeStyle = col;
            ctx.lineWidth = 1.4 / scale;
            ctx.stroke();
            ctx.setLineDash([]);
          } else {
            ctx.fillStyle = col;
            ctx.fill();
          }

          // source flare ring (hop 0)
          if (node.hop === 0) {
            ctx.strokeStyle = FLARE;
            ctx.lineWidth = 1.2 / scale;
            ctx.stroke();
          }

          // drill-down: bright selection ring on the node the user clicked
          if (selected === node.id) {
            ctx.setLineDash([]);
            ctx.strokeStyle = SELECT;
            ctx.lineWidth = 2.2 / scale;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
            ctx.stroke();
          }
          ctx.restore();

          // label (tickers; bigger nodes always, others when zoomed) — ~half size (U3)
          if (r > 3 || scale > 1.6) {
            const fs = Math.max(5, 6 / scale);
            ctx.font = `600 ${fs}px "JetBrains Mono", monospace`;
            ctx.fillStyle = "#c9d4e3";
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillText(node.id, node.x, node.y + r + 1);
          }

          // Time Machine: reveal realized abnormal return + ✓/✗ on scored nodes
          if (useStore.getState().revealActuals && node.actual !== undefined) {
            const hit = node.hit;
            ctx.strokeStyle = hit ? GAIN : LOSS;
            ctx.lineWidth = 1.6 / scale;
            ctx.beginPath();
            ctx.arc(node.x, node.y, r + 2, 0, 2 * Math.PI);
            ctx.stroke();
            const fs = Math.max(5, 6 / scale);
            ctx.font = `600 ${fs}px "JetBrains Mono", monospace`;
            ctx.fillStyle = hit ? GAIN : LOSS;
            ctx.textAlign = "center";
            ctx.textBaseline = "bottom";
            ctx.fillText(`${hit ? "✓" : "✗"} ${node.actual >= 0 ? "+" : ""}${node.actual}%`, node.x, node.y - r - 2);
          }
        }}
        nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
          ctx.fillStyle = color;
          ctx.beginPath();
          ctx.arc(node.x, node.y, 6, 0, 2 * Math.PI);   // smaller hit area to match the smaller nodes (U3)
          ctx.fill();
        }}
      />
      <div className="graph-legend">
        <span><i className="lg-solid" /> confident</span>
        <span><i className="lg-hollow" /> direction uncertain</span>
        <span><i className="lg-dash" /> speculative hop</span>
        <span><i className="lg-conduit" /> conduit (not scored)</span>
        {selected && <span className="lg-clear" onClick={() => setSelected(null)}>● {selected} — click empty space to clear</span>}
      </div>
    </div>
  );
}
