import type { Page, WebSocketRoute } from "@playwright/test";

/** A fake backend: REST answers and the WebSocket feed, so the dashboard can be tested without Kafka or Spark. */

const now = () => Date.now();

const coin = (symbol: string, price: number, change: number, notional: number, buy: number) => ({
  symbol, price, ts: now(), change_5m_pct: change,
  minute: { trades: 12, notional: notional / 5, vwap: price, buy_ratio: buy },
  buy_ratio_5m: buy, notional_5m: notional, spark: [price * 0.99, price, price * 1.01, price],
});

export const COINS = [
  coin("BTCUSDT", 77_900, 0.12, 2_000_000, 0.7),
  coin("ETHUSDT", 2_270, -0.3, 700_000, 0.35),
  coin("DOGEUSDT", 0.0759, 0.8, 40_000, 0.5),
];

export const alertOf = (id: string, over: Record<string, unknown> = {}) => ({
  id, seq: 1, type: "whale_trade", s: "BTCUSDT", ts: now() - 30_000, severity: "warning", value: 60_000,
  message: "$60.0K BTC buy - 900x the typical BTC trade",
  detail: { side: "buy", notional: 60_000, ratio: 900 }, ...over,
});

const system = {
  kafka: { connected: true, topics: { "trades.raw": { partitions: 3, messages: 25_000 }, "trades.agg1m": { partitions: 3, messages: 900 }, "trades.alerts": { partitions: 3, messages: 5 } } },
  binance_feed: { trades_per_second: 120, last_trade_age_s: 0.2, status: "live" },
  spark: { alive: true, queries: { aggregates: { query: "aggregates", batch: 40, rows: 100, in_rps: 100, proc_rps: 160, duration_ms: 700, age_s: 1 } } },
  latency_ms: { producer_to_api_p50: 55, producer_to_api_p95: 70, producer_to_spark_p50: 1500, producer_to_spark_p95: 3000 },
  counts: { trades: 5000 }, uptime_s: 600,
};

function tick(alerts: unknown[] = []) {
  return {
    type: "tick", ts: now(), overview: COINS,
    hot: [
      { rank: 1, symbol: "BTCUSDT", notional: 2_000_000, trades: 3000, share_pct: 72, change_vs_prev_pct: 40 },
      { rank: 2, symbol: "ETHUSDT", notional: 700_000, trades: 2000, share_pct: 25, change_vs_prev_pct: -20 },
    ],
    pressure: { minutes: 5, coins: [{ symbol: "BTCUSDT", buy: 1_400_000, sell: 600_000, buy_pct: 70 }], buy_pct: 62, buy: 1_700_000, sell: 1_000_000 },
    system, trades: [], alerts,
  };
}

function candles(minutes: number) {
  const bucket = minutes <= 180 ? 1 : minutes <= 720 ? 5 : 15;
  const count = Math.floor(minutes / bucket);
  const end = Math.floor(now() / (bucket * 60_000)) * bucket * 60_000;
  return Array.from({ length: count }, (_, i) => {
    const price = 77_800 + i * 2;
    return { ws: end - (count - 1 - i) * bucket * 60_000, open: price, high: price + 5, low: price - 5, close: price + 1, vwap: price, notional: 20_000 + (i % 7) * 3000, trades: 50, buy_notional: 12_000, sell_notional: 8000, largest: 900, bucket_min: bucket };
  });
}

export interface Backend {
  /** Pushes a new tick (optionally with new alerts) to the page, as the real server would every second. */
  push(alerts?: unknown[]): void;
  /** The `minutes` values the page asked for on the chart endpoint. */
  seriesRequests: number[];
}

export async function mockBackend(page: Page, initialAlerts: unknown[] = [alertOf("a1")]): Promise<Backend> {
  let socket: WebSocketRoute | undefined;
  const seriesRequests: number[] = [];

  await page.routeWebSocket(/\/ws$/, (ws) => {
    socket = ws;
    const config = { symbols: COINS.map((c) => c.symbol), thresholds: { whale_min_usd: 25000, spike_pct: 0.15, surge_ratio: 3 } };
    // Like the real server: a snapshot on connect, then a tick every second (shortened here to keep tests quick).
    const timer = setInterval(() => ws.send(JSON.stringify(tick())), 400);
    setTimeout(() => ws.send(JSON.stringify({ type: "snapshot", alerts: initialAlerts, trades: [], config })), 50);
    ws.onClose(() => clearInterval(timer));
  });

  await page.route(/\/api\//, async (route) => {
    const url = new URL(route.request().url());
    const json = (body: unknown) => route.fulfill({ json: body, headers: { "access-control-allow-origin": "*" } });
    if (url.pathname.startsWith("/api/series/")) {
      const minutes = Number(url.searchParams.get("minutes") ?? 60);
      seriesRequests.push(minutes);
      const list = candles(minutes);
      return json({ symbol: "BTCUSDT", minutes, bucket_min: list[0].bucket_min, candles: list });
    }
    if (url.pathname.startsWith("/api/coin/")) {
      const symbol = url.pathname.split("/").pop()!;
      const c = COINS.find((x) => x.symbol === symbol);
      if (!c) return route.fulfill({ status: 404, json: { detail: "unknown" }, headers: { "access-control-allow-origin": "*" } });
      return json({ symbol, price: c.price, ts: now(), change_5m_pct: c.change_5m_pct, change_1h_pct: 0.4, change_24h_pct: -1.2, high_24h: c.price * 1.02, low_24h: c.price * 0.97, notional_5m: c.notional_5m, notional_1h: 9e6, notional_24h: 123_000_000, trades_24h: 250_000, largest_24h: 410_000, buy_pct_5m: 70, buy_pct_1h: 64, rank_5m: 1, of: 3, minutes_of_data: 1440 });
    }
    if (url.pathname === "/api/alerts") return json({ alerts: [alertOf("a1")] });
    if (url.pathname === "/api/trades") return json({ trades: [{ s: "BTCUSDT", id: 1, p: 77_900, q: 0.01, n: 779, ts: now(), side: "buy", ing: now() }] });
    return route.fulfill({ status: 404, json: {} });
  });

  return {
    seriesRequests,
    push(alerts = []) { socket?.send(JSON.stringify(tick(alerts))); },
  };
}
