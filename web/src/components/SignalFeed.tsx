import { useMemo, useRef, useState, useEffect } from "react";
import { useStore } from "../store";

// Act 1 — the Feed: a filterable news wire; every card is click-to-cascade.
// U4: ◂/▸ arrow carousel replaces the raw scrollbar (disabled at the ends; scrollbar hidden).
export default function SignalFeed() {
  const index = useStore((s) => s.index);
  const eventId = useStore((s) => s.eventId);
  const select = useStore((s) => s.select);
  const [filter, setFilter] = useState<string>("all");
  const stripRef = useRef<HTMLDivElement>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  const scopes = useMemo(
    () => ["all", ...Array.from(new Set(index.map((e) => e.scope)))],
    [index]
  );
  const rows = useMemo(
    () =>
      index
        .filter((e) => filter === "all" || e.scope === filter)
        .slice()
        .sort((a, b) => (a.date < b.date ? 1 : -1)), // newest first, like a wire
    [index, filter]
  );

  const updateEnds = () => {
    const el = stripRef.current;
    if (!el) return;
    setAtStart(el.scrollLeft <= 2);
    setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 2);
  };
  useEffect(() => {
    updateEnds();
    const ro = new ResizeObserver(updateEnds);
    if (stripRef.current) ro.observe(stripRef.current);
    return () => ro.disconnect();
  }, [rows]);

  const nudge = (dir: number) => {
    const el = stripRef.current;
    if (!el) return;
    const card = el.querySelector(".signal-card") as HTMLElement | null;
    const step = (card ? card.offsetWidth + 8 : el.clientWidth * 0.4) * 2; // ~2 cards per press
    el.scrollBy({ left: dir * step, behavior: "smooth" });
  };

  return (
    <div className="feed">
      <div className="feed-head">
        <span className="feed-title">◢ SIGNAL WIRE</span>
        <span className="feed-hint">click a signal to fire its blast radius</span>
        <span className="feed-filters">
          {scopes.map((s) => (
            <a key={s} className={filter === s ? "on" : ""} onClick={() => setFilter(s)}>
              {s}
            </a>
          ))}
        </span>
      </div>
      <div className="feed-carousel">
        <button className="feed-arrow" onClick={() => nudge(-1)} disabled={atStart} aria-label="previous signals">‹</button>
        <div className="feed-strip" ref={stripRef} onScroll={updateEnds}>
          {rows.map((e) => (
            <button
              key={e.id}
              className={`signal-card ${e.id === eventId ? "active" : ""}`}
              onClick={() => select(e.id)}
              title={e.headline}
            >
              <div className="sc-top">
                <span className="sc-date">{e.date}</span>
                <span className={`sc-scope ${e.scope}`}>{e.scope}</span>
              </div>
              <div className="sc-headline">{e.headline}</div>
              <div className="sc-foot">
                <span className={`regime-dot ${e.regime}`} />
                {e.regime} · {e.reached} in range
                <span className="sc-sev" title={`severity ${e.severity}`}>
                  <i style={{ width: `${Math.round((e.severity ?? 0) * 100)}%` }} />
                </span>
              </div>
            </button>
          ))}
        </div>
        <button className="feed-arrow" onClick={() => nudge(1)} disabled={atEnd} aria-label="next signals">›</button>
      </div>
    </div>
  );
}
