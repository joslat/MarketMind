import { useStore } from "../store";
import Tip from "./Tip";

// U8 — "expected impact profile": an ILLUSTRATIVE curve of effect strength over time, shaped by the
// event's category (how this *kind* of news typically plays out) and scaled by event.severity.
// Honest framing: this is a shape model of the event's nature, NOT measured intraday price data.
type Profile = { kind: string; ticks: string[]; f: (t: number) => number };

// t in [0,1] across the profile's own time window (see ticks). f returns relative strength 0..1.
const SPIKE: Profile = { kind: "sharp repricing, fast fade", ticks: ["0", "+1h", "+1d", "+3d"], f: (t) => Math.exp(-t * 5.5) };
const RAMP_TAIL: Profile = { kind: "ramp, then a week-long tail", ticks: ["0", "+1d", "+1w", "+1m"], f: (t) => (t < 0.12 ? t / 0.12 : Math.exp(-(t - 0.12) * 2.6)) };
const BUILD_TAIL: Profile = { kind: "slow build, long tail", ticks: ["0", "+1d", "+1w", "+1m"], f: (t) => (t < 0.3 ? t / 0.3 : Math.exp(-(t - 0.3) * 1.7)) };
const STEP_PLATEAU: Profile = { kind: "step change, then it persists", ticks: ["0", "+1w", "+1m", "ongoing"], f: (t) => 0.25 + 0.65 * Math.min(1, t / 0.12) };

const BY_CATEGORY: Record<string, Profile> = {
  earnings: SPIKE,
  demand_surge: SPIKE,
  supply_chain_disruption: RAMP_TAIL,
  geopolitical: BUILD_TAIL,
  macro: BUILD_TAIL,
  sector: BUILD_TAIL,
  fx_monetary: BUILD_TAIL,
  commodity_shock: BUILD_TAIL,
  thematic: BUILD_TAIL,
  regulatory: STEP_PLATEAU,
  election_policy: STEP_PLATEAU,
};

const W = 248, H = 96, PAD = 14, N = 48;

export default function ImpactCurveCard() {
  const cascade = useStore((s) => s.cascade);
  if (!cascade) return null;
  const ev = cascade.event;
  const prof = BY_CATEGORY[ev.category] ?? BUILD_TAIL;
  const amp = Math.max(0.15, Math.min(1, ev.severity ?? 0.5)); // severity scales peak height
  const contagion = ev.regime === "contagion";
  const stroke = contagion ? "#ff4d4f" : "#58a6ff";

  const innerW = W - 2 * PAD, innerH = H - 2 * PAD;
  const px = (t: number) => PAD + t * innerW;
  const py = (v: number) => H - PAD - v * amp * innerH;

  const pts: [number, number][] = [];
  for (let i = 0; i <= N; i++) {
    const t = i / N;
    pts.push([px(t), py(prof.f(t))]);
  }
  const line = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${line} L${px(1).toFixed(1)},${(H - PAD).toFixed(1)} L${px(0).toFixed(1)},${(H - PAD).toFixed(1)} Z`;

  // the ONE real number we have: the epicenter company's realized abnormal return at +1 day.
  // Drawn as a dot ON the illustrative curve at the +1d tick, with the actual % in the label — so the
  // shape stays clearly illustrative while one honest, measured point anchors it.
  const epicenter = cascade.nodes
    .filter((n) => n.hop === 0 && n.tradable && n.actual !== undefined)
    .sort((a, b) => Math.abs(b.impact) - Math.abs(a.impact))[0];
  const d1 = prof.ticks.indexOf("+1d");
  const measured = epicenter?.actual !== undefined && d1 >= 0
    ? { x: px(d1 / (prof.ticks.length - 1)), y: py(prof.f(d1 / (prof.ticks.length - 1))), ticker: epicenter.id, actual: epicenter.actual! }
    : null;

  const tip = (
    <>
      An <b>illustrative</b> shape model — how this <i>kind</i> of event (earnings spike, supply-chain ramp,
      macro build, regulatory step) typically plays out over time, scaled by severity. It is <b>not</b> a precise
      estimate or measured intraday data. The one real number is the ● <b>measured</b> point: the epicenter's
      actual abnormal return at +1 day.
    </>
  );

  return (
    <div className="curve-card">
      <Tip tip={tip} pos="bottom" align="right" w={290}>
        <div className="curve-h">⌁ EXPECTED IMPACT OVER TIME <span className="curve-illus">illustrative ⓘ</span></div>
      </Tip>
      <svg viewBox={`0 0 ${W} ${H}`} className="curve-svg" preserveAspectRatio="none">
        <defs>
          <linearGradient id="curveFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={stroke} stopOpacity="0.35" />
            <stop offset="100%" stopColor={stroke} stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {/* baseline */}
        <line x1={PAD} y1={H - PAD} x2={W - PAD} y2={H - PAD} stroke="#2a3550" strokeWidth="1" />
        <path d={area} fill="url(#curveFill)" />
        <path d={line} fill="none" stroke={stroke} strokeWidth="1.6" />
        {/* the one real measured point (epicenter, +1d) */}
        {measured && (
          <>
            <line x1={measured.x} y1={PAD} x2={measured.x} y2={H - PAD} stroke="#ffffff22" strokeWidth="0.6" strokeDasharray="2 2" />
            <circle cx={measured.x} cy={measured.y} r="3" fill="#f5f7fa" stroke={stroke} strokeWidth="1" />
          </>
        )}
        {/* time ticks */}
        {prof.ticks.map((tk, i) => (
          <text key={i} x={px(i / (prof.ticks.length - 1))} y={H - 3} fontSize="7" fill="#7d8aa0" textAnchor={i === 0 ? "start" : i === prof.ticks.length - 1 ? "end" : "middle"}>{tk}</text>
        ))}
      </svg>
      <div className="curve-note">
        <b>{prof.kind}</b> · severity {Math.round(amp * 100)}% · {contagion ? "contagion" : "substitution"}.
        Illustrative shape by event type — not measured intraday data.
        {measured && (
          <span className="curve-measured"> ● measured: {measured.ticker} {measured.actual >= 0 ? "+" : ""}{measured.actual}% at +1d.</span>
        )}
      </div>
    </div>
  );
}
