import { useState } from "react";
import { AlertType } from "../api";
import { coinName, ticker } from "../format";
import { askNotificationPermission, notificationPermission, PermissionState, playBeep, showSystemNotification } from "../notifications";
import { Settings, Theme, useSettings } from "../settings";
import { KINDS } from "./AlertsPanel";
import { Section } from "./ui";

const THEMES: { id: Theme; label: string; hint: string }[] = [
  { id: "system", label: "Match my device", hint: "Light or dark, following your computer" },
  { id: "light", label: "Light", hint: "" },
  { id: "dark", label: "Dark", hint: "" },
];

const BIG_TRADE_STEPS = [25_000, 50_000, 100_000, 250_000, 500_000];

function Toggle({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean }) {
  return (
    <label className={`toggle${disabled ? " disabled" : ""}`}>
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span className="toggle-text">
        <span className="strong">{label}</span>
        {hint && <span className="muted small">{hint}</span>}
      </span>
    </label>
  );
}

const permissionText: Record<PermissionState, string> = {
  granted: "System notifications are allowed.",
  denied: "System notifications are blocked in your browser. Pop-ups on this page still work. To allow them, change the site setting in your browser's address bar.",
  default: "System notifications have not been allowed yet. Pop-ups on this page work without it.",
  unsupported: "This browser does not support system notifications. Pop-ups on this page still work.",
};

export default function SettingsPage({ symbols, detectorFloor }: { symbols: string[]; detectorFloor?: number }) {
  const { settings, update, toggleWatch, reset } = useSettings();
  const [permission, setPermission] = useState<PermissionState>(notificationPermission());

  const setType = (type: AlertType, on: boolean) => update({ types: { ...settings.types, [type]: on } } as Partial<Settings>);

  return (
    <>
      <Section title="Appearance" subtitle="Choose how the page looks. Your choice is remembered on this device.">
        <div className="segmented wide" role="radiogroup" aria-label="Theme">
          {THEMES.map((t) => (
            <button key={t.id} role="radio" aria-checked={settings.theme === t.id} className={settings.theme === t.id ? "active" : ""} onClick={() => update({ theme: t.id })}>
              {t.label}
            </button>
          ))}
        </div>
      </Section>

      <Section
        title="Alerts"
        subtitle="Get told about unusual moments without watching the page. Pop-ups appear while this page is open in a browser tab."
        learn={<p>Alerts only come from the live data this page receives, so the page (or at least its browser tab) needs to stay open.</p>}
      >
        <div className="form">
          <Toggle
            label="Alert me about unusual moments"
            hint="Shows a pop-up in the corner when something new happens."
            checked={settings.notify}
            onChange={(on) => update({ notify: on })}
          />
          <Toggle label="Play a short sound" checked={settings.sound} disabled={!settings.notify} onChange={(on) => { update({ sound: on }); if (on) playBeep(); }} />

          <div className="field">
            <div className="strong">What should alert me?</div>
            <div className="checks">
              {(Object.keys(KINDS) as AlertType[]).map((t) => (
                <label key={t} className="check">
                  <input type="checkbox" checked={settings.types[t]} disabled={!settings.notify} onChange={(e) => setType(t, e.target.checked)} />
                  {KINDS[t].icon} {KINDS[t].name}
                </label>
              ))}
            </div>
          </div>

          <div className="field">
            <label className="strong" htmlFor="severity">How unusual?</label>
            <select id="severity" value={settings.minSeverity} disabled={!settings.notify}
              onChange={(e) => update({ minSeverity: e.target.value === "critical" ? "critical" : "warning" })}>
              <option value="warning">Anything unusual</option>
              <option value="critical">Only the very unusual</option>
            </select>
          </div>

          <Toggle label="Only for coins on my watchlist" hint={`${settings.watchlist.length} coin${settings.watchlist.length === 1 ? "" : "s"} starred`}
            checked={settings.watchOnly} disabled={!settings.notify} onChange={(on) => update({ watchOnly: on })} />

          <div className="field">
            <label className="strong" htmlFor="bigtrade">Smallest big trade to show</label>
            <select id="bigtrade" value={settings.minWhaleUsd} onChange={(e) => update({ minWhaleUsd: Number(e.target.value) })}>
              {BIG_TRADE_STEPS.map((v) => <option key={v} value={v}>${v.toLocaleString()}</option>)}
            </select>
            <span className="muted small">Smaller big trades are hidden from the list and never alert you. {detectorFloor ? `The detector itself already ignores anything under $${detectorFloor.toLocaleString()}.` : ""}</span>
          </div>

          <div className="field">
            <div className="strong">System notifications</div>
            <p className="muted small">{permissionText[permission]}</p>
            <div className="row">
              {permission !== "granted" && permission !== "unsupported" && permission !== "denied" && (
                <button className="button" onClick={async () => setPermission(await askNotificationPermission())}>Allow system notifications</button>
              )}
              <button className="button secondary" onClick={() => { playBeep(); showSystemNotification("Test alert", "This is how an alert will look.", "BTCUSDT"); }}>
                Send a test
              </button>
            </div>
          </div>
        </div>
      </Section>

      <Section title="My watchlist" subtitle="Star the coins you care about. They get their own list on the Overview page, and you can limit alerts to them.">
        <div className="row spaced">
          <button className="button secondary" onClick={() => update({ watchlist: [...symbols] })} disabled={!symbols.length}>Select all</button>
          <button className="button secondary" onClick={() => update({ watchlist: [] })} disabled={!settings.watchlist.length}>Clear</button>
        </div>
        <div className="checks grid">
          {symbols.length === 0 && <div className="empty">The coin list is loading…</div>}
          {symbols.map((s) => (
            <label key={s} className="check">
              <input type="checkbox" checked={settings.watchlist.includes(s)} onChange={() => toggleWatch(s)} />
              {coinName(s)} <span className="ticker">{ticker(s)}</span>
            </label>
          ))}
        </div>
      </Section>

      <Section title="Reset" subtitle="Put every setting back to how it was the first time you opened the page.">
        <button className="button secondary" onClick={reset}>Reset all settings</button>
      </Section>
    </>
  );
}
