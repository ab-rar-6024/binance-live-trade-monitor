"""Tests for the live market picture (Hub) and the HTTP API, with no Kafka involved."""

import json
import time

import pytest
from fastapi.testclient import TestClient

import backend.app.main as main
from backend.app.hub import MINUTE, Hub, percentile


def window(symbol, ws, close=100.0, notional=1000.0, buy=600.0, trades=10):
    return {"ws": ws, "we": ws + MINUTE, "s": symbol, "trades": trades, "volume": notional / close, "notional": notional,
            "vwap": close, "open": close, "high": close, "low": close, "close": close, "buy_notional": buy,
            "sell_notional": notional - buy, "buy_trades": 6, "largest": 150.0, "last_ts": ws + 1000,
            "last_ing": ws + 1010}


def alert(kind="whale_trade", symbol="BTCUSDT", ts=None, ident=None):
    ts = ts or int(time.time() * 1000)
    return {"id": ident or f"{kind}:{symbol}:{ts}", "type": kind, "s": symbol, "ts": ts, "severity": "warning", "value": 1.0,
            "message": "test alert", "detail": json.dumps({"x": 1}), "ing": ts}


@pytest.fixture
def hub():
    h = Hub()
    now = int(time.time() * 1000) // MINUTE * MINUTE
    for i in range(6):  # six minutes of BTC (busy, buyers), three of ETH (quiet, sellers)
        h.on_agg(window("BTCUSDT", now - i * MINUTE, close=100 + i, notional=9000, buy=7000))
    for i in range(3):
        h.on_agg(window("ETHUSDT", now - i * MINUTE, close=50, notional=2000, buy=500))
    h.on_trade({"s": "BTCUSDT", "id": 1, "p": 106.5, "q": 1.0, "n": 106.5, "ts": now, "side": "buy", "ing": now}, live=True)
    return h


class TestHubViews:
    def test_overview_has_price_minute_stats_and_sparkline(self, hub):
        btc = next(c for c in hub.overview() if c["symbol"] == "BTCUSDT")

        assert btc["price"] == 106.5
        assert btc["minute"]["notional"] == 9000
        assert btc["minute"]["buy_ratio"] == pytest.approx(7000 / 9000, abs=1e-3)
        assert len(btc["spark"]) == 6

    def test_hot_ranking_is_by_traded_value_and_shares_sum_to_100(self, hub):
        ranking = hub.hot(5)

        assert [r["symbol"] for r in ranking] == ["BTCUSDT", "ETHUSDT"]
        assert [r["rank"] for r in ranking] == [1, 2]
        assert sum(r["share_pct"] for r in ranking) == pytest.approx(100, abs=0.2)

    def test_pressure_splits_buy_and_sell(self, hub):
        result = hub.pressure(5)
        by_coin = {c["symbol"]: c for c in result["coins"]}

        assert by_coin["BTCUSDT"]["buy_pct"] > 50 > by_coin["ETHUSDT"]["buy_pct"]
        assert result["buy"] + result["sell"] == pytest.approx(5 * 9000 + 3 * 2000)

    def test_series_returns_candles_oldest_first(self, hub):
        candles = hub.series("BTCUSDT", 10)

        assert len(candles) == 6
        assert [c["ws"] for c in candles] == sorted(c["ws"] for c in candles)

    def test_replayed_trades_do_not_count_toward_rate_or_latency(self):
        h = Hub()
        old = int(time.time() * 1000) - 60_000
        h.on_trade({"s": "BTCUSDT", "id": 1, "p": 1.0, "q": 1.0, "n": 1.0, "ts": old, "side": "buy", "ing": old}, live=False)

        assert len(h.feed) == 1                      # it fills the feed ...
        assert h.system()["counts"].get("trades", 0) == 0  # ... but is not "live traffic"
        assert h.system()["latency_ms"]["producer_to_api_p50"] is None

    def test_a_live_trade_measures_kafka_latency(self):
        h = Hub()
        now = int(time.time() * 1000)
        h.on_trade({"s": "BTCUSDT", "id": 1, "p": 1.0, "q": 1.0, "n": 1.0, "ts": now, "side": "buy", "ing": now - 40}, live=True)

        assert 30 <= h.system()["latency_ms"]["producer_to_api_p50"] < 5000


class TestAlerts:
    def test_duplicates_are_ignored_and_detail_is_decoded(self):
        h = Hub()
        h.on_alert(alert(ident="a1"))
        h.on_alert(alert(ident="a1"))

        assert len(h.recent_alerts()) == 1
        assert h.recent_alerts()[0]["detail"] == {"x": 1}

    def test_newest_first_and_type_filter(self):
        h = Hub()
        h.on_alert(alert("whale_trade", ts=1000))
        h.on_alert(alert("price_spike", ts=3000))
        h.on_alert(alert("price_spike", symbol="ETHUSDT", ts=2000))

        assert [a["ts"] for a in h.recent_alerts()] == [3000, 2000, 1000]
        assert [a["type"] for a in h.recent_alerts(kind="whale_trade")] == ["whale_trade"]


def test_percentile_helper():
    assert percentile([], 50) is None
    assert percentile([10, 20, 30, 40, 50], 50) == 30
    assert percentile([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], 95) == 10


@pytest.fixture
def client(hub, monkeypatch):
    monkeypatch.setattr(main, "hub", hub)
    monkeypatch.setattr(main, "wait_for_broker", lambda *_: False)  # no Kafka in tests
    monkeypatch.setattr(hub, "start", lambda: None)
    hub.on_alert(alert(ident="x1"))
    with TestClient(main.app) as c:
        yield c


class TestApi:
    def test_overview_hot_pressure_alerts(self, client):
        assert len(client.get("/api/overview").json()["coins"]) >= 2
        assert client.get("/api/hot?minutes=5").json()["coins"][0]["symbol"] == "BTCUSDT"
        assert client.get("/api/pressure").json()["buy_pct"] is not None
        assert client.get("/api/alerts").json()["alerts"][0]["id"] == "x1"

    def test_series_and_unknown_symbol(self, client):
        assert len(client.get("/api/series/btcusdt?minutes=10").json()["candles"]) == 6
        assert client.get("/api/series/NOPEUSDT").status_code == 404

    def test_query_validation(self, client):
        assert client.get("/api/hot?minutes=0").status_code == 422
        assert client.get("/api/alerts?limit=9999").status_code == 422

    def test_health_reports_degraded_without_kafka(self, client):
        body = client.get("/api/health").json()

        assert body["status"] == "degraded" and body["kafka"] is False

    def test_config_lists_symbols_and_thresholds(self, client):
        body = client.get("/api/config").json()

        assert "BTCUSDT" in body["symbols"] and "whale_min_usd" in body["thresholds"]

    def test_websocket_sends_snapshot_then_ticks(self, client):
        with client.websocket_connect("/ws") as ws:
            snapshot = ws.receive_json()
            tick = ws.receive_json()

        assert snapshot["type"] == "snapshot" and len(snapshot["alerts"]) == 1
        assert tick["type"] == "tick" and tick["overview"] and tick["system"]["kafka"]["connected"] in (True, False)
