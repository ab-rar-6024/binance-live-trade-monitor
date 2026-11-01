"""
Per-coin anomaly detectors: whale trades, price spikes and volume surges.

Pure Python (no Spark imports) so the logic is unit-testable. The Spark job feeds each
micro-batch of one coin's trades through `process_trades`, keeping a `CoinState` between
batches (Spark's stateful operator stores it in the checkpoint).

* Whale trade   - the trade's USD value is far above what is typical for that coin: it is
                  large in absolute terms, a high z-score of log(value) against an exponentially
                  decayed history, and a big multiple of the typical (geometric-mean) trade.
* Price spike   - the price moved more than SPIKE_PCT within the last 10 seconds.
* Volume surge  - this minute's traded value so far is a multiple of the median of recent
                  minutes (needs a few minutes of history first).
"""

import json
import math
import statistics
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Tuple

from backend.common.config import Thresholds

SPIKE_WINDOW_MS = 10_000
SPIKE_COOLDOWN_MS = 15_000
DECAY = 0.02  # weight of a new trade in the running mean/variance once history is established
MIN_HISTORY_FOR_DECAY = 50

STATE_SCHEMA = (
    "n double, mean double, var double, last_spike_ts long, prices string, minutes string, "
    "cur_minute long, cur_value double, last_surge_minute long"
)


@dataclass
class CoinState:
    n: float = 0.0
    mean: float = 0.0          # running mean of ln(trade value)
    var: float = 0.0           # running variance of ln(trade value)
    last_spike_ts: int = 0
    prices: List[List[float]] = field(default_factory=list)  # [[ts_ms, price]] within the spike window
    minutes: List[float] = field(default_factory=list)       # completed-minute traded values
    cur_minute: int = 0
    cur_value: float = 0.0
    last_surge_minute: int = 0

    def to_tuple(self) -> Tuple:
        return (self.n, self.mean, self.var, self.last_spike_ts, json.dumps(self.prices), json.dumps(self.minutes),
                self.cur_minute, self.cur_value, self.last_surge_minute)

    @classmethod
    def from_tuple(cls, t: Tuple) -> "CoinState":
        return cls(n=t[0], mean=t[1], var=t[2], last_spike_ts=t[3], prices=json.loads(t[4]), minutes=json.loads(t[5]),
                   cur_minute=t[6], cur_value=t[7], last_surge_minute=t[8])


def money(value: float) -> str:
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:.0f}"


def coin(symbol: str) -> str:
    return symbol[:-4] if symbol.endswith("USDT") else symbol


def _alert(kind: str, symbol: str, ts: int, severity: str, value: float, message: str, detail: Dict[str, Any],
           ing: int) -> Dict[str, Any]:
    return {"id": f"{kind}:{symbol}:{ts}", "type": kind, "s": symbol, "ts": int(ts), "severity": severity,
            "value": float(value), "message": message, "detail": json.dumps(detail, separators=(",", ":")), "ing": int(ing)}


def update_log_stats(state: CoinState, value: float) -> None:
    x = math.log(max(value, 1e-9))
    state.n += 1
    if state.n == 1:
        state.mean, state.var = x, 0.0
        return
    alpha = max(1.0 / state.n, DECAY) if state.n > MIN_HISTORY_FOR_DECAY else 1.0 / state.n
    delta = x - state.mean
    state.mean += alpha * delta
    state.var = (1 - alpha) * (state.var + alpha * delta * delta)


def process_trades(state: CoinState, symbol: str, trades: Iterable[Dict[str, Any]], th: Thresholds
                   ) -> Tuple[CoinState, List[Dict[str, Any]]]:
    """Run one coin's new trades (any order) through all detectors; returns (new state, alerts)."""
    alerts: List[Dict[str, Any]] = []
    for t in sorted(trades, key=lambda r: (r["ts"], r["id"])):
        ts, price, value, ing = int(t["ts"]), float(t["p"]), float(t["n"]), int(t.get("ing", 0))

        # ---- whale trade: judged against history BEFORE this trade is added to it
        if state.n >= th.whale_min_history and value >= th.whale_min_usd and state.var > 0:
            sd = math.sqrt(state.var)
            z = (math.log(max(value, 1e-9)) - state.mean) / sd
            typical = math.exp(state.mean)
            ratio = value / typical
            if z >= th.whale_z and ratio >= th.whale_ratio:
                severity = "critical" if value >= 250_000 else "warning"
                alerts.append(_alert(
                    "whale_trade", symbol, ts, severity, value,
                    f"{money(value)} {coin(symbol)} {t['side']} - {ratio:.0f}x the typical {coin(symbol)} trade",
                    {"notional": value, "side": t["side"], "price": price, "qty": t["q"], "z": round(z, 1),
                     "ratio": round(ratio, 1), "typical": round(typical, 2)}, ing))
        update_log_stats(state, value)

        # ---- price spike: move over the last 10 seconds
        state.prices = [p for p in state.prices if ts - p[0] <= SPIKE_WINDOW_MS] + [[ts, price]]
        if len(state.prices) >= 5 and ts - state.last_spike_ts >= SPIKE_COOLDOWN_MS:
            ref_ts, ref_price = state.prices[0]
            move = (price - ref_price) / ref_price * 100 if ref_price else 0.0
            if abs(move) >= th.spike_pct:
                state.last_spike_ts = ts
                seconds = max((ts - ref_ts) / 1000, 1)
                alerts.append(_alert(
                    "price_spike", symbol, ts, "critical" if abs(move) >= th.spike_pct * 3 else "warning", move,
                    f"{coin(symbol)} {move:+.2f}% in {seconds:.0f}s ({ref_price:g} -> {price:g})",
                    {"pct": round(move, 3), "from": ref_price, "to": price, "seconds": round(seconds, 1),
                     "trades": len(state.prices)}, ing))

        # ---- volume surge: this minute so far vs the median of recent minutes
        minute = ts // 60_000
        if state.cur_minute == 0:
            state.cur_minute = minute
        elif minute > state.cur_minute:
            state.minutes.append(state.cur_value)
            state.minutes.extend([0.0] * min(minute - state.cur_minute - 1, th.surge_history))  # silent minutes
            state.minutes = state.minutes[-th.surge_history:]
            state.cur_minute, state.cur_value = minute, 0.0
        if minute == state.cur_minute:
            state.cur_value += value
            if len(state.minutes) >= th.surge_min_history and minute != state.last_surge_minute:
                baseline = statistics.median(state.minutes)
                if baseline > 0 and state.cur_value >= max(th.surge_min_usd, th.surge_ratio * baseline):
                    state.last_surge_minute = minute
                    ratio = state.cur_value / baseline
                    alerts.append(_alert(
                        "volume_surge", symbol, ts, "critical" if ratio >= 3 * th.surge_ratio else "warning", ratio,
                        f"{coin(symbol)} volume {ratio:.1f}x normal ({money(state.cur_value)} this minute)",
                        {"ratio": round(ratio, 2), "minute_value": round(state.cur_value, 2),
                         "baseline": round(baseline, 2), "minutes_of_history": len(state.minutes)}, ing))
    return state, alerts
