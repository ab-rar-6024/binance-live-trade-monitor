import { menuFor, MENU, PageId, Route } from "../routes";

export function Sidebar({
  route,
  live,
  badges,
}: {
  route: Route;
  live: { state: "ok" | "warn" | "bad"; text: string; sub?: string };
  badges: Partial<Record<PageId, number>>;
}) {
  const active = menuFor(route);
  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">₿</div>
        <div>
          <h1>Live Crypto Market</h1>
          <p>Real trades from Binance, explained simply</p>
        </div>
      </div>

      <nav aria-label="Sections">
        <ul className="nav">
          {MENU.map((p) => (
            <li key={p.id}>
              <a href={`#/${p.id}`} className={active === p.id ? "active" : ""} aria-current={active === p.id ? "page" : undefined}>
                <span className="nav-icon" aria-hidden="true">{p.icon}</span>
                <span className="nav-text">
                  <span className="nav-label">{p.label}</span>
                  <span className="nav-hint">{p.hint}</span>
                </span>
                {badges[p.id] ? <span className="nav-badge">{badges[p.id]}</span> : null}
              </a>
            </li>
          ))}
        </ul>
      </nav>

      <div className={`status ${live.state}`} role="status">
        <span className="dot" />
        <span>
          <b>{live.text}</b>
          {live.sub && <span className="status-sub">{live.sub}</span>}
        </span>
      </div>
    </aside>
  );
}
