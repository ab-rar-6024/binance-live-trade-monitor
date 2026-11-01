export type PageId = "overview" | "prices" | "coin" | "unusual" | "active" | "pressure" | "trades" | "how" | "settings";

export interface Route {
  page: PageId;
  /** Set on the coin page, e.g. "BTCUSDT". */
  symbol?: string;
}

/** Pages shown in the sidebar menu (the coin page is reached from the coin list). */
export const MENU: { id: Exclude<PageId, "coin">; label: string; icon: string; hint: string }[] = [
  { id: "overview", label: "Overview", icon: "🏠", hint: "The market at a glance" },
  { id: "prices", label: "Coins & prices", icon: "💲", hint: "Search and open any coin" },
  { id: "unusual", label: "Unusual moments", icon: "⚡", hint: "Big trades and sudden moves" },
  { id: "active", label: "Where the money is", icon: "🔥", hint: "The busiest coins" },
  { id: "pressure", label: "Buyers vs sellers", icon: "⚖️", hint: "Who is pushing harder" },
  { id: "trades", label: "Latest trades", icon: "🧾", hint: "Live, one by one" },
  { id: "how", label: "How it works", icon: "💡", hint: "For the curious" },
  { id: "settings", label: "Settings", icon: "⚙️", hint: "Alerts, watchlist, theme" },
];

const SIMPLE = new Set<PageId>(["overview", "prices", "unusual", "active", "pressure", "trades", "how", "settings"]);

/** "#/coin/BTCUSDT" -> { page: "coin", symbol: "BTCUSDT" }; anything unknown -> the overview. */
export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  if (parts[0] === "coin" && parts[1] && /^[A-Za-z0-9]{2,20}$/.test(parts[1])) {
    return { page: "coin", symbol: parts[1].toUpperCase() };
  }
  const page = parts[0] as PageId;
  return SIMPLE.has(page) ? { page } : { page: "overview" };
}

/** Which menu item should look selected for a route (the coin page belongs under "Coins & prices"). */
export function menuFor(route: Route): PageId {
  return route.page === "coin" ? "prices" : route.page;
}

export const coinLink = (symbol: string) => `#/coin/${symbol}`;
