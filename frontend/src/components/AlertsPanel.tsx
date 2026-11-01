import { useState } from "react";
import { Alert, AlertType } from "../api";
import { ago, clock, coinName, price, usd } from "../format";
import { passesDisplayFilter } from "../notifications";
import { coinLink } from "../routes";
import { useSettings } from "../settings";
import { Section } from "./ui";

export const KINDS: Record<AlertType, { icon: string; name: string }> = {
  whale_trade: { icon: "🐋", name: "Big trades" },
  price_spike: { icon: "⚡", name: "Sudden price moves" },
  volume_surge: { icon: "📈", name: "Trading surges" },
};

/** Turns an alert into a plain-English headline and one supporting sentence. */
export function describe(a: Alert): { headline: string; detail: string } {
  const coin = coinName(a.s);
  const d = a.detail;
  if (a.type === "whale_trade") {
    const sold = d.side === "sell";
    return {
      headline: `Big ${sold ? "sale" : "purchase"}: ${usd(Number(d.notional))} of ${coin}`,
      detail: `That is about ${Math.round(Number(d.ratio)).toLocaleString()} times the size of a typical ${coin} trade, so someone ${sold ? "sold" : "bought"} a lot at once.`,
    };
  }
  if (a.type === "price_spike") {
    const move = Number(d.pct);
    const secs = Math.max(1, Math.round(Number(d.seconds)));
    return {
      headline: `${coin} ${move > 0 ? "jumped" : "dropped"} ${Math.abs(move).toFixed(2)}% in ${secs} second${secs === 1 ? "" : "s"}`,
      detail: `The price went from $${price(Number(d.from))} to $${price(Number(d.to))}. Moves this fast are uncommon.`,
    };
  }
  return {
    headline: `${coin} is trading ${Number(d.ratio).toFixed(1)} times more than normal`,
    detail: `${usd(Number(d.minute_value))} changed hands this minute, compared with about ${usd(Number(d.baseline))} in a typical minute.`,
  };
}

export function AlertList({ alerts, now, empty, linkCoins = true }: { alerts: Alert[]; now: number; empty: string; linkCoins?: boolean }) {
  if (alerts.length === 0) return <div className="empty">{empty}</div>;
  return (
    <ul className="alert-list">
      {alerts.map((a) => {
        const text = describe(a);
        return (
          <li key={a.id} className={`alert ${a.severity}`}>
            <span className="alert-icon" aria-hidden="true">{KINDS[a.type].icon}</span>
            <div className="alert-body">
              <div className="alert-headline">{text.headline}</div>
              <div className="alert-detail">{text.detail}</div>
              <div className="alert-meta">
                {ago(a.ts, now)} · {clock(a.ts)}
                {linkCoins && <> · <a href={coinLink(a.s)}>Open {coinName(a.s)}</a></>}
                {a.severity === "critical" && <span className="badge strong-flag">Very unusual</span>}
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function AlertsPanel({ alerts, thresholds, now }: { alerts: Alert[]; thresholds: Record<string, number> | undefined; now: number }) {
  const { settings } = useSettings();
  const [filter, setFilter] = useState<AlertType | "all">("all");
  const [onlyWatched, setOnlyWatched] = useState(false);

  const visible = alerts.filter((a) => passesDisplayFilter(a, settings) && (!onlyWatched || settings.watchlist.includes(a.s)));
  const shown = visible.filter((a) => filter === "all" || a.type === filter).slice(0, 60);
  const count = (type: AlertType) => visible.filter((a) => a.type === type).length;
  const kinds = Object.keys(KINDS) as AlertType[];
  const hidden = alerts.length - alerts.filter((a) => passesDisplayFilter(a, settings)).length;

  return (
    <Section
      title="Unusual moments"
      subtitle="The page flags anything out of the ordinary, newest first, so you don't have to watch the numbers yourself."
      className="alerts-card"
      learn={
        <>
          <p>An event is only shown when it stands out compared with that coin's own normal behaviour:</p>
          <ul>
            <li>
              <b>🐋 Big trade</b>: one single trade{thresholds ? <> worth at least ${thresholds.whale_min_usd?.toLocaleString()}</> : ""} and
              far larger than the usual trade of that coin. (People call these "whales".)
            </li>
            <li>
              <b>⚡ Sudden price move</b>: the price {thresholds ? <>changes by {thresholds.spike_pct}% or more</> : "changes a lot"} within 10 seconds.
            </li>
            <li>
              <b>📈 Trading surge</b>: this minute's trading is {thresholds ? <>at least {thresholds.surge_ratio}× </> : "much higher than "}
              what that coin usually sees in a minute.
            </li>
          </ul>
          <p>Unusual does not mean good or bad. It is simply a moment worth a look.</p>
        </>
      }
    >
      <div className="chips" role="group" aria-label="Filter unusual moments">
        <button className={`chip${filter === "all" ? " active" : ""}`} onClick={() => setFilter("all")}>All ({visible.length})</button>
        {kinds.map((t) => (
          <button key={t} className={`chip${filter === t ? " active" : ""}`} onClick={() => setFilter(t)}>
            {KINDS[t].icon} {KINDS[t].name} ({count(t)})
          </button>
        ))}
        <button className={`chip${onlyWatched ? " active" : ""}`} aria-pressed={onlyWatched} onClick={() => setOnlyWatched((v) => !v)}>
          ★ My watchlist
        </button>
      </div>
      {hidden > 0 && (
        <p className="note">
          {hidden} big trade{hidden === 1 ? "" : "s"} below ${settings.minWhaleUsd.toLocaleString()} hidden. Change this in <a href="#/settings">Settings</a>.
        </p>
      )}

      <div className="scroll">
        <AlertList
          alerts={shown}
          now={now}
          empty="Nothing unusual to show. That is normal: big events are rare, and the page needs a few minutes after starting to learn what is typical for each coin."
        />
      </div>
    </Section>
  );
}
