// Types mirroring the Python API (backend/app/main.py) and small fetch helpers.

export const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8100";
export const WS_URL = API_URL.replace(/^http/, "ws") + "/ws";

export interface Coin {
  symbol: string;
  price: number | null;
  ts: number | null;
  change_5m_pct: number | null;
  minute: { trades: number; notional: number; vwap: number | null; buy_ratio: number | null };
  buy_ratio_5m: number | null;
  notional_5m: number;
  spark: number[];
}

export interface HotCoin {
  rank: number;
  symbol: string;
  notional: number;
  trades: number;
  share_pct: number;
  change_vs_prev_pct: number | null;
}

export interface PressureCoin {
  symbol: string;
  buy: number;
  sell: number;
  buy_pct: number;
}

export interface Pressure {
  minutes: number;
  coins: PressureCoin[];
  buy_pct: number | null;
  buy: number;
  sell: number;
}

export type AlertType = "whale_trade" | "price_spike" | "volume_surge";
export type Severity = "info" | "warning" | "critical";

export interface Alert {
  id: string;
  seq: number;
  type: AlertType;
  s: string;
  ts: number;
  severity: Severity;
  value: number;
  message: string;
  detail: Record<string, number | string>;
}

export interface Trade {
  s: string;
  id: number;
  p: number;
  q: number;
  n: number;
  ts: number;
  side: "buy" | "sell";
  ing: number;
}

export interface QueryProgress {
  query: string;
  batch: number | null;
  rows: number | null;
  in_rps: number | null;
  proc_rps: number | null;
  duration_ms: number | null;
  age_s: number;
}

export interface SystemInfo {
  kafka: { connected: boolean; topics: Record<string, { partitions: number; messages: number }> };
  binance_feed: { trades_per_second: number; last_trade_age_s: number | null; status: "live" | "stalled" };
  spark: { alive: boolean; queries: Record<string, QueryProgress> };
  latency_ms: {
    producer_to_api_p50: number | null;
    producer_to_api_p95: number | null;
    producer_to_spark_p50: number | null;
    producer_to_spark_p95: number | null;
  };
  counts: Record<string, number>;
  uptime_s: number;
}

export interface Tick {
  type: "tick";
  ts: number;
  overview: Coin[];
  hot: HotCoin[];
  pressure: Pressure;
  system: SystemInfo;
  trades: Trade[];
  alerts: Alert[];
}

export interface Candle {
  ws: number;
  bucket_min?: number;
  open: number;
  high: number;
  low: number;
  close: number;
  vwap: number | null;
  notional: number;
  trades: number;
  buy_notional: number;
  sell_notional: number;
  largest: number;
}

export interface Config {
  symbols: string[];
  topics: string[];
  thresholds: Record<string, number>;
}

export interface CoinSummary {
  symbol: string;
  price: number | null;
  ts: number | null;
  change_5m_pct: number | null;
  change_1h_pct: number | null;
  change_24h_pct: number | null;
  high_24h: number | null;
  low_24h: number | null;
  notional_5m: number;
  notional_1h: number;
  notional_24h: number;
  trades_24h: number;
  largest_24h: number | null;
  buy_pct_5m: number | null;
  buy_pct_1h: number | null;
  rank_5m: number | null;
  of: number;
  minutes_of_data: number;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_URL}${path}`);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return (await res.json()) as T;
}

export async function fetchCandles(symbol: string, minutes: number): Promise<{ candles: Candle[]; bucketMin: number }> {
  const body = await getJson<{ candles: Candle[]; bucket_min: number | null }>(`/api/series/${symbol}?minutes=${minutes}`);
  return { candles: body.candles, bucketMin: body.bucket_min ?? 1 };
}

export const fetchCoin = (symbol: string) => getJson<CoinSummary>(`/api/coin/${symbol}`);

export async function fetchSymbolTrades(symbol: string, limit = 30): Promise<Trade[]> {
  return (await getJson<{ trades: Trade[] }>(`/api/trades?symbol=${symbol}&limit=${limit}`)).trades;
}

export async function fetchSymbolAlerts(symbol: string, limit = 30): Promise<Alert[]> {
  return (await getJson<{ alerts: Alert[] }>(`/api/alerts?symbol=${symbol}&limit=${limit}`)).alerts;
}
