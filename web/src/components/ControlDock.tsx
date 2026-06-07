import { useStore } from "../store";
import Tip from "./Tip";

export default function ControlDock() {
  const { index, eventId, cascade, cinematic, timeMachine, select, replay, toggleCinematic, toggleTimeMachine } =
    useStore();

  const cur = index.findIndex((e) => e.id === eventId);
  const go = (delta: number) => {
    if (!index.length) return;
    const next = (cur + delta + index.length) % index.length;
    select(index[next].id);
  };

  return (
    <div className="dock">
      <button onClick={() => go(-1)} title="previous event">◀</button>
      <select value={eventId ?? ""} onChange={(e) => select(e.target.value)}>
        {index.map((e) => (
          <option key={e.id} value={e.id}>
            {e.date} — {e.headline.slice(0, 60)}
          </option>
        ))}
      </select>
      <button onClick={() => go(1)} title="next event">▶</button>
      <Tip pos="top" align="left" w={260} tip={<>Replay the shockwave animation for this event from the top (or press <b>R</b> / <b>Space</b>).</>}>
        <button onClick={replay}>↻ replay</button>
      </Tip>
      <Tip pos="top" align="left" w={300} tip={
        <><b>Time Machine</b> reveals what <i>actually</i> happened — the realized 1-day abnormal return for each
        company, from real Yahoo Finance prices, with a ✓/✗ on whether our predicted <i>direction</i> was right.
        It shows our misses too: this is the honesty check, not a victory lap.</>
      }>
        <button onClick={toggleTimeMachine} className={timeMachine ? "active" : ""}>
          {timeMachine ? "⏱ time machine ◼" : "⏱ time machine"}
        </button>
      </Tip>
      <Tip pos="top" align="left" w={290} tip={
        <><b>Cinematic mode</b> (or press <b>C</b>): fullscreen, auto-advancing through a curated playlist of
        notable events.</>
      }>
        <button onClick={toggleCinematic}>{cinematic ? "◼ exit" : "⛶ cinematic"}</button>
      </Tip>
      <div className="spacer" />
      <Tip pos="top" align="right" w={340} tip={
        <><b>Not investment advice.</b> MarketMind is a research & education project. It models <b>exposure</b>
        and explained impact paths — it does <b>not</b> predict prices. On a held-out test it showed no next-day
        directional edge (it ties a whole-sector baseline). <b>Do not use it, on its own, to make buy or sell
        decisions.</b> Provided AS-IS, no warranty.</>
      }>
        <span className="dock-disclaimer">⚠ research only · not investment advice</span>
      </Tip>
      {cascade && (
        <span className="metric">
          weights: fSup↓{cascade.meta.weights.fSupDown} fSup↑{cascade.meta.weights.fSupUp} fCmp
          {cascade.meta.weights.fCmp} decay{cascade.meta.weights.hopDecay} ·{" "}
          <Tip pos="top" align="right" w={360} tip={
            <><b>What this means.</b> MarketMind doesn't predict tomorrow's price. It reasons about
            <b> exposure</b>: given a news event, which companies are structurally in the blast radius — through
            supply, ownership, partnership, and competition — how strongly, and along what path.<br /><br />
            <b>Why we frame it this way.</b> On real out-of-sample data the directional edge is modest (it ties a
            whole-sector baseline), so claiming "prediction" would be dishonest. The durable value is the
            <i> explained path</i> and the non-obvious names the headline never mentioned — validated openly, misses included.</>
          }>
            <u className="pos-line">reasoning + exposure, not prediction</u>
          </Tip>
        </span>
      )}
    </div>
  );
}
