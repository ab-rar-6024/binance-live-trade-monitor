/** Number, time and wording helpers. Everything user-facing is written for people who are new to crypto. */

const NAMES: Record<string, string> = {
  BTC: "Bitcoin",
  ETH: "Ethereum",
  BNB: "BNB",
  SOL: "Solana",
  XRP: "XRP",
  DOGE: "Dogecoin",
  ADA: "Cardano",
  AVAX: "Avalanche",
  LINK: "Chainlink",
  TRX: "TRON",
  DOT: "Polkadot",
  LTC: "Litecoin",
  BCH: "Bitcoin Cash",
  ATOM: "Cosmos",
  NEAR: "NEAR Protocol",
  UNI: "Uniswap",
  APT: "Aptos",
  ARB: "Arbitrum",
  OP: "Optimism",
  FIL: "Filecoin",
  INJ: "Injective",
  SUI: "Sui",
  SHIB: "Shiba Inu",
  PEPE: "Pepe",
  ETC: "Ethereum Classic",
  XLM: "Stellar",
  HBAR: "Hedera",
  AAVE: "Aave",
  ICP: "Internet Computer",
  CRV: "Curve",
};

/** "BTCUSDT" -> "BTC" */
export const ticker = (symbol: string) => (symbol.endsWith("USDT") ? symbol.slice(0, -4) : symbol);

/** "BTCUSDT" -> "Bitcoin" */
export const coinName = (symbol: string) => NAMES[ticker(symbol)] ?? ticker(symbol);

export function usd(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
  if (abs >= 1e3) return `$${(value / 1e3).toFixed(1)}K`;
  return `$${value.toFixed(abs < 10 ? 2 : 0)}`;
}

/** A price without the currency sign; more decimals for cheap coins. */
export function price(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const digits = value >= 1000 ? 2 : value >= 10 ? 3 : value >= 1 ? 4 : value >= 0.01 ? 5 : 8;
  return value.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function qty(value: number): string {
  return value >= 100 ? value.toFixed(1) : value >= 1 ? value.toFixed(2) : value.toFixed(4);
}

export function clock(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-GB", { hour12: false });
}

export function clockShort(ms: number): string {
  return clock(ms).slice(0, 5);
}

/** "just now", "12 seconds ago", "3 minutes ago" */
export function ago(ms: number, now = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - ms) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds} seconds ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} hour${hours === 1 ? "" : "s"} ago`;
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value >= 1000 ? `${(value / 1000).toFixed(1)} seconds` : `${Math.round(value)} milliseconds`;
}

export function compact(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  return value.toLocaleString("en-US", { notation: "compact", maximumFractionDigits: 1 });
}

export type Tone = "buy" | "sell" | "even";

/** Who is pushing harder, from the share (0-100) of money that came from buyers. */
export function mood(buyPct: number | null | undefined): { tone: Tone; short: string; long: string } {
  if (buyPct === null || buyPct === undefined) return { tone: "even", short: "No data yet", long: "Waiting for trades" };
  if (buyPct >= 58) return { tone: "buy", short: "Mostly buying", long: "Buyers are leading" };
  if (buyPct <= 42) return { tone: "sell", short: "Mostly selling", long: "Sellers are leading" };
  return { tone: "even", short: "Balanced", long: "Buyers and sellers are balanced" };
}

/** Axis label for a candle start time: the time of day, plus the weekday on day-long charts. */
export function axisLabel(ms: number, spanMinutes: number): string {
  const d = new Date(ms);
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
  return spanMinutes > 720 ? `${d.toLocaleDateString("en-GB", { weekday: "short" })} ${time}` : time;
}
