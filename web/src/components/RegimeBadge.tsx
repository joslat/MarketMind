import Tip from "./Tip";

export default function RegimeBadge({ regime }: { regime: "contagion" | "substitution" }) {
  const tip = (
    <>
      <b>Regime</b> — how rivals respond to the shock.<br />
      <b>SUBSTITUTION</b> (a firm-specific stumble): a company's own problem can <i>help</i> its rivals,
      who pick up the slack — so competitor links flip sign (you'll see some green winners).<br />
      <b>CONTAGION</b> (a sector-wide, macro, or policy shock): rivals fall <i>together</i>, so that
      competitor benefit is switched off.<br />
      This event is <b>{regime.toUpperCase()}</b>.
    </>
  );
  return (
    <Tip tip={tip} pos="bottom" align="right" w={300}>
      <span className={`regime ${regime}`}>
        {regime === "contagion" ? "◍ CONTAGION" : "◐ SUBSTITUTION"}
      </span>
    </Tip>
  );
}
