"""
The API's live picture of the market, rebuilt from Kafka.

Four consumer threads read the topics the pipeline writes:

  trades.raw      -> latest price per coin, recent trade feed, trades/second, Kafka transit latency
  trades.agg1m    -> one-minute windows per coin (Spark)            -> prices, volume, pressure, ranking
  trades.alerts   -> detector output (Spark)                        -> alert feed
  spark.progress  -> Spark batch statistics                         -> pipeline health

On start-up the hub first loads the last day of windows and alerts from the SQLite history store
(`store.py`), then each consumer replays only what the store is missing (found with offsets_for_times),
so the dashboard is populated immediately and survives restarts.
"""

import json
import logging
import threading
import time
from collections import defaultdict, deque
from typing import Any, Callable, Deque, Dict, List, Optional

from confluent_kafka import OFFSET_END, Consumer, TopicPartition

from backend.common.config import settings
from backend.common.kafka_admin import topic_offsets

from .store import Store

log = logging.getLogger("hub")
MINUTE = 60_000
KEEP_MINUTES = 1440        # one day of one-minute windows per coin is kept in memory
MAX_REPLAY_S = 72 * 3600   # Kafka retention


def auto_bucket(minutes: int) -> int:
    """Minutes per chart point, so any range stays around 60-150 points."""
    return 1 if minutes <= 180 else 5 if minutes <= 720 else 15


def percentile(values: List[float], pct: float) -> Optional[float]:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(pct / 100 * (len(ordered) - 1))))]


class Hub:
    def __init__(self, store: Optional[Store] = None) -> None:
        self.store = store
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.threads: List[threading.Thread] = []
        # raw trades
        self.last: Dict[str, Dict[str, Any]] = {}
        self.feed: Deque[Dict[str, Any]] = deque(maxlen=400)
        self.by_symbol: Dict[str, Deque[Dict[str, Any]]] = defaultdict(lambda: deque(maxlen=80))
        self.trade_times: Deque[float] = deque(maxlen=5000)
        self.kafka_latency: Deque[tuple] = deque(maxlen=2000)   # (arrival_s, ms from producer to API)
        # spark aggregates: symbol -> {window_start_ms: record}
        self.aggs: Dict[str, Dict[int, Dict[str, Any]]] = defaultdict(dict)
        self.spark_latency: Deque[tuple] = deque(maxlen=1000)   # (arrival_s, ms from producer to Spark result)
        # alerts
        self.alerts: Deque[Dict[str, Any]] = deque(maxlen=1500)
        self.alert_ids: set = set()
        self.alert_seq = 0
        # spark progress + topic statistics
        self.progress: Dict[str, Dict[str, Any]] = {}
        self.topic_stats: Dict[str, Dict[str, int]] = {}
        self.kafka_ok = False
        self.started = time.time()
        self.counts = defaultdict(int)

    # ------------------------------------------------------------------ handlers
    def on_trade(self, rec: Dict[str, Any], live: bool = True) -> None:
        """`live` is False for messages replayed at start-up: they fill the feed but not the rate/latency stats."""
        now = time.time()
        with self.lock:
            self.last[rec["s"]] = {"price": rec["p"], "ts": rec["ts"], "side": rec["side"]}
            self.feed.append(rec)
            self.by_symbol[rec["s"]].append(rec)
            if live:
                self.trade_times.append(now)
                self.counts["trades"] += 1
                if rec.get("ing"):
                    self.kafka_latency.append((now, max(0.0, now * 1000 - rec["ing"])))

    def _add_agg(self, rec: Dict[str, Any]) -> None:
        windows = self.aggs[rec["s"]]
        windows[rec["ws"]] = rec
        if len(windows) > KEEP_MINUTES + 60:  # trim in batches so replaying history stays cheap
            for ws in sorted(windows)[:-KEEP_MINUTES]:
                del windows[ws]

    def on_agg(self, rec: Dict[str, Any], live: bool = True) -> None:
        now = time.time()
        with self.lock:
            self._add_agg(rec)
            if live and rec.get("last_ing"):
                self.spark_latency.append((now, max(0.0, now * 1000 - rec["last_ing"])))
            self.counts["aggs"] += 1
        if self.store:
            self.store.put_window(rec)

    def _add_alert(self, rec: Dict[str, Any]) -> bool:
        if rec["id"] in self.alert_ids:
            return False
        self.alert_ids.add(rec["id"])
        detail = rec.get("detail")
        if isinstance(detail, (str, type(None))):
            try:
                rec["detail"] = json.loads(detail or "{}")
            except ValueError:
                rec["detail"] = {}
        self.alert_seq += 1
        rec["seq"] = self.alert_seq
        if len(self.alerts) == self.alerts.maxlen:
            self.alert_ids.discard(self.alerts[0]["id"])
        self.alerts.append(rec)
        return True

    def on_alert(self, rec: Dict[str, Any], live: bool = True) -> None:
        raw_detail = rec.get("detail")
        with self.lock:
            added = self._add_alert(rec)
            if added:
                self.counts["alerts"] += 1
        if added and self.store:
            self.store.put_alert({**rec, "detail": raw_detail if isinstance(raw_detail, str) else json.dumps(raw_detail or {})})

    def on_progress(self, rec: Dict[str, Any], live: bool = True) -> None:
        with self.lock:
            self.progress[rec["query"]] = {**rec, "seen": time.time()}

    # ------------------------------------------------------------------ consumers
    def _consume(self, topic: str, handler: Callable[..., None], replay_seconds: int) -> None:
        group = f"binance-api-{topic}-{int(self.started)}"
        while not self.stop.is_set():
            consumer = Consumer({"bootstrap.servers": settings.bootstrap, "group.id": group, "enable.auto.commit": False,
                                 "auto.offset.reset": "latest", "fetch.min.bytes": 1, "fetch.wait.max.ms": 100})
            try:
                meta = consumer.list_topics(topic, timeout=10).topics[topic]
                since = int((time.time() - replay_seconds) * 1000)
                wanted = [TopicPartition(topic, p, since) for p in meta.partitions]
                assigned = []
                for tp in consumer.offsets_for_times(wanted, timeout=10):
                    assigned.append(TopicPartition(topic, tp.partition, tp.offset if tp.offset >= 0 else OFFSET_END))
                consumer.assign(assigned)
                self.kafka_ok = True
                while not self.stop.is_set():
                    msg = consumer.poll(0.25)
                    if msg is None:
                        continue
                    if msg.error():
                        log.warning("%s: %s", topic, msg.error())
                        continue
                    try:
                        # a message written within the last 5 s is "live"; older ones are start-up replay
                        live = time.time() * 1000 - msg.timestamp()[1] < 5000
                        handler(json.loads(msg.value()), live)
                    except Exception:
                        log.exception("bad message on %s", topic)
            except Exception as exc:
                self.kafka_ok = False
                log.warning("consumer for %s failed (%s); retrying in 3s", topic, exc)
                time.sleep(3)
            finally:
                try:
                    consumer.close()
                except Exception:
                    pass

    def _watch_topics(self) -> None:
        while not self.stop.is_set():
            for topic in settings.topics.all():
                try:
                    stats = topic_offsets(topic, group="binance-api-stats")
                    if stats:
                        with self.lock:
                            self.topic_stats[topic] = stats
                except Exception:
                    pass
            self.stop.wait(10)

    def warm_load(self) -> None:
        """Fill the in-memory picture from the history store (before any Kafka replay)."""
        if not self.store:
            return
        now = int(time.time() * 1000)
        with self.lock:
            for rec in self.store.load_windows(now - KEEP_MINUTES * MINUTE):
                self._add_agg(rec)
            for rec in self.store.load_alerts(now - 7 * 86_400_000)[-1500:]:
                self._add_alert(rec)
        log.info("history store: %d coins and %d alerts loaded", len(self.aggs), len(self.alerts))

    @staticmethod
    def replay_horizon(newest_stored_ms: Optional[int], minimum_s: int) -> int:
        """Seconds of Kafka history to replay: back to the newest stored record (plus 5 min), never less than `minimum_s`."""
        if newest_stored_ms is None:
            return MAX_REPLAY_S
        gap = int(time.time() - newest_stored_ms / 1000) + 300
        return max(minimum_s, min(MAX_REPLAY_S, gap))

    def start(self) -> None:
        self.warm_load()
        newest_window = newest_alert = None
        if self.store:
            newest_window, newest_alert = self.store.latest_window_ts(), self.store.latest_alert_ts()
            self.store.start()
        plan = [
            (settings.topics.raw, self.on_trade, 120),
            (settings.topics.agg, self.on_agg, self.replay_horizon(newest_window, 1800)),
            (settings.topics.alerts, self.on_alert, self.replay_horizon(newest_alert, 1800)),
            (settings.topics.progress, self.on_progress, 60),
        ]
        for topic, handler, replay in plan:
            t = threading.Thread(target=self._consume, args=(topic, handler, replay), name=f"consume-{topic}", daemon=True)
            t.start()
            self.threads.append(t)
        t = threading.Thread(target=self._watch_topics, name="topic-stats", daemon=True)
        t.start()
        self.threads.append(t)

    def close(self) -> None:
        self.stop.set()
        if self.store:
            self.store.close()

    # ------------------------------------------------------------------ views
    def overview(self) -> List[Dict[str, Any]]:
        now_ms = int(time.time() * 1000)
        cur = now_ms // MINUTE * MINUTE
        rows = []
        with self.lock:
            symbols = sorted(set(self.last) | set(self.aggs) | set(settings.symbols))
            for s in symbols:
                last = self.last.get(s)
                windows = self.aggs.get(s, {})
                w = windows.get(cur)
                recent = [windows[k] for k in sorted(windows) if k >= cur - 4 * MINUTE]
                price = last["price"] if last else (windows[max(windows)]["close"] if windows else None)
                ref = next((windows[k]["open"] for k in sorted(windows) if k >= cur - 5 * MINUTE), None)
                notional5 = sum(r["notional"] for r in recent)
                buy5 = sum(r["buy_notional"] for r in recent)
                closes = [windows[k]["close"] for k in sorted(windows)[-30:]]
                rows.append({
                    "symbol": s, "price": price, "ts": last["ts"] if last else None,
                    "change_5m_pct": round((price - ref) / ref * 100, 3) if price and ref else None,
                    "minute": {
                        "trades": w["trades"] if w else 0, "notional": round(w["notional"], 2) if w else 0.0,
                        "vwap": round(w["vwap"], 6) if w and w.get("vwap") else None,
                        "buy_ratio": round(w["buy_notional"] / w["notional"], 4) if w and w["notional"] else None,
                    },
                    "buy_ratio_5m": round(buy5 / notional5, 4) if notional5 else None,
                    "notional_5m": round(notional5, 2),
                    "spark": closes,
                })
        return rows

    def series(self, symbol: str, minutes: int, bucket: Optional[int] = None) -> List[Dict[str, Any]]:
        """Candles for a coin. Longer ranges are merged into `bucket`-minute candles (auto-chosen when not given)."""
        bucket = bucket or auto_bucket(minutes)
        size = bucket * MINUTE
        since = int(time.time() * 1000) // size * size - (max(minutes // bucket, 1) - 1) * size
        with self.lock:
            windows = self.aggs.get(symbol, {})
            picked = [windows[ws] for ws in sorted(windows) if ws >= since]
        groups: Dict[int, List[Dict[str, Any]]] = {}
        for w in picked:
            groups.setdefault(w["ws"] // size * size, []).append(w)
        out = []
        for start in sorted(groups):
            g = groups[start]
            notional = sum(w["notional"] for w in g)
            volume = sum(w.get("volume") or 0 for w in g)
            out.append({
                "ws": start, "open": g[0]["open"], "high": max(w["high"] for w in g), "low": min(w["low"] for w in g),
                "close": g[-1]["close"], "vwap": notional / volume if volume else g[-1].get("vwap"),
                "notional": notional, "trades": sum(w["trades"] for w in g),
                "buy_notional": sum(w["buy_notional"] for w in g), "sell_notional": sum(w["sell_notional"] for w in g),
                "largest": max(w["largest"] for w in g), "bucket_min": bucket,
            })
        return out

    def coin_summary(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Headline numbers for one coin: price, changes, 24-hour range and volume, buyer share, rank."""
        cur = int(time.time() * 1000) // MINUTE * MINUTE
        ranking = [r["symbol"] for r in self.hot(5)]
        with self.lock:
            windows = self.aggs.get(symbol, {})
            last = self.last.get(symbol)
            if not windows and not last:
                return None
            ordered = sorted(windows)
            price = last["price"] if last else windows[ordered[-1]]["close"]

            def change_since(minutes: int) -> Optional[float]:
                ref = next((windows[k]["open"] for k in ordered if k >= cur - minutes * MINUTE), None)
                return round((price - ref) / ref * 100, 3) if ref else None

            def span(minutes: int) -> List[Dict[str, Any]]:
                return [windows[k] for k in ordered if k >= cur - (minutes - 1) * MINUTE]

            def buy_pct(rows: List[Dict[str, Any]]) -> Optional[float]:
                total = sum(r["notional"] for r in rows)
                return round(100 * sum(r["buy_notional"] for r in rows) / total, 1) if total else None

            day, hour, five = span(1440), span(60), span(5)
            return {
                "symbol": symbol, "price": price, "ts": last["ts"] if last else None,
                "change_5m_pct": change_since(5), "change_1h_pct": change_since(60), "change_24h_pct": change_since(1440),
                "high_24h": max((r["high"] for r in day), default=None), "low_24h": min((r["low"] for r in day), default=None),
                "notional_5m": round(sum(r["notional"] for r in five), 2),
                "notional_1h": round(sum(r["notional"] for r in hour), 2),
                "notional_24h": round(sum(r["notional"] for r in day), 2),
                "trades_24h": sum(r["trades"] for r in day), "largest_24h": max((r["largest"] for r in day), default=None),
                "buy_pct_5m": buy_pct(five), "buy_pct_1h": buy_pct(hour),
                "rank_5m": ranking.index(symbol) + 1 if symbol in ranking else None, "of": len(ranking),
                "minutes_of_data": len(windows),
            }

    def hot(self, minutes: int = 5) -> List[Dict[str, Any]]:
        now_ms = int(time.time() * 1000)
        cur = now_ms // MINUTE * MINUTE
        lo, prev_lo = cur - (minutes - 1) * MINUTE, cur - (2 * minutes - 1) * MINUTE
        out = []
        with self.lock:
            for s, windows in self.aggs.items():
                now_part = [r for ws, r in windows.items() if ws >= lo]
                prev_part = [r for ws, r in windows.items() if prev_lo <= ws < lo]
                notional, prev = sum(r["notional"] for r in now_part), sum(r["notional"] for r in prev_part)
                if notional <= 0:
                    continue
                out.append({"symbol": s, "notional": round(notional, 2), "trades": sum(r["trades"] for r in now_part),
                            "change_vs_prev_pct": round((notional - prev) / prev * 100, 1) if prev else None})
        out.sort(key=lambda r: -r["notional"])
        total = sum(r["notional"] for r in out) or 1.0
        for rank, row in enumerate(out, 1):
            row["rank"], row["share_pct"] = rank, round(100 * row["notional"] / total, 1)
        return out

    def pressure(self, minutes: int = 5) -> Dict[str, Any]:
        cur = int(time.time() * 1000) // MINUTE * MINUTE
        lo = cur - (minutes - 1) * MINUTE
        coins, buy_total, sell_total = [], 0.0, 0.0
        with self.lock:
            for s, windows in self.aggs.items():
                buy = sum(r["buy_notional"] for ws, r in windows.items() if ws >= lo)
                sell = sum(r["sell_notional"] for ws, r in windows.items() if ws >= lo)
                if buy + sell > 0:
                    coins.append({"symbol": s, "buy": round(buy, 2), "sell": round(sell, 2),
                                  "buy_pct": round(100 * buy / (buy + sell), 1)})
                    buy_total, sell_total = buy_total + buy, sell_total + sell
        coins.sort(key=lambda r: -(r["buy"] + r["sell"]))
        overall = round(100 * buy_total / (buy_total + sell_total), 1) if buy_total + sell_total else None
        return {"minutes": minutes, "coins": coins, "buy_pct": overall, "buy": round(buy_total, 2), "sell": round(sell_total, 2)}

    def recent_alerts(self, limit: int = 100, kind: Optional[str] = None, symbol: Optional[str] = None,
                      since: Optional[int] = None) -> List[Dict[str, Any]]:
        with self.lock:
            items = [a for a in self.alerts if (not kind or a["type"] == kind) and (not symbol or a["s"] == symbol)
                     and (since is None or a["ts"] >= since)]
        items.sort(key=lambda a: a["ts"], reverse=True)
        return items[:limit]

    def recent_trades(self, limit: int = 100, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        with self.lock:
            items = list(self.by_symbol.get(symbol, [])) if symbol else list(self.feed)
        return items[-limit:][::-1]

    def system(self) -> Dict[str, Any]:
        now = time.time()
        with self.lock:
            recent = [t for t in self.trade_times if now - t <= 10]
            rate = len(recent) / 10 if now - self.started > 10 else len(recent) / max(now - self.started, 1)
            kafka_lat = [v for t, v in self.kafka_latency if now - t <= 60]
            spark_lat = [v for t, v in self.spark_latency if now - t <= 60]
            last_trade_age = now - self.trade_times[-1] if self.trade_times else None
            spark = {q: {**p, "age_s": round(now - p["seen"], 1)} for q, p in self.progress.items()}
            alive = bool(spark) and all(p["age_s"] < 15 for p in spark.values())
            return {
                "kafka": {"connected": self.kafka_ok, "topics": dict(self.topic_stats)},
                "binance_feed": {"trades_per_second": round(rate, 2),
                                 "last_trade_age_s": round(last_trade_age, 1) if last_trade_age is not None else None,
                                 "status": "live" if last_trade_age is not None and last_trade_age < 15 else "stalled"},
                "spark": {"alive": alive, "queries": spark},
                "latency_ms": {
                    "producer_to_api_p50": percentile(kafka_lat, 50), "producer_to_api_p95": percentile(kafka_lat, 95),
                    "producer_to_spark_p50": percentile(spark_lat, 50), "producer_to_spark_p95": percentile(spark_lat, 95),
                },
                "counts": dict(self.counts),
                "uptime_s": round(now - self.started),
            }
