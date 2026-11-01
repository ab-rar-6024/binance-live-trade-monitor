import { useMemo, useState } from "react";
import { Coin } from "../api";
import { coinName, mood, price, ticker, usd } from "../format";
import { coinLink } from "../routes";
import { useSettings } from "../settings";
import { Change, Section, Star } from "./ui";

export function Sparkline({ points, up }: { points: number[]; up: boolean }) {
  if (points.length < 2) return <div className="spark-empty">collecting data…</div>;
  const min = Math.min(...points);
  const max = Math.max(...points);
  const span = max - min || 1;
  const coords = points.map((p, i) => `${(i / (points.length - 1)) * 100},${28 - ((p - min) / span) * 26}`).join(" ");
  return (
    <svg viewBox="0 0 100 30" preserveAspectRatio="none" className="spark" aria-hidden="true">
      <polyline points={coords} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth="2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export function CoinCard({ coin }: { coin: Coin }) {
  const { settings, toggleWatch } = useSettings();
  const up = (coin.change_5m_pct ?? 0) >= 0;
  const feel = mood(coin.buy_ratio_5m === null ? null : coin.buy_ratio_5m * 100);

  return (
    <div className="coin-wrap">
      <a className="coin" href={coinLink(coin.symbol)} aria-label={`Open ${coinName(coin.symbol)}`}>
        <div className="coin-name">
          <span className="strong">{coinName(coin.symbol)}</span>
          <span className="ticker">{ticker(coin.symbol)}</span>
        </div>
        <div className="coin-price">${price(coin.price)}</div>
        <div className="coin-change">
          <Change value={coin.change_5m_pct} suffix=" in 5 min" />
        </div>
        <Sparkline points={coin.spark} up={up} />
        <div className="coin-foot">
          <span className={`badge ${feel.tone}`}>{feel.short}</span>
          <span className="muted">{usd(coin.notional_5m)} traded</span>
        </div>
      </a>
      <Star symbol={coin.symbol} on={settings.watchlist.includes(coin.symbol)} onToggle={() => toggleWatch(coin.symbol)} />
    </div>
  );
}

export type SortKey = "busiest" | "rising" | "falling" | "name";

const SORTS: { id: SortKey; label: string }[] = [
  { id: "busiest", label: "Busiest first" },
  { id: "rising", label: "Biggest rise first" },
  { id: "falling", label: "Biggest fall first" },
  { id: "name", label: "A to Z" },
];

/** Filters by name or ticker, optionally to the watchlist, then sorts. Exported for testing. */
export function arrangeCoins(coins: Coin[], query: string, sort: SortKey, watchlist: string[] | null): Coin[] {
  const q = query.trim().toLowerCase();
  const matches = coins.filter(
    (c) =>
      (!watchlist || watchlist.includes(c.symbol)) &&
      (!q || coinName(c.symbol).toLowerCase().includes(q) || ticker(c.symbol).toLowerCase().includes(q)),
  );
  const change = (c: Coin) => c.change_5m_pct ?? 0;
  const sorted = [...matches];
  if (sort === "busiest") sorted.sort((a, b) => b.notional_5m - a.notional_5m);
  else if (sort === "rising") sorted.sort((a, b) => change(b) - change(a));
  else if (sort === "falling") sorted.sort((a, b) => change(a) - change(b));
  else sorted.sort((a, b) => coinName(a.symbol).localeCompare(coinName(b.symbol)));
  return sorted;
}

export function CoinGrid({ coins }: { coins: Coin[] }) {
  const { settings } = useSettings();
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<SortKey>("busiest");
  const [onlyWatched, setOnlyWatched] = useState(false);

  const shown = useMemo(
    () => arrangeCoins(coins, query, sort, onlyWatched ? settings.watchlist : null),
    [coins, query, sort, onlyWatched, settings.watchlist],
  );

  return (
    <Section
      title="Coins & prices"
      subtitle="What each coin costs at this moment. Click a coin to open its page, or tap the star to add it to your watchlist."
      learn={
        <ul>
          <li><b>Price</b> is what the most recent trade was done at.</li>
          <li><b>The arrow</b> shows how much the price changed in the last 5 minutes (▲ up, ▼ down).</li>
          <li><b>The little line</b> is the price over the last 30 minutes.</li>
          <li>
            <b>The label</b> says whether more of the last 5 minutes' money came from people buying or selling.
            "Traded" is the total dollar value that changed hands in those 5 minutes.
          </li>
        </ul>
      }
    >
      <div className="toolbar">
        <label className="search">
          <span className="sr-only">Search coins</span>
          <input type="search" placeholder="Search a coin, e.g. Bitcoin or ETH" value={query} onChange={(e) => setQuery(e.target.value)} />
        </label>
        <label className="select">
          <span className="sr-only">Sort coins</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as SortKey)}>
            {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
        <button className={`chip${onlyWatched ? " active" : ""}`} aria-pressed={onlyWatched} onClick={() => setOnlyWatched((v) => !v)}>
          ★ My watchlist ({settings.watchlist.length})
        </button>
      </div>

      <div className="coin-grid">
        {coins.length === 0 && <div className="empty">Loading prices…</div>}
        {coins.length > 0 && shown.length === 0 && (
          <div className="empty">
            {onlyWatched && !query ? "Your watchlist is empty. Tap the ☆ on any coin to add it." : "No coin matches your search."}
          </div>
        )}
        {shown.map((coin) => <CoinCard key={coin.symbol} coin={coin} />)}
      </div>
      <p className="note">Showing {shown.length} of {coins.length} coins.</p>
    </Section>
  );
}
