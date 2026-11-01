import { Trade } from "../api";
import { clock, coinName, qty, ticker, usd } from "../format";
import { coinLink } from "../routes";
import { Section } from "./ui";

/** One plain row per trade. `linkCoins` makes the coin name open that coin's page. */
export function TradeList({ trades, linkCoins = true, limit = 40 }: { trades: Trade[]; linkCoins?: boolean; limit?: number }) {
  if (trades.length === 0) return <div className="empty">Waiting for trades…</div>;
  return (
    <ul className="trade-list">
      {trades.slice(0, limit).map((t) => (
        <li key={`${t.s}-${t.id}`} className={`trade${t.n >= 10_000 ? " big" : ""}`}>
          <span className="trade-time">{clock(t.ts)}</span>
          <span className={`badge ${t.side === "buy" ? "buy" : "sell"}`}>{t.side === "buy" ? "Bought" : "Sold"}</span>
          <span className="trade-what">
            {qty(t.q)} {linkCoins ? <a href={coinLink(t.s)}>{ticker(t.s)}</a> : ticker(t.s)}{" "}
            <span className="muted">({coinName(t.s)})</span>
          </span>
          <span className="trade-value strong">{usd(t.n)}</span>
        </li>
      ))}
    </ul>
  );
}

/** The most recent individual trades across all coins. */
export function TradesPanel({ trades }: { trades: Trade[] }) {
  return (
    <Section
      title="Latest trades"
      subtitle="Real trades as they happen on Binance, newest first. Each row is one person buying or selling a coin."
      learn={<p>Rows with a coloured background are large trades, worth $10,000 or more.</p>}
    >
      <TradeList trades={trades} />
    </Section>
  );
}
