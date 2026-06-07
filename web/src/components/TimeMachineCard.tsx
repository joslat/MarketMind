import { useStore } from "../store";

// "Here's our call → here's what actually happened." Reveals the golden-dataset realized
// abnormal returns after the cascade settles, with a per-company ✓/✗ and an honest split label.
export default function TimeMachineCard() {
  const cascade = useStore((s) => s.cascade);
  const timeMachine = useStore((s) => s.timeMachine);
  const revealActuals = useStore((s) => s.revealActuals);
  if (!timeMachine || !cascade) return null;

  const scored = cascade.nodes.filter((n) => n.actual !== undefined);
  const hits = scored.filter((n) => n.hit).length;
  const split = cascade.event.split === "TEST" ? "HELD-OUT TEST" : "in-sample (TRAIN)";

  return (
    <div className="tm-card">
      <div className="tm-h">
        ⏱ TIME MACHINE <span className={`tm-split ${cascade.event.split}`}>{split}</span>
      </div>
      {!revealActuals ? (
        <div className="tm-wait">our call is on the board — revealing what actually happened…</div>
      ) : (
        <>
          <div className="tm-score">
            direction called right on <b>{hits}/{scored.length}</b> scored names
          </div>
          <div className="tm-list">
            {[...scored]
              .sort((a, b) => Math.abs(b.actual!) - Math.abs(a.actual!))
              .slice(0, 8)
              .map((n) => (
                <div className={`tm-row ${n.hit ? "ok" : "no"}`} key={n.id}>
                  <span className="tk">{n.id}</span>
                  <span className="pred">pred {n.direction === "gain" ? "▲" : "▼"}</span>
                  <span className="act">{n.actual! >= 0 ? "+" : ""}{n.actual}%</span>
                  <span className="mark">{n.hit ? "✓" : "✗"}</span>
                </div>
              ))}
          </div>
          <div className="tm-note">
            realized 1-day abnormal returns (vs each name's local benchmark) from the golden dataset.
            We show the <i>misses</i> too — that's the point.
          </div>
        </>
      )}
    </div>
  );
}
