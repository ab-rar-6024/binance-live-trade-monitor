"""
A small SQLite history store, so the dashboard keeps its memory when the API restarts and can chart
more than the last hour.

Spark's one-minute windows and the alerts are written here (batched, from a background thread) and
read back at start-up. Kafka stays the source of truth for the live stream; this file only holds the
results that are worth keeping longer than Kafka's retention.
"""

import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("store")

WINDOW_COLUMNS = ["s", "ws", "trades", "volume", "notional", "vwap", "open", "high", "low", "close",
                  "buy_notional", "sell_notional", "buy_trades", "largest", "last_ts"]
ALERT_COLUMNS = ["id", "type", "s", "ts", "severity", "value", "message", "detail"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS windows (
    s TEXT NOT NULL, ws INTEGER NOT NULL,
    trades INTEGER, volume REAL, notional REAL, vwap REAL, open REAL, high REAL, low REAL, close REAL,
    buy_notional REAL, sell_notional REAL, buy_trades INTEGER, largest REAL, last_ts INTEGER,
    PRIMARY KEY (s, ws)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS windows_ws ON windows (ws);
CREATE TABLE IF NOT EXISTS alerts (
    id TEXT PRIMARY KEY, type TEXT, s TEXT, ts INTEGER, severity TEXT, value REAL, message TEXT, detail TEXT
);
CREATE INDEX IF NOT EXISTS alerts_ts ON alerts (ts);
"""


class Store:
    def __init__(self, path: Path, flush_seconds: float = 2.0, window_days: int = 7, alert_days: int = 30) -> None:
        self.path = Path(path)
        self.flush_seconds = flush_seconds
        self.window_days, self.alert_days = window_days, alert_days
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._windows: Dict[tuple, Dict[str, Any]] = {}
        self._alerts: Dict[str, Dict[str, Any]] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        with self._connect() as db:
            db.executescript(SCHEMA)
        self.prune()

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.row_factory = sqlite3.Row
        return db

    # ---------------------------------------------------------------- writing (batched)
    def put_window(self, rec: Dict[str, Any]) -> None:
        with self._lock:
            self._windows[(rec["s"], rec["ws"])] = rec  # later updates of the same minute replace earlier ones

    def put_alert(self, rec: Dict[str, Any]) -> None:
        with self._lock:
            self._alerts[rec["id"]] = rec

    def flush(self) -> int:
        with self._lock:
            windows, alerts = list(self._windows.values()), list(self._alerts.values())
            self._windows, self._alerts = {}, {}
        if not windows and not alerts:
            return 0
        with self._connect() as db:
            db.executemany(
                f"INSERT OR REPLACE INTO windows ({','.join(WINDOW_COLUMNS)}) VALUES ({','.join('?' * len(WINDOW_COLUMNS))})",
                [[w.get(c) for c in WINDOW_COLUMNS] for w in windows])
            db.executemany(
                f"INSERT OR REPLACE INTO alerts ({','.join(ALERT_COLUMNS)}) VALUES ({','.join('?' * len(ALERT_COLUMNS))})",
                [[a.get(c) for c in ALERT_COLUMNS] for a in alerts])
        return len(windows) + len(alerts)

    def _run(self) -> None:
        last_prune = time.time()
        while not self._stop.wait(self.flush_seconds):
            try:
                self.flush()
                if time.time() - last_prune > 3600:
                    self.prune()
                    last_prune = time.time()
            except Exception:
                log.exception("could not write to the history database")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="store-writer", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        try:
            self.flush()
        except Exception:
            log.exception("final flush failed")

    def prune(self) -> None:
        now = int(time.time() * 1000)
        with self._connect() as db:
            db.execute("DELETE FROM windows WHERE ws < ?", (now - self.window_days * 86_400_000,))
            db.execute("DELETE FROM alerts WHERE ts < ?", (now - self.alert_days * 86_400_000,))

    # ---------------------------------------------------------------- reading
    def load_windows(self, since_ms: int) -> List[Dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM windows WHERE ws >= ? ORDER BY ws", (since_ms,)).fetchall()
        return [dict(r) for r in rows]

    def load_alerts(self, since_ms: int) -> List[Dict[str, Any]]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM alerts WHERE ts >= ? ORDER BY ts", (since_ms,)).fetchall()
        return [dict(r) for r in rows]

    def latest_window_ts(self) -> Optional[int]:
        with self._connect() as db:
            row = db.execute("SELECT MAX(ws) FROM windows").fetchone()
        return row[0]

    def latest_alert_ts(self) -> Optional[int]:
        with self._connect() as db:
            row = db.execute("SELECT MAX(ts) FROM alerts").fetchone()
        return row[0]

    def alert_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """How many alerts of each kind fired per coin, per day (UTC): used to judge whether thresholds are sensible."""
        since = int(time.time() * 1000) - days * 86_400_000
        with self._connect() as db:
            rows = db.execute(
                "SELECT date(ts/1000, 'unixepoch') AS day, s, type, COUNT(*) AS n FROM alerts WHERE ts >= ? "
                "GROUP BY day, s, type ORDER BY day DESC, n DESC", (since,)).fetchall()
        return [dict(r) for r in rows]
