import { useEffect } from "react";
import { Alert } from "../api";
import { coinName } from "../format";
import { coinLink } from "../routes";
import { describe, KINDS } from "./AlertsPanel";

export interface Toast {
  key: string;
  alert: Alert;
}

const LIFETIME_MS = 10_000;

function ToastItem({ toast, onClose }: { toast: Toast; onClose: (key: string) => void }) {
  useEffect(() => {
    const timer = window.setTimeout(() => onClose(toast.key), LIFETIME_MS);
    return () => window.clearTimeout(timer);
  }, [toast.key, onClose]);

  const text = describe(toast.alert);
  return (
    <div className={`toast ${toast.alert.severity}`} role="status">
      <span className="alert-icon" aria-hidden="true">{KINDS[toast.alert.type].icon}</span>
      <div className="toast-body">
        <div className="alert-headline">{text.headline}</div>
        <a href={coinLink(toast.alert.s)} onClick={() => onClose(toast.key)}>Open {coinName(toast.alert.s)}</a>
      </div>
      <button className="toast-close" aria-label="Dismiss" onClick={() => onClose(toast.key)}>×</button>
    </div>
  );
}

/** Small pop-ups in the corner for new unusual moments. */
export function Toasts({ toasts, onClose }: { toasts: Toast[]; onClose: (key: string) => void }) {
  if (!toasts.length) return null;
  return (
    <div className="toasts" aria-live="polite">
      {toasts.map((t) => <ToastItem key={t.key} toast={t} onClose={onClose} />)}
    </div>
  );
}
