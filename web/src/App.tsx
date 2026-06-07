import { useEffect, useRef } from "react";
import { useStore, PLAYLIST } from "./store";
import { playCascade } from "./cascadePlayer";
import GraphCanvas from "./components/GraphCanvas";
import ImpactLedger from "./components/ImpactLedger";
import ReasoningRail from "./components/ReasoningRail";
import RegimeBadge from "./components/RegimeBadge";
import HeadlineCard from "./components/HeadlineCard";
import ControlDock from "./components/ControlDock";
import AgentAnswerCard from "./components/AgentAnswerCard";
import MetricsCard from "./components/MetricsCard";
import TimeMachineCard from "./components/TimeMachineCard";
import SignalFeed from "./components/SignalFeed";
import DrillDownCard from "./components/DrillDownCard";
import BlastSeverityGauge from "./components/BlastSeverityGauge";
import ImpactCurveCard from "./components/ImpactCurveCard";
import ExplainerCard from "./components/ExplainerCard";
import Tip from "./components/Tip";

export default function App() {
  const { index, cascade, eventId, playToken, cinematic, timeMachine, view, error, loadIndex, select, setLedger, replay,
    toggleCinematic, setReveal, toggleView, setSelected } = useStore();
  const fgRef = useRef<any>(null);
  if (import.meta.env.DEV) (window as any).fg = fgRef;   // dev-only: lets headless capture frame the graph (zoomToFit)
  const cancelRef = useRef<() => void>();

  // load the event index, then select the URL-hash event (shareable permalink) or the TSMC quake (the default)
  useEffect(() => {
    loadIndex().then(() => {
      const idx = useStore.getState().index;
      const hash = typeof window !== "undefined" ? decodeURIComponent(window.location.hash.slice(1)) : "";
      const start =
        idx.find((e) => e.id === hash) ||
        idx.find((e) => e.id === "evt_tsmc_quake_2024") ||
        idx[0];
      if (start) select(start.id);
    });
  }, [loadIndex, select]);

  // (re)play the wave whenever a cascade loads or replay is pressed
  useEffect(() => {
    if (!cascade) return;
    cancelRef.current?.();
    setLedger([]);
    setReveal(false);
    const t = setTimeout(() => {
      cancelRef.current = playCascade(cascade, fgRef, setLedger);
    }, 650); // let the layout settle + zoomToFit
    // Time Machine: after the wave settles, reveal the realized abnormal returns (✓/✗)
    const revealMs = 650 + (cascade.hops.length + 1) * 850 + 1200;
    const r = timeMachine ? window.setTimeout(() => setReveal(true), revealMs) : undefined;
    return () => {
      clearTimeout(t);
      if (r) clearTimeout(r);
      cancelRef.current?.();
    };
  }, [cascade, playToken, timeMachine, setLedger, setReveal]);

  // keyboard: space = replay · → = next event · r = replay · c = cinematic
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === " ") {
        e.preventDefault();
        replay();
      } else if (e.key === "ArrowRight") {
        const i = index.findIndex((x) => x.id === eventId);
        if (index.length) select(index[(i + 1) % index.length].id);
      } else if (e.key.toLowerCase() === "r") {
        replay();
      } else if (e.key.toLowerCase() === "c") {
        toggleCinematic();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, eventId, select, replay, toggleCinematic]);

  // cinematic mode: fullscreen + auto-advance through the curated playlist
  useEffect(() => {
    if (!cinematic) {
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      return;
    }
    document.documentElement.requestFullscreen?.().catch(() => {});
    let i = Math.max(0, PLAYLIST.indexOf(eventId ?? ""));
    select(PLAYLIST[i]);
    const adv = setInterval(() => {
      i = (i + 1) % PLAYLIST.length;
      select(PLAYLIST[i]);
    }, 9000);
    return () => clearInterval(adv);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cinematic]);

  return (
    <div className={`app${cinematic ? " cinematic" : ""}`}>
      <div className="topbar">
        <Tip pos="bottom" align="left" w={340} tip={
          <><b>MarketMind</b> drops a news event into a curated company-dependency graph
          (suppliers, customers, partners, owners, rivals) and traces where the impact travels,
          how strong it is at each hop, and <i>why</i> — including who quietly <b>benefits</b>.
          It's a reasoning + exposure engine, not a price predictor, and it's validated openly on real prices.</>
        }>
          <div className="brand">
            <span className="mark">◤</span> MARKETMIND
            <span className="sub">news → contagion on a dependency graph</span>
          </div>
        </Tip>
        <div style={{ flex: 1 }} />
        <Tip pos="bottom" align="center" w={300} tip={
          <><b>GRAPH</b> lays companies out by their dependency structure (a force-directed web) so you read the
          cascade's topology. <b>MAP</b> pins each company to its real-world HQ so you see the geography of the
          shock — e.g. a Taiwan quake rippling out to US and Korean names.</>
        }>
          <div className="view-toggle">
            <a className={view === "graph" ? "on" : ""} onClick={() => view !== "graph" && toggleView()}>GRAPH</a>
            <a className={view === "map" ? "on" : ""} onClick={() => view !== "map" && toggleView()}>MAP</a>
          </div>
        </Tip>
        <BlastSeverityGauge />
        {cascade && <RegimeBadge regime={cascade.event.regime} />}
      </div>

      <div className="stage">
        <div className="left-col">
          <ImpactLedger />
          <ExplainerCard />
        </div>
        <div className="graph-col">
          {cascade && <HeadlineCard cascade={cascade} />}
          {error ? (
            <div className="error-panel">⚠ {error}</div>
          ) : cascade ? (
            <GraphCanvas
              cascade={cascade}
              fgRef={fgRef}
              geo={view === "map"}
              onNodeClick={(n: any) => {
                setSelected(n.id);          // drill-down: isolate this node's strongest path + per-hop math
                if (n?.x != null) {
                  fgRef.current?.centerAt?.(n.x, n.y, 600);
                  fgRef.current?.zoom?.(4, 600);
                }
              }}
            />
          ) : (
            <div className="metric" style={{ padding: 40 }}>loading cascades…</div>
          )}
        </div>
        <div className="rail-col panel">
          <AgentAnswerCard />
          <DrillDownCard />
          <ImpactCurveCard />
          <TimeMachineCard />
          <ReasoningRail />
          <MetricsCard />
        </div>
      </div>

      <SignalFeed />
      <ControlDock />
    </div>
  );
}
