import { useEffect, useRef } from "react";
import { Alert } from "./api";
import { Settings } from "./settings";

/** Hide big trades below the person's chosen size. Every other alert type is always shown. */
export function passesDisplayFilter(alert: Alert, settings: Settings): boolean {
  return alert.type !== "whale_trade" || Number(alert.detail.notional) >= settings.minWhaleUsd;
}

/** Whether a new alert should interrupt the person (pop-up, system notification, sound). */
export function shouldNotify(alert: Alert, settings: Settings): boolean {
  if (!settings.notify) return false;
  if (!settings.types[alert.type]) return false;
  if (settings.minSeverity === "critical" && alert.severity !== "critical") return false;
  if (!passesDisplayFilter(alert, settings)) return false;
  if (settings.watchOnly && !settings.watchlist.includes(alert.s)) return false;
  return true;
}

/**
 * Calls `onFresh` with alerts that appeared after the page had loaded. The alerts already present on the first
 * load are remembered silently, so opening the page never produces a burst of old notifications.
 */
export function useFreshAlerts(alerts: Alert[], ready: boolean, onFresh: (fresh: Alert[]) => void): void {
  const seen = useRef<Set<string> | null>(null);
  const callback = useRef(onFresh);
  callback.current = onFresh;

  useEffect(() => {
    if (!ready) return;
    if (seen.current === null) {
      seen.current = new Set(alerts.map((a) => a.id));
      return;
    }
    const known = seen.current;
    const fresh = alerts.filter((a) => !known.has(a.id));
    if (!fresh.length) return;
    fresh.forEach((a) => known.add(a.id));
    callback.current(fresh);
  }, [alerts, ready]);
}

/** A short two-tone beep made with the browser's audio API (no sound file needed). */
export function playBeep(): void {
  try {
    const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    const now = ctx.currentTime;
    [660, 880].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, now + i * 0.16);
      gain.gain.exponentialRampToValueAtTime(0.15, now + i * 0.16 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.16 + 0.15);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + i * 0.16);
      osc.stop(now + i * 0.16 + 0.16);
    });
    window.setTimeout(() => void ctx.close(), 800);
  } catch {
    /* sound is a nicety; ignore any browser restriction */
  }
}

export type PermissionState = "granted" | "denied" | "default" | "unsupported";

export function notificationPermission(): PermissionState {
  return typeof Notification === "undefined" ? "unsupported" : Notification.permission;
}

export async function askNotificationPermission(): Promise<PermissionState> {
  if (typeof Notification === "undefined") return "unsupported";
  try {
    return await Notification.requestPermission();
  } catch {
    return Notification.permission;
  }
}

/** Shows a system notification when the browser allows it. Clicking it opens the coin's page. */
export function showSystemNotification(title: string, body: string, symbol: string): void {
  if (notificationPermission() !== "granted") return;
  try {
    const n = new Notification(title, { body, tag: `alert-${symbol}` });
    n.onclick = () => {
      window.focus();
      window.location.hash = `#/coin/${symbol}`;
      n.close();
    };
  } catch {
    /* some browsers only allow notifications from a service worker; the on-page pop-up still appears */
  }
}
