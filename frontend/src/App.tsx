import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Alert } from "./api";
import { BuyersVsSellers, MostActive } from "./components/Activity";
import { AlertsPanel } from "./components/AlertsPanel";
import { CoinGrid } from "./components/CoinGrid";
import { HowItWorks } from "./components/HowItWorks";
import { Overview } from "./components/Overview";
import { Sidebar } from "./components/Sidebar";
import { Toast, Toasts } from "./components/Toasts";
import { TradesPanel } from "./components/TradesPanel";
import { coinName } from "./format";
import { playBeep, shouldNotify, showSystemNotification, useFreshAlerts } from "./notifications";
import { parseHash, Route } from "./routes";
import { useSettings } from "./settings";
import { useMarketStream } from "./useMarketStream";

// The coin and settings pages are loaded only when opened, which keeps the first page load small
// (the chart library is the biggest part).
const CoinPage = lazy(() => import("./components/CoinPage"));
const SettingsPage = lazy(() => import("./components/SettingsPage"));

/** One honest, plain-language line about whether the data on screen is live. */
export function liveStatus(connected: boolean, hasData: boolean, feedLive: boolean | undefined): { state: "ok" | "warn" | "bad"; text: string } {
  if (!hasData) return { state: "warn", text: connected ? "Loading the first data…" : "Connecting…" };
  if (!connected) return { state: "warn", text: "Connection lost. Reconnecting, showing the last data received." };
  if (feedLive === false) return { state: "bad", text: "Paused: no trades are arriving from Binance right now." };
  return { state: "ok", text: "Live" };
}

function useRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const onChange = () => {
      setRoute(parseHash(window.location.hash));
      window.scrollTo({ top: 0 });
    };
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return route;
}

export default function App() {
  const { tick, alerts, trades, config, status } = useMarketStream();
  const { settings } = useSettings();
  const route = useRoute();
  const [now, setNow] = useState(Date.now());
  const [toasts, setToasts] = useState<Toast[]>([]);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  const closeToast = useCallback((key: string) => setToasts((t) => t.filter((x) => x.key !== key)), []);

  // New unusual moments: pop-up on the page, plus a system notification and a sound when the person turned them on.
  useFreshAlerts(alerts, !!tick, (fresh: Alert[]) => {
    const wanted = fresh.filter((a) => shouldNotify(a, settings)).slice(0, 3);
    if (!wanted.length) return;
    setToasts((current) => [...wanted.map((alert) => ({ key: alert.id, alert })), ...current].slice(0, 3));
    wanted.forEach((a) => showSystemNotification(`Unusual: ${coinName(a.s)}`, a.message, a.s));
    if (settings.sound) playBeep();
  });

  const system = tick?.system;
  const coins = tick?.overview ?? [];
  const live = liveStatus(status === "open", !!tick, system ? system.binance_feed.status === "live" : undefined);
  const age = tick ? Math.max(0, Math.round((now - tick.ts) / 1000)) : 0;
  const sub = live.state === "ok" && tick ? `Updated ${age <= 2 ? "just now" : `${age} s ago`}` : undefined;
  const lastHour = alerts.filter((a) => now - a.ts <= 3_600_000).length;
  const symbols = config?.symbols ?? coins.map((c) => c.symbol);

  return (
    <div className="shell">
      <Sidebar route={route} live={{ ...live, sub }} badges={{ unusual: lastHour }} />

      <main className="main">
        {status === "closed" && !tick && (
          <div className="notice">
            The data service is not answering yet. If you are the person running this, start it with <code>python scripts/dev.py start</code>.
          </div>
        )}

        <Suspense fallback={<div className="empty">Loading…</div>}>
          {route.page === "overview" && <Overview coins={coins} hot={tick?.hot ?? []} pressure={tick?.pressure} alerts={alerts} now={now} />}
          {route.page === "prices" && <CoinGrid coins={coins} />}
          {route.page === "coin" && route.symbol && (
            <CoinPage key={route.symbol} symbol={route.symbol} live={coins.find((c) => c.symbol === route.symbol)} now={now} />
          )}
          {route.page === "unusual" && <AlertsPanel alerts={alerts} thresholds={config?.thresholds} now={now} />}
          {route.page === "active" && <MostActive hot={tick?.hot ?? []} />}
          {route.page === "pressure" && <BuyersVsSellers pressure={tick?.pressure} />}
          {route.page === "trades" && <TradesPanel trades={trades} />}
          {route.page === "how" && <HowItWorks system={system} />}
          {route.page === "settings" && <SettingsPage symbols={symbols} detectorFloor={config?.thresholds.whale_min_usd} />}
        </Suspense>

        <footer className="footer">
          Information only, not financial advice. Prices are in USDT, a coin worth about one US dollar. Trade data comes from Binance's
          free public feed.
        </footer>
      </main>

      <Toasts toasts={toasts} onClose={closeToast} />
    </div>
  );
}
