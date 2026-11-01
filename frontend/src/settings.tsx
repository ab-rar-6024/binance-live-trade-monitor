import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { AlertType } from "./api";

export type Theme = "system" | "light" | "dark";

export interface Settings {
  theme: Theme;
  /** Coins the person starred. */
  watchlist: string[];
  /** Alert me (on-page pop-ups, and system notifications when allowed) about new unusual moments. */
  notify: boolean;
  sound: boolean;
  minSeverity: "warning" | "critical";
  types: Record<AlertType, boolean>;
  /** Big trades smaller than this are hidden from the list and never notified. */
  minWhaleUsd: number;
  /** Only notify about starred coins. */
  watchOnly: boolean;
}

export const DEFAULT_SETTINGS: Settings = {
  theme: "system",
  watchlist: [],
  notify: false,
  sound: false,
  minSeverity: "warning",
  types: { whale_trade: true, price_spike: true, volume_surge: true },
  minWhaleUsd: 25_000,
  watchOnly: false,
};

const KEY = "crypto-monitor-settings-v1";

/** Reads saved settings, tolerating missing, old or corrupted data by falling back to the defaults field by field. */
export function parseSettings(raw: string | null): Settings {
  if (!raw) return DEFAULT_SETTINGS;
  let data: Record<string, unknown>;
  try {
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return DEFAULT_SETTINGS;
    data = parsed as Record<string, unknown>;
  } catch {
    return DEFAULT_SETTINGS;
  }
  const types = (data.types && typeof data.types === "object" ? data.types : {}) as Record<string, unknown>;
  const flag = (value: unknown, fallback: boolean) => (typeof value === "boolean" ? value : fallback);
  return {
    theme: data.theme === "light" || data.theme === "dark" || data.theme === "system" ? data.theme : DEFAULT_SETTINGS.theme,
    watchlist: Array.isArray(data.watchlist) ? data.watchlist.filter((s): s is string => typeof s === "string") : [],
    notify: flag(data.notify, DEFAULT_SETTINGS.notify),
    sound: flag(data.sound, DEFAULT_SETTINGS.sound),
    minSeverity: data.minSeverity === "critical" ? "critical" : "warning",
    types: {
      whale_trade: flag(types.whale_trade, true),
      price_spike: flag(types.price_spike, true),
      volume_surge: flag(types.volume_surge, true),
    },
    minWhaleUsd: typeof data.minWhaleUsd === "number" && data.minWhaleUsd >= 0 ? data.minWhaleUsd : DEFAULT_SETTINGS.minWhaleUsd,
    watchOnly: flag(data.watchOnly, DEFAULT_SETTINGS.watchOnly),
  };
}

function load(): Settings {
  try {
    return parseSettings(localStorage.getItem(KEY));
  } catch {
    return DEFAULT_SETTINGS; // storage can be blocked (private windows, strict browser settings)
  }
}

interface Ctx {
  settings: Settings;
  update: (patch: Partial<Settings>) => void;
  toggleWatch: (symbol: string) => void;
  reset: () => void;
}

const SettingsContext = createContext<Ctx | null>(null);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<Settings>(load);

  useEffect(() => {
    try {
      localStorage.setItem(KEY, JSON.stringify(settings));
    } catch {
      /* not saved, but everything still works for this visit */
    }
  }, [settings]);

  useEffect(() => {
    const root = document.documentElement;
    if (settings.theme === "system") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", settings.theme);
  }, [settings.theme]);

  const update = useCallback((patch: Partial<Settings>) => setSettings((s) => ({ ...s, ...patch })), []);
  const toggleWatch = useCallback(
    (symbol: string) =>
      setSettings((s) => ({
        ...s,
        watchlist: s.watchlist.includes(symbol) ? s.watchlist.filter((x) => x !== symbol) : [...s.watchlist, symbol],
      })),
    [],
  );
  const reset = useCallback(() => setSettings(DEFAULT_SETTINGS), []);
  const value = useMemo(() => ({ settings, update, toggleWatch, reset }), [settings, update, toggleWatch, reset]);

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): Ctx {
  const ctx = useContext(SettingsContext);
  if (!ctx) throw new Error("useSettings must be used inside <SettingsProvider>");
  return ctx;
}
