import { Alert, Coin, HotCoin, Pressure } from "../api";
import { coinName, mood, usd } from "../format";
import { coinLink } from "../routes";
import { Change, TugBar } from "./ui";

/** Four big "at a glance" answers, each in a plain sentence. */
export function Summary({
  coins,
  hot,
  pressure,
  alerts,
  now,
}: {
  coins: Coin[];
  hot: HotCoin[];
  pressure: Pressure | undefined;
  alerts: Alert[];
  now: number;
}) {
  const buyPct = pressure?.buy_pct ?? null;
  const marketMood = mood(buyPct);
  const busiest = hot[0];
  const movers = coins.filter((c) => c.change_5m_pct !== null);
  const mover = movers.length
    ? movers.reduce((a, b) => (Math.abs(b.change_5m_pct ?? 0) > Math.abs(a.change_5m_pct ?? 0) ? b : a))
    : undefined;
  const lastHour = alerts.filter((a) => now - a.ts <= 3_600_000);
  const latest = lastHour[0];

  return (
    <section className="summary" aria-label="At a glance">
      <article className="tile">
        <h3>Who is winning right now?</h3>
        <div className={`tile-big ${marketMood.tone}-text`}>{marketMood.long}</div>
        {buyPct !== null && <TugBar buyPct={buyPct} labels />}
        <p className="tile-note">Share of money that came from buyers vs sellers over the last 5 minutes, across all coins.</p>
      </article>

      <article className="tile">
        <h3>Busiest coin</h3>
        <div className="tile-big">{busiest ? <a className="coin-link" href={coinLink(busiest.symbol)}>{coinName(busiest.symbol)}</a> : "-"}</div>
        <p className="tile-note">
          {busiest
            ? `${usd(busiest.notional)} changed hands in the last 5 minutes, ${busiest.share_pct.toFixed(0)}% of everything we watch.`
            : "Waiting for trades."}
        </p>
      </article>

      <article className="tile">
        <h3>Biggest price move</h3>
        <div className="tile-big">{mover ? <a className="coin-link" href={coinLink(mover.symbol)}>{coinName(mover.symbol)}</a> : "-"}</div>
        <p className="tile-note">
          {mover ? <><Change value={mover.change_5m_pct} /> over the last 5 minutes.</> : "Waiting for trades."}
        </p>
      </article>

      <article className="tile">
        <h3>Unusual moments (last hour)</h3>
        <div className="tile-big">{lastHour.length === 0 ? "None" : lastHour.length}</div>
        <p className="tile-note">
          {latest ? `Most recent: ${describeShort(latest)}.` : "Quiet so far. Big events are rare, and that is normal."}
        </p>
      </article>
    </section>
  );
}

function describeShort(a: Alert): string {
  const coin = coinName(a.s);
  if (a.type === "whale_trade") return `a big ${a.detail.side === "sell" ? "sale" : "purchase"} of ${coin}`;
  if (a.type === "price_spike") return `${coin} ${a.value > 0 ? "jumped" : "dropped"} suddenly`;
  return `${coin} trading surge`;
}
