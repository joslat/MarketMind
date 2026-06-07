import { useStore } from "../store";

const BAND_RANK: Record<string, number> = { Severe: 4, High: 3, Moderate: 2, Marginal: 1 };

export default function ImpactLedger() {
  const ledger = useStore((s) => s.ledger);
  const selected = useStore((s) => s.selected);
  const setSelected = useStore((s) => s.setSelected);
  const losers = ledger.filter((r) => r.direction === "loss").slice(0, 14);
  const winners = ledger.filter((r) => r.direction === "gain").slice(0, 10);

  const Row = (r: { id: string; impact: number; direction: "gain" | "loss"; band: string; hop: number }) => (
    <div
      className={`ledger-row ${r.direction}${selected === r.id ? " on" : ""}`}
      key={r.id}
      onClick={() => setSelected(selected === r.id ? null : r.id)}
      title={`click to drill in · raw exposure ${r.impact >= 0 ? "+" : ""}${r.impact.toFixed(3)} · hop ${r.hop}`}
    >
      <span>
        <span className="glyph">{r.direction === "gain" ? "▲" : "▼"}</span>
        <span className="tk">{r.id}</span>
        <span className="hopdot">h{r.hop}</span>
      </span>
      <span className={`band b${BAND_RANK[r.band] ?? 1}`}>{r.band}</span>
    </div>
  );

  return (
    <div className="panel">
      <h3>Exposure · {ledger.length} in range</h3>
      <div className="ledger-group">▼ losers</div>
      {losers.length ? losers.map(Row) : <div className="metric">—</div>}
      <div className="ledger-group">▲ winners</div>
      {winners.length ? winners.map(Row) : <div className="metric">—</div>}
      <div className="band-legend">band = relative structural exposure (Severe→Marginal), not a % price move</div>
    </div>
  );
}
