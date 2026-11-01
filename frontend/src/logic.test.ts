import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Alert } from "./api";
import { ago, axisLabel, coinName, mood, price, ticker, usd } from "./format";
import { passesDisplayFilter, shouldNotify, useFreshAlerts } from "./notifications";
import { menuFor, parseHash } from "./routes";
import { DEFAULT_SETTINGS, parseSettings, Settings } from "./settings";
import { makeAlert } from "./test-helpers";

describe("format", () => {
  it("gives coins their full names and tickers", () => {
    expect(coinName("BTCUSDT")).toBe("Bitcoin");
    expect(coinName("PEPEUSDT")).toBe("Pepe");
    expect(coinName("NEWUSDT")).toBe("NEW"); // unknown coins fall back to the ticker
    expect(ticker("ETHUSDT")).toBe("ETH");
  });

  it("shortens dollar amounts", () => {
    expect([usd(5), usd(950), usd(25_000), usd(1_230_000), usd(2_500_000_000), usd(null)]).toEqual(["$5.00", "$950", "$25.0K", "$1.23M", "$2.50B", "-"]);
  });

  it("uses more decimals for cheap coins", () => {
    expect(price(77_925.5)).toBe("77,925.50");
    expect(price(0.19394)).toBe("0.19394");
    expect(price(0.000012345)).toBe("0.00001235");
  });

  it("says how long ago in words", () => {
    const now = 1_000_000_000_000;
    expect(ago(now - 2000, now)).toBe("just now");
    expect(ago(now - 30_000, now)).toBe("30 seconds ago");
    expect(ago(now - 60_000, now)).toBe("1 minute ago");
    expect(ago(now - 5 * 60_000, now)).toBe("5 minutes ago");
    expect(ago(now - 2 * 3_600_000, now)).toBe("2 hours ago");
  });

  it("describes who is leading", () => {
    expect(mood(70).tone).toBe("buy");
    expect(mood(30).tone).toBe("sell");
    expect(mood(50).short).toBe("Balanced");
    expect(mood(null).short).toBe("No data yet");
  });

  it("adds the weekday to axis labels only on long ranges", () => {
    const ms = new Date(2026, 0, 5, 14, 30).getTime();
    expect(axisLabel(ms, 60)).toBe("14:30");
    expect(axisLabel(ms, 1440)).toMatch(/^Mon 14:30$/);
  });
});

describe("routes", () => {
  it("understands page and coin links", () => {
    expect(parseHash("#/unusual")).toEqual({ page: "unusual" });
    expect(parseHash("#/coin/btcusdt")).toEqual({ page: "coin", symbol: "BTCUSDT" });
    expect(parseHash("#/settings")).toEqual({ page: "settings" });
  });

  it("falls back to the overview for anything unknown or unsafe", () => {
    expect(parseHash("")).toEqual({ page: "overview" });
    expect(parseHash("#/nope")).toEqual({ page: "overview" });
    expect(parseHash("#/coin/")).toEqual({ page: "overview" });
    expect(parseHash("#/coin/<script>")).toEqual({ page: "overview" });
  });

  it("keeps the coins menu item selected on a coin page", () => {
    expect(menuFor({ page: "coin", symbol: "BTCUSDT" })).toBe("prices");
    expect(menuFor({ page: "trades" })).toBe("trades");
  });
});

describe("settings", () => {
  it("falls back to defaults for missing or corrupted data", () => {
    expect(parseSettings(null)).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("{not json")).toEqual(DEFAULT_SETTINGS);
    expect(parseSettings("42")).toEqual(DEFAULT_SETTINGS);
  });

  it("keeps valid fields and repairs invalid ones one by one", () => {
    const s = parseSettings(JSON.stringify({ theme: "dark", watchlist: ["BTCUSDT", 5, null], minWhaleUsd: -3, notify: "yes", types: { price_spike: false } }));

    expect(s.theme).toBe("dark");
    expect(s.watchlist).toEqual(["BTCUSDT"]);
    expect(s.minWhaleUsd).toBe(DEFAULT_SETTINGS.minWhaleUsd);
    expect(s.notify).toBe(false);
    expect(s.types).toEqual({ whale_trade: true, price_spike: false, volume_surge: true });
  });

  it("ignores an unknown theme", () => {
    expect(parseSettings(JSON.stringify({ theme: "neon" })).theme).toBe("system");
  });
});

describe("notifications", () => {
  const on: Settings = { ...DEFAULT_SETTINGS, notify: true };

  it("never notifies when alerts are off", () => {
    expect(shouldNotify(makeAlert(), DEFAULT_SETTINGS)).toBe(false);
  });

  it("respects type, severity, size and watchlist choices", () => {
    expect(shouldNotify(makeAlert(), on)).toBe(true);
    expect(shouldNotify(makeAlert(), { ...on, types: { ...on.types, whale_trade: false } })).toBe(false);
    expect(shouldNotify(makeAlert({ severity: "warning" }), { ...on, minSeverity: "critical" })).toBe(false);
    expect(shouldNotify(makeAlert({ severity: "critical" }), { ...on, minSeverity: "critical" })).toBe(true);
    expect(shouldNotify(makeAlert({ detail: { notional: 30_000 } }), { ...on, minWhaleUsd: 100_000 })).toBe(false);
    expect(shouldNotify(makeAlert({ s: "ETHUSDT" }), { ...on, watchOnly: true, watchlist: ["BTCUSDT"] })).toBe(false);
    expect(shouldNotify(makeAlert({ s: "BTCUSDT" }), { ...on, watchOnly: true, watchlist: ["BTCUSDT"] })).toBe(true);
  });

  it("only the big-trade size filter touches big trades", () => {
    const spike = makeAlert({ type: "price_spike", detail: { pct: 0.2 } });
    expect(passesDisplayFilter(spike, { ...on, minWhaleUsd: 500_000 })).toBe(true);
    expect(passesDisplayFilter(makeAlert({ detail: { notional: 30_000 } }), { ...on, minWhaleUsd: 50_000 })).toBe(false);
  });

  describe("useFreshAlerts", () => {
    it("stays quiet about alerts that were already there, then reports only new ones", () => {
      const first = makeAlert({ id: "old" });
      const onFresh = vi.fn();
      const { rerender } = renderHook(({ alerts, ready }: { alerts: Alert[]; ready: boolean }) => useFreshAlerts(alerts, ready, onFresh),
        { initialProps: { alerts: [first], ready: false } });

      rerender({ alerts: [first], ready: true });          // first real data: remembered silently
      expect(onFresh).not.toHaveBeenCalled();

      const fresh = makeAlert({ id: "new" });
      rerender({ alerts: [fresh, first], ready: true });
      expect(onFresh).toHaveBeenCalledTimes(1);
      expect(onFresh.mock.calls[0][0].map((a: Alert) => a.id)).toEqual(["new"]);

      rerender({ alerts: [fresh, first], ready: true });   // nothing new: no repeat
      expect(onFresh).toHaveBeenCalledTimes(1);
    });
  });
});
