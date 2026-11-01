import { fetchCoin, fetchSymbolAlerts, fetchSymbolTrades } from "../api";
import type { Coin, CoinSummary } from "../api";
import { coinName, compact, mood, price, ticker, usd } from "../format";
import { usePolling } from "../hooks";
import { useSettings } from "../settings";
import { AlertList } from "./AlertsPanel";
import PriceChart from "./PriceChart";
import { TradeList } from "./TradesPanel";
import { Change, Section, Star, TugBar } from "./ui";

function Stat({ label, children, note }: { label: string; children: React.ReactNode; note?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{children}</div>
      {note && <div className="stat-note">{note}</div>}
    </div>
  );
}

function Facts({ s }: { s: CoinSummary }) {
  const feel = mood(s.buy_pct_1h);
  const short = s.minutes_of_data < 60;
  return (
    <>
      <div className="stat-grid">
        <Stat label="Change in 1 hour"><Change value={s.change_1h_pct} /></Stat>
        <Stat label="Change in 24 hours"><Change value={s.change_24h_pct} /></Stat>
        <Stat label="Highest in 24 hours">{s.high_24h === null ? "-" : `$${price(s.high_24h)}`}</Stat>
        <Stat label="Lowest in 24 hours">{s.low_24h === null ? "-" : `$${price(s.low_24h)}`}</Stat>
        <Stat label="Money traded in 24 hours" note={`${compact(s.trades_24h)} trades`}>{usd(s.notional_24h)}</Stat>
        <Stat label="Biggest single trade" note="in 24 hours">{usd(s.largest_24h)}</Stat>
        <Stat label="Busyness right now" note="ranked by money traded in 5 min">
          {s.rank_5m ? `#${s.rank_5m} of ${s.of}` : "-"}
        </Stat>
        <Stat label="Who is pushing harder (1 hour)" note={feel.short}>
          {s.buy_pct_1h === null ? "-" : <TugBar buyPct={s.buy_pct_1h} labels />}
        </Stat>
      </div>
      {short && (
        <p className="note">
          Only {s.minutes_of_data} minute{s.minutes_of_data === 1 ? "" : "s"} of data have been collected for this coin so far, so the 1-hour
          and 24-hour figures cover just that time. They fill in as the page keeps running.
        </p>
      )}
    </>
  );
}

/** One coin on its own page: headline numbers, price history, its unusual moments and its latest trades. */
export default function CoinPage({ symbol, live, now }: { symbol: string; live: Coin | undefined; now: number }) {
  const { settings, toggleWatch } = useSettings();
  const name = coinName(symbol);
  const summary = usePolling(() => fetchCoin(symbol), symbol, 3000);
  const alerts = usePolling(() => fetchSymbolAlerts(symbol, 30), symbol, 10000);
  const trades = usePolling(() => fetchSymbolTrades(symbol, 30), symbol, 3000);

  const currentPrice = live?.price ?? summary.data?.price ?? null;
  const missing = summary.failed && !summary.data && !live;

  return (
    <>
      <a className="back-link" href="#/prices">← All coins</a>

      <section className="card coin-head">
        <div>
          <h2 className="coin-title">
            {name} <span className="ticker">{ticker(symbol)}</span>
            <Star symbol={symbol} on={settings.watchlist.includes(symbol)} onToggle={() => toggleWatch(symbol)} />
          </h2>
          <p className="subtitle">Everything about {name} in one place.</p>
        </div>
        <div className="coin-head-price">
          <div className="chart-price">{currentPrice === null ? "-" : `$${price(currentPrice)}`}</div>
          <Change value={live?.change_5m_pct ?? summary.data?.change_5m_pct} suffix=" in the last 5 minutes" />
        </div>
      </section>

      {missing && (
        <div className="notice">
          There is no data for {name} yet. Either it is not one of the coins being watched, or trades have not arrived yet.
        </div>
      )}

      {summary.data && <Facts s={summary.data} />}

      <PriceChart symbol={symbol} />

      <div className="two-col even">
        <Section title={`Unusual moments: ${name}`} subtitle={`Big trades, sudden moves and surges that stood out for ${name}.`}>
          <div className="scroll short">
            <AlertList alerts={alerts.data ?? []} now={now} linkCoins={false}
              empty={`Nothing unusual for ${name} yet. That is normal: big events are rare.`} />
          </div>
        </Section>
        <Section title={`Latest ${name} trades`} subtitle="Real trades as they happen, newest first.">
          <div className="scroll short">
            <TradeList trades={trades.data ?? []} linkCoins={false} />
          </div>
        </Section>
      </div>
    </>
  );
}
