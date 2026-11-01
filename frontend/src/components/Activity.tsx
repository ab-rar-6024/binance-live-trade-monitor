import { HotCoin, Pressure } from "../api";
import { coinName, mood, ticker, usd } from "../format";
import { coinLink } from "../routes";
import { Section, TugBar } from "./ui";

/** Where the money is moving: coins ranked by how much was traded recently. */
export function MostActive({ hot, minutes = 5 }: { hot: HotCoin[]; minutes?: number }) {
  const top = hot[0]?.notional || 1;
  return (
    <Section
      title="Where the money is moving"
      subtitle={`The coins people traded the most, over the last ${minutes} minutes. A longer bar means more money.`}
      learn={
        <ul>
          <li><b>Traded</b> is the total dollar value of all trades in the last {minutes} minutes.</li>
          <li>
            <b>Busier / quieter</b> compares that with the {minutes} minutes before. "Busier by 100%" means twice as much trading as before.
          </li>
        </ul>
      }
    >
      {hot.length === 0 ? (
        <div className="empty">Waiting for trades…</div>
      ) : (
        <ol className="rank">
          {hot.slice(0, 10).map((row) => {
            const change = row.change_vs_prev_pct;
            return (
              <li key={row.symbol} className="rank-row">
                <span className="rank-no">{row.rank}</span>
                <div className="rank-main">
                  <div className="rank-top">
                    <span><a className="coin-link" href={coinLink(row.symbol)}><b>{coinName(row.symbol)}</b></a> <span className="ticker">{ticker(row.symbol)}</span></span>
                    <span className="strong">{usd(row.notional)}</span>
                  </div>
                  <div className="meter"><div style={{ width: `${Math.max(2, (row.notional / top) * 100)}%` }} /></div>
                  <div className="rank-sub">
                    {row.trades.toLocaleString()} trades ·{" "}
                    {change === null ? (
                      <span className="muted">no comparison yet</span>
                    ) : change >= 0 ? (
                      <span className="up">▲ {Math.round(change)}% busier</span>
                    ) : (
                      <span className="down">▼ {Math.round(Math.abs(change))}% quieter</span>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </Section>
  );
}

/** Buyers vs sellers for every coin as a tug of war. */
export function BuyersVsSellers({ pressure }: { pressure: Pressure | undefined }) {
  const minutes = pressure?.minutes ?? 5;
  return (
    <Section
      title="Buyers vs sellers"
      subtitle={`Who is pushing harder in each coin over the last ${minutes} minutes. Green is buyers, red is sellers.`}
      learn={
        <>
          <p>
            Every trade needs a buyer and a seller. We look at who made the move: a buyer paying the asking price (an eager buyer) or a
            seller accepting the highest offer (an eager seller).
          </p>
          <p>
            More eager buyers often goes along with rising prices, and more eager sellers with falling prices, but it is not a promise.
          </p>
        </>
      }
    >
      <div className="pressure-list">
        {(pressure?.coins ?? []).slice(0, 10).map((c) => {
          const feel = mood(c.buy_pct);
          return (
            <div key={c.symbol} className="pressure-row" title={`Buyers ${usd(c.buy)}, sellers ${usd(c.sell)}`}>
              <div className="pressure-top">
                <a className="coin-link" href={coinLink(c.symbol)}><b>{coinName(c.symbol)}</b></a>
                <span className={`${feel.tone}-text`}>{feel.short}</span>
              </div>
              <TugBar buyPct={c.buy_pct} labels />
            </div>
          );
        })}
        {!pressure && <div className="empty">Waiting for trades…</div>}
      </div>
    </Section>
  );
}
