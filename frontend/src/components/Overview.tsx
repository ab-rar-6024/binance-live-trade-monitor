import { Alert, Coin, HotCoin, Pressure } from "../api";
import { ago, coinName } from "../format";
import { passesDisplayFilter } from "../notifications";
import { coinLink } from "../routes";
import { useSettings } from "../settings";
import { describe, KINDS } from "./AlertsPanel";
import { CoinCard } from "./CoinGrid";
import { Intro } from "./Intro";
import { Summary } from "./Summary";
import { Section } from "./ui";

/** The home page: a short guide, the four headline answers, and the latest few unusual moments. */
export function Overview({
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
  const { settings } = useSettings();
  const visible = alerts.filter((a) => passesDisplayFilter(a, settings));
  const latest = visible.slice(0, 3);
  const watched = coins.filter((c) => settings.watchlist.includes(c.symbol));
  return (
    <>
      <Intro />
      <Summary coins={coins} hot={hot} pressure={pressure} alerts={visible} now={now} />
      <Section
        title="My watchlist"
        subtitle="The coins you starred. Open “Coins & prices” and tap the ☆ on a coin to add it here."
      >
        {watched.length === 0 ? (
          <div className="empty">No coins starred yet. <a href="#/prices">Pick some coins</a> to follow them here.</div>
        ) : (
          <div className="coin-grid">{watched.map((c) => <CoinCard key={c.symbol} coin={c} />)}</div>
        )}
      </Section>
      <Section
        title="Latest unusual moments"
        subtitle="The three most recent things that stood out. Open “Unusual moments” in the menu to see them all."
      >
        {latest.length === 0 ? (
          <div className="empty">Nothing unusual yet. That is normal: big events are rare.</div>
        ) : (
          <ul className="alert-list preview">
            {latest.map((a) => {
              const text = describe(a);
              return (
                <li key={a.id} className={`alert ${a.severity}`}>
                  <span className="alert-icon" aria-hidden="true">{KINDS[a.type].icon}</span>
                  <div className="alert-body">
                    <div className="alert-headline">{text.headline}</div>
                    <div className="alert-meta">{ago(a.ts, now)} · <a href={coinLink(a.s)}>Open {coinName(a.s)}</a></div>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
        <a className="more-link" href="#/unusual">See all unusual moments →</a>
      </Section>
    </>
  );
}
