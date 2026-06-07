// The integrity beat — the honest backtest, rendered (not buried). Numbers from tools/calibrate.py
// (27 events, held-out TEST, CORE cohort). We lead with reach; direction is stated as modest.
export default function MetricsCard() {
  return (
    <div className="metrics-card">
      <div className="metrics-h">VALIDATION · honest</div>
      <table className="metrics-tbl">
        <thead>
          <tr><th>non-headline movers</th><th>TEST</th><th>reach</th></tr>
        </thead>
        <tbody>
          <tr className="hl"><td>Graph (tuned)</td><td>46.6%</td><td>~20%</td></tr>
          <tr><td>Headline-only</td><td>—</td><td>0%</td></tr>
          <tr><td>Whole-sector</td><td>48.3%</td><td>~34%</td></tr>
        </tbody>
      </table>
      <p className="metrics-note">
        Daily direction is noisy — even <i>directly-named</i> names move "as expected" only ~60–67% at 1 day.
        We beat headline-only on <b>reach</b>; we <b>tie</b> the sector baseline on raw direction and claim
        <b> no robust directional edge</b> on a 27-event sample. The value is the <b>explained path</b> and the
        non-obvious winner — and we say exactly that.
      </p>
      <p className="metrics-stamp">source: <code>tools/calibrate.py</code> · 27 events · real Yahoo Finance, local benchmarks · refresh before the demo: <code>python tools/calibrate.py</code></p>
    </div>
  );
}
