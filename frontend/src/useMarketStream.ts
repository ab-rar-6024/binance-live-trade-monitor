import { useEffect, useState } from "react";
import { Alert, Config, Tick, Trade, WS_URL } from "./api";

export type ConnectionStatus = "connecting" | "open" | "closed";

const MAX_ALERTS = 200;
const MAX_TRADES = 120;

function mergeAlerts(incoming: Alert[], existing: Alert[]): Alert[] {
  const seen = new Set<string>();
  return [...incoming, ...existing]
    .filter((a) => (seen.has(a.id) ? false : (seen.add(a.id), true)))
    .sort((a, b) => b.ts - a.ts)
    .slice(0, MAX_ALERTS);
}

/** Subscribes to the API's WebSocket and keeps the latest tick, alert list and trade feed. */
export function useMarketStream() {
  const [tick, setTick] = useState<Tick | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

  useEffect(() => {
    let socket: WebSocket | undefined;
    let timer: number | undefined;
    let stopped = false;

    const connect = () => {
      setStatus("connecting");
      socket = new WebSocket(WS_URL);
      socket.onopen = () => setStatus("open");
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        if (message.type === "snapshot") {
          setAlerts(message.alerts);
          setTrades(message.trades);
          setConfig(message.config);
        } else if (message.type === "tick") {
          setTick(message as Tick);
          if (message.alerts.length) setAlerts((current) => mergeAlerts(message.alerts, current));
          if (message.trades.length) setTrades((current) => [...message.trades, ...current].slice(0, MAX_TRADES));
        }
      };
      socket.onclose = () => {
        setStatus("closed");
        if (!stopped) timer = window.setTimeout(connect, 2000); // the API restarts: reconnect quietly
      };
    };

    connect();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      socket?.close();
    };
  }, []);

  return { tick, alerts, trades, config, status };
}
