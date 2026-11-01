import { Alert, Coin } from "./api";

export function makeAlert(over: Partial<Alert> & { detail?: Alert["detail"] } = {}): Alert {
  return {
    id: over.id ?? `a-${Math.random()}`,
    seq: 1,
    type: "whale_trade",
    s: "BTCUSDT",
    ts: Date.now(),
    severity: "warning",
    value: 1,
    message: "test message",
    detail: { side: "buy", notional: 50_000, ratio: 1500 },
    ...over,
  };
}

export function makeCoin(symbol: string, over: Partial<Coin> = {}): Coin {
  return {
    symbol,
    price: 100,
    ts: Date.now(),
    change_5m_pct: 0.1,
    minute: { trades: 5, notional: 1000, vwap: 100, buy_ratio: 0.5 },
    buy_ratio_5m: 0.5,
    notional_5m: 1000,
    spark: [1, 2, 3],
    ...over,
  };
}
