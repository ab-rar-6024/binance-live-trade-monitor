import { ReactNode } from "react";
import { coinName } from "../format";

/** A titled block. `subtitle` is always visible and says in one sentence what the block shows. */
export function Section({
  title,
  subtitle,
  children,
  learn,
  actions,
  className = "",
}: {
  title: string;
  subtitle: ReactNode;
  children: ReactNode;
  /** Optional longer explanation, hidden until the reader asks for it. */
  learn?: ReactNode;
  /** Controls shown at the right of the heading (for example a time-range picker). */
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      <div className="card-head">
        <div>
          <h2>{title}</h2>
          <p className="subtitle">{subtitle}</p>
        </div>
        {actions && <div className="card-actions">{actions}</div>}
      </div>
      {children}
      {learn && (
        <details className="learn">
          <summary>What does this mean?</summary>
          <div className="learn-body">{learn}</div>
        </details>
      )}
    </section>
  );
}

/** A tug-of-war bar: the green side is buyers, the red side is sellers. */
export function TugBar({ buyPct, size = "normal", labels = false }: { buyPct: number; size?: "normal" | "big"; labels?: boolean }) {
  const buy = Math.max(0, Math.min(100, buyPct));
  return (
    <div className="tug-wrap">
      <div className={`tug ${size}`} role="img" aria-label={`${buy.toFixed(0)}% buyers, ${(100 - buy).toFixed(0)}% sellers`}>
        <div className="tug-buy" style={{ width: `${buy}%` }} />
      </div>
      {labels && (
        <div className="tug-labels">
          <span className="buy-text">Buyers {buy.toFixed(0)}%</span>
          <span className="sell-text">Sellers {(100 - buy).toFixed(0)}%</span>
        </div>
      )}
    </div>
  );
}

/** A price change with an arrow, so it never depends on colour alone. */
export function Change({ value, suffix = "" }: { value: number | null | undefined; suffix?: string }) {
  if (value === null || value === undefined) return <span className="muted">no data</span>;
  if (Math.abs(value) < 0.005) return <span className="muted">● unchanged{suffix}</span>;
  const up = value > 0;
  return (
    <span className={up ? "up" : "down"}>
      {up ? "▲" : "▼"} {Math.abs(value).toFixed(2)}%{suffix}
    </span>
  );
}

/** Star button to add or remove a coin from the watchlist. */
export function Star({ symbol, on, onToggle }: { symbol: string; on: boolean; onToggle: () => void }) {
  return (
    <button
      type="button"
      className={`star${on ? " on" : ""}`}
      aria-pressed={on}
      aria-label={`${on ? "Remove" : "Add"} ${coinName(symbol)} ${on ? "from" : "to"} your watchlist`}
      title={on ? "On your watchlist" : "Add to your watchlist"}
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        onToggle();
      }}
    >
      {on ? "★" : "☆"}
    </button>
  );
}
