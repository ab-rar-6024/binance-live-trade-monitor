import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SettingsProvider } from "../settings";
import { makeAlert, makeCoin } from "../test-helpers";
import { AlertsPanel, describe as describeAlert } from "./AlertsPanel";
import { arrangeCoins, CoinGrid } from "./CoinGrid";
import { takeaway } from "./PriceChart";
import { Sidebar } from "./Sidebar";
import { Candle } from "../api";

const coins = [
  makeCoin("BTCUSDT", { notional_5m: 5000, change_5m_pct: 0.1 }),
  makeCoin("ETHUSDT", { notional_5m: 9000, change_5m_pct: -0.4 }),
  makeCoin("DOGEUSDT", { notional_5m: 100, change_5m_pct: 0.9 }),
];

const withSettings = (ui: React.ReactElement) => render(<SettingsProvider>{ui}</SettingsProvider>);

describe("alert wording", () => {
  it("writes a big trade as a plain sentence", () => {
    const text = describeAlert(makeAlert({ s: "SOLUSDT", detail: { side: "sell", notional: 31_000, ratio: 2649 } }));

    expect(text.headline).toBe("Big sale: $31.0K of Solana");
    expect(text.detail).toContain("2,649 times");
    expect(text.detail).toContain("sold a lot");
  });

  it("writes a price move with direction and singular seconds", () => {
    const up = describeAlert(makeAlert({ type: "price_spike", s: "AVAXUSDT", value: 0.2, detail: { pct: 0.16, seconds: 1, from: 8.961, to: 8.975 } }));
    const down = describeAlert(makeAlert({ type: "price_spike", s: "AVAXUSDT", detail: { pct: -0.16, seconds: 8, from: 8.974, to: 8.96 } }));

    expect(up.headline).toBe("Avalanche jumped 0.16% in 1 second");
    expect(down.headline).toBe("Avalanche dropped 0.16% in 8 seconds");
  });

  it("writes a surge", () => {
    const text = describeAlert(makeAlert({ type: "volume_surge", s: "LINKUSDT", detail: { ratio: 4.5, minute_value: 50_000, baseline: 11_200 } }));

    expect(text.headline).toBe("Chainlink is trading 4.5 times more than normal");
    expect(text.detail).toContain("$50.0K");
  });
});

describe("coin list", () => {
  const names = (list: ReturnType<typeof arrangeCoins>) => list.map((c) => c.symbol);

  it("sorts four ways", () => {
    expect(names(arrangeCoins(coins, "", "busiest", null))).toEqual(["ETHUSDT", "BTCUSDT", "DOGEUSDT"]);
    expect(names(arrangeCoins(coins, "", "rising", null))).toEqual(["DOGEUSDT", "BTCUSDT", "ETHUSDT"]);
    expect(names(arrangeCoins(coins, "", "falling", null))).toEqual(["ETHUSDT", "BTCUSDT", "DOGEUSDT"]);
    expect(names(arrangeCoins(coins, "", "name", null))).toEqual(["BTCUSDT", "DOGEUSDT", "ETHUSDT"]);
  });

  it("searches by full name or ticker, ignoring case", () => {
    expect(names(arrangeCoins(coins, "bitc", "busiest", null))).toEqual(["BTCUSDT"]);
    expect(names(arrangeCoins(coins, "ETH", "busiest", null))).toEqual(["ETHUSDT"]);
    expect(arrangeCoins(coins, "zzz", "busiest", null)).toEqual([]);
  });

  it("can limit to the watchlist", () => {
    expect(names(arrangeCoins(coins, "", "busiest", ["DOGEUSDT"]))).toEqual(["DOGEUSDT"]);
  });

  it("filters as the person types and links each coin to its page", async () => {
    withSettings(<CoinGrid coins={coins} />);

    expect(screen.getByText("Showing 3 of 3 coins.")).toBeInTheDocument();
    await userEvent.type(screen.getByPlaceholderText(/search a coin/i), "doge");

    expect(screen.getByText("Showing 1 of 3 coins.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open Dogecoin" })).toHaveAttribute("href", "#/coin/DOGEUSDT");
  });

  it("stars a coin and the watchlist filter then shows it", async () => {
    withSettings(<CoinGrid coins={coins} />);

    await userEvent.click(screen.getByRole("button", { name: /add bitcoin to your watchlist/i }));
    await userEvent.click(screen.getByRole("button", { name: /my watchlist \(1\)/i }));

    expect(screen.getByText("Showing 1 of 3 coins.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /remove bitcoin from your watchlist/i })).toHaveAttribute("aria-pressed", "true");
  });
});

describe("alerts page", () => {
  const alerts = [
    makeAlert({ id: "1", detail: { side: "buy", notional: 60_000, ratio: 900 } }),
    makeAlert({ id: "2", type: "price_spike", s: "ETHUSDT", detail: { pct: 0.3, seconds: 5, from: 1, to: 1.003 } }),
    makeAlert({ id: "3", detail: { side: "buy", notional: 26_000, ratio: 300 }, s: "SOLUSDT" }),
  ];

  it("lists alerts and filters by kind", async () => {
    withSettings(<AlertsPanel alerts={alerts} thresholds={undefined} now={Date.now()} />);

    expect(screen.getByRole("button", { name: /All \(3\)/ })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Sudden price moves \(1\)/ }));

    const list = document.querySelector(".alert-list") as HTMLElement;
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByText(/Ethereum jumped/)).toBeInTheDocument();
  });

  it("links each alert to its coin", () => {
    withSettings(<AlertsPanel alerts={alerts} thresholds={undefined} now={Date.now()} />);

    expect(screen.getByRole("link", { name: "Open Ethereum" })).toHaveAttribute("href", "#/coin/ETHUSDT");
  });

  it("says so when there is nothing to show", () => {
    withSettings(<AlertsPanel alerts={[]} thresholds={undefined} now={Date.now()} />);

    expect(screen.getByText(/Nothing unusual to show/)).toBeInTheDocument();
  });
});

describe("sidebar", () => {
  const live = { state: "ok" as const, text: "Live", sub: "Updated just now" };

  it("marks the current page and shows the unusual-moments count", () => {
    render(<Sidebar route={{ page: "unusual" }} live={live} badges={{ unusual: 7 }} />);

    expect(screen.getByRole("link", { name: /Unusual moments/ })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: /Overview/ })).not.toHaveAttribute("aria-current");
    expect(screen.getByText("7")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent("Live");
  });

  it("keeps Coins & prices selected while on a coin page", () => {
    render(<Sidebar route={{ page: "coin", symbol: "BTCUSDT" }} live={live} badges={{}} />);

    expect(screen.getByRole("link", { name: /Coins & prices/ })).toHaveAttribute("aria-current", "page");
  });

  it("has a link for every section", () => {
    render(<Sidebar route={{ page: "overview" }} live={live} badges={{}} />);

    expect(screen.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(
      ["overview", "prices", "unusual", "active", "pressure", "trades", "how", "settings"].map((p) => `#/${p}`));
  });
});

describe("chart summary sentence", () => {
  const candle = (ws: number, open: number, close: number, notional: number): Candle => ({
    ws, open, close, high: Math.max(open, close), low: Math.min(open, close), vwap: close, notional, trades: 1,
    buy_notional: 0, sell_notional: 0, largest: 0,
  });

  it("states the change over the covered period", () => {
    const text = takeaway("Bitcoin", [candle(0, 100, 101, 10), candle(60_000, 101, 102, 50), candle(120_000, 102, 103, 20)], 1);

    expect(text).toContain("Over the last 3 minutes, Bitcoin is up 3.00%");
    expect(text).toContain("from $100.000 to $103.000");
    expect(text).toContain("$50.00 was traded".replace(".00", ""));
  });

  it("describes longer buckets in hours", () => {
    const data = Array.from({ length: 72 }, (_, i) => candle(i * 300_000, 100, 100, 1));

    expect(takeaway("Bitcoin", data, 5)).toContain("Over the last 6 hours, Bitcoin is about where it started");
  });
});
