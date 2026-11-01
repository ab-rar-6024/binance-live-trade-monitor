"""History store, warm start, bucketed series, coin summary and the API protections."""

import json
import time

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.hub import MINUTE, Hub, auto_bucket
from backend.app.security import ConnectionLimiter, RateLimiter
from backend.app.store import Store


def window(symbol, ws, close=100.0, notional=1000.0, buy=600.0, trades=10, high=None, low=None):
    return {"ws": ws, "we": ws + MINUTE, "s": symbol, "trades": trades, "volume": notional / close, "notional": notional,
            "vwap": close, "open": close, "high": high or close, "low": low or close, "close": close, "buy_notional": buy,
            "sell_notional": notional - buy, "buy_trades": 6, "largest": 150.0, "last_ts": ws + 1000}


def alert(ident, symbol="BTCUSDT", kind="whale_trade", ts=None):
    ts = ts or int(time.time() * 1000)
    return {"id": ident, "type": kind, "s": symbol, "ts": ts, "severity": "warning", "value": 1.0, "message": "m",
            "detail": json.dumps({"side": "buy"})}


@pytest.fixture
def store(tmp_path):
    s = Store(tmp_path / "t.db", flush_seconds=0.05)
    yield s
    s.close()


class TestStore:
    def test_windows_survive_and_later_updates_replace_earlier_ones(self, store):
        now = int(time.time() * 1000) // MINUTE * MINUTE
        store.put_window(window("BTCUSDT", now, notional=100))
        store.put_window(window("BTCUSDT", now, notional=900))  # Spark re-emits the same minute as it grows
        store.flush()

        rows = store.load_windows(now - MINUTE)

        assert len(rows) == 1 and rows[0]["notional"] == 900

    def test_alerts_are_deduplicated_by_id(self, store):
        store.put_alert(alert("a"))
        store.put_alert(alert("a"))
        store.flush()

        assert len(store.load_alerts(0)) == 1

    def test_old_rows_are_pruned(self, tmp_path):
        s = Store(tmp_path / "p.db", window_days=1, alert_days=1)
        now = int(time.time() * 1000)
        s.put_window(window("BTCUSDT", now - 3 * 86_400_000))
        s.put_window(window("BTCUSDT", now // MINUTE * MINUTE))
        s.put_alert(alert("old", ts=now - 3 * 86_400_000))
        s.flush()
        s.prune()

        assert len(s.load_windows(0)) == 1 and s.load_alerts(0) == []

    def test_alert_stats_count_per_day_coin_and_type(self, store):
        store.put_alert(alert("1", "BTCUSDT", "whale_trade"))
        store.put_alert(alert("2", "BTCUSDT", "whale_trade"))
        store.put_alert(alert("3", "ETHUSDT", "price_spike"))
        store.flush()

        rows = {(r["s"], r["type"]): r["n"] for r in store.alert_stats(1)}

        assert rows == {("BTCUSDT", "whale_trade"): 2, ("ETHUSDT", "price_spike"): 1}

    def test_background_writer_flushes_by_itself(self, store):
        store.start()
        store.put_alert(alert("bg"))
        time.sleep(0.4)

        assert len(store.load_alerts(0)) == 1


class TestWarmStart:
    def test_a_new_hub_remembers_history_from_the_store(self, store):
        now = int(time.time() * 1000) // MINUTE * MINUTE
        first = Hub(store)
        for i in range(5):
            first.on_agg(window("BTCUSDT", now - i * MINUTE))
        first.on_alert(alert("w1"))
        store.flush()

        second = Hub(store)
        second.warm_load()

        assert len(second.series("BTCUSDT", 10)) == 5
        assert second.recent_alerts()[0]["id"] == "w1" and second.recent_alerts()[0]["detail"] == {"side": "buy"}

    def test_replay_horizon_covers_the_gap_since_the_last_stored_record(self):
        assert Hub.replay_horizon(None, 1800) == 72 * 3600  # empty store: replay all of Kafka's history
        recent = int(time.time() * 1000) - 60_000
        assert Hub.replay_horizon(recent, 1800) == 1800     # fresh store: just the minimum
        old = int(time.time() * 1000) - 3 * 3600_000
        assert 3 * 3600 <= Hub.replay_horizon(old, 1800) <= 3 * 3600 + 400


class TestSeriesAndSummary:
    @pytest.fixture
    def hub(self):
        h = Hub()
        self.now = int(time.time() * 1000) // MINUTE * MINUTE
        for i in range(120):  # two hours of BTC, price rising 1.0 per minute, 1000 USD per minute
            h.on_agg(window("BTCUSDT", self.now - (119 - i) * MINUTE, close=100 + i, notional=1000, buy=700,
                            high=101 + i, low=99 + i))
        h.on_trade({"s": "BTCUSDT", "id": 1, "p": 219.0, "q": 1.0, "n": 219.0, "ts": self.now, "side": "buy", "ing": self.now}, True)
        return h

    def test_auto_bucket_keeps_point_counts_reasonable(self):
        assert [auto_bucket(m) for m in (60, 180, 360, 720, 1440)] == [1, 1, 5, 5, 15]

    def test_one_hour_is_one_point_per_minute(self, hub):
        assert len(hub.series("BTCUSDT", 60)) == 60

    def test_long_ranges_merge_minutes_into_correct_candles(self, hub):
        candles = hub.series("BTCUSDT", 120, bucket=10)

        assert 11 <= len(candles) <= 13 and all(c["bucket_min"] == 10 for c in candles)
        mid = candles[3]  # buckets line up with the clock, so only look at one that is completely filled
        i0 = (mid["ws"] - (self.now - 119 * MINUTE)) // MINUTE  # index of its first minute in the generated data
        assert mid["notional"] == 10_000 and mid["trades"] == 100
        assert mid["open"] == 100 + i0 and mid["close"] == 109 + i0      # first minute's open, last minute's close
        assert mid["high"] == 110 + i0 and mid["low"] == 99 + i0         # extremes across the ten minutes
        assert mid["buy_notional"] + mid["sell_notional"] == pytest.approx(mid["notional"])
        # true VWAP = money traded / coins traded (here $1000 a minute at rising prices)
        assert mid["vwap"] == pytest.approx(10_000 / sum(1000 / (100 + i0 + k) for k in range(10)))

    def test_coin_summary_numbers(self, hub):
        s = hub.coin_summary("BTCUSDT")

        assert s["price"] == 219.0 and s["rank_5m"] == 1
        assert s["notional_1h"] == 60_000 and s["notional_24h"] == 120_000 and s["trades_24h"] == 1200
        assert s["high_24h"] == 220 and s["low_24h"] == 99
        assert s["buy_pct_1h"] == 70.0
        assert s["change_1h_pct"] > 0 and s["minutes_of_data"] == 120

    def test_unknown_coin_has_no_summary(self, hub):
        assert hub.coin_summary("NOPEUSDT") is None

    def test_per_coin_trade_feed_is_not_crowded_out_by_busy_coins(self):
        h = Hub()
        h.on_trade({"s": "SLOWUSDT", "id": 1, "p": 1, "q": 1, "n": 1, "ts": 1, "side": "buy", "ing": 1}, False)
        for i in range(1000):  # a busy coin floods the shared feed
            h.on_trade({"s": "BTCUSDT", "id": i, "p": 1, "q": 1, "n": 1, "ts": i, "side": "buy", "ing": i}, False)

        assert [t["id"] for t in h.recent_trades(5, "SLOWUSDT")] == [1]

    def test_alert_filters(self):
        h = Hub()
        h.on_alert(alert("1", "BTCUSDT", "whale_trade", ts=1000))
        h.on_alert(alert("2", "ETHUSDT", "price_spike", ts=2000))

        assert [a["id"] for a in h.recent_alerts(symbol="ETHUSDT")] == ["2"]
        assert [a["id"] for a in h.recent_alerts(since=1500)] == ["2"]


class TestProtections:
    def test_rate_limiter_blocks_then_recovers(self):
        limiter = RateLimiter(3, window=10)

        assert [limiter.allow("a", now=t) for t in (0, 1, 2, 3)] == [True, True, True, False]
        assert limiter.allow("b", now=3)                 # another client is unaffected
        assert limiter.allow("a", now=11)                # the window has moved on

    def test_limit_zero_means_unlimited(self):
        assert all(RateLimiter(0).allow("a") for _ in range(1000))

    def test_connection_limiter(self):
        limiter = ConnectionLimiter(2)

        assert [limiter.acquire("a") for _ in range(3)] == [True, True, False]
        limiter.release("a")
        assert limiter.acquire("a")

    @pytest.fixture
    def client(self, monkeypatch):
        hub = Hub()
        now = int(time.time() * 1000) // MINUTE * MINUTE
        for i in range(30):
            hub.on_agg(window("BTCUSDT", now - i * MINUTE))
        monkeypatch.setattr(main, "hub", hub)
        monkeypatch.setattr(main, "wait_for_broker", lambda *_: False)
        monkeypatch.setattr(hub, "start", lambda: None)
        with TestClient(main.app) as c:
            yield c

    def test_api_returns_429_when_a_client_is_too_fast(self, client, monkeypatch):
        monkeypatch.setattr(main, "rate_limiter", RateLimiter(3))

        codes = [client.get("/api/health").status_code for _ in range(5)]

        assert codes == [200, 200, 200, 429, 429]

    def test_safe_headers_are_set(self, client):
        headers = client.get("/api/health").headers

        assert headers["x-content-type-options"] == "nosniff" and headers["referrer-policy"] == "no-referrer"

    def test_new_endpoints(self, client):
        assert client.get("/api/coin/BTCUSDT").json()["price"] == 100.0
        assert client.get("/api/coin/NOPEUSDT").status_code == 404
        body = client.get("/api/series/BTCUSDT?minutes=1440").json()
        assert body["bucket_min"] == 15 and body["candles"]
        assert client.get("/api/series/BTCUSDT?minutes=1441").status_code == 422
        assert client.get("/api/stats/alerts").json()["rows"] == []
        assert client.get("/api/alerts?symbol=ETHUSDT").json()["alerts"] == []

    def test_websocket_connection_cap(self, client, monkeypatch):
        monkeypatch.setattr(main, "ws_limiter", ConnectionLimiter(1))

        with client.websocket_connect("/ws") as first:
            assert first.receive_json()["type"] == "snapshot"
            with pytest.raises(Exception):
                with client.websocket_connect("/ws") as second:
                    second.receive_json()
