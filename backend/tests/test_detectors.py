"""Unit tests for the per-coin detectors (pure Python, no Spark or Kafka needed)."""

import random

from backend.common.config import Thresholds
from backend.streaming.detectors import CoinState, process_trades

TH = Thresholds(whale_z=4.0, whale_ratio=10.0, whale_min_usd=25_000, whale_min_history=30, spike_pct=0.15,
                surge_ratio=3.0, surge_history=30, surge_min_history=5, surge_min_usd=50_000)
T0 = 1_700_000_000_000  # an arbitrary start time (ms)


def trade(i, ts, price=100.0, qty=1.0, side="buy", value=None):
    n = value if value is not None else price * qty
    return {"s": "TESTUSDT", "id": i, "p": price, "q": n / price, "n": n, "ts": ts, "side": side, "ing": ts + 5}


def calm_history(count=60, seed=1):
    """Small, ordinary trades (about $50-$300) a second apart at a steady price."""
    rng = random.Random(seed)
    return [trade(i, T0 + i * 1000, value=rng.uniform(50, 300)) for i in range(count)]


def types(alerts):
    return [a["type"] for a in alerts]


class TestWhaleTrades:
    def test_huge_trade_after_calm_history_is_flagged(self):
        state, _ = process_trades(CoinState(), "TESTUSDT", calm_history(), TH)

        _, alerts = process_trades(state, "TESTUSDT", [trade(999, T0 + 61_000, value=400_000)], TH)

        assert types(alerts) == ["whale_trade"]
        assert alerts[0]["severity"] == "critical"  # $400K is over the $250K critical line
        assert "TEST" in alerts[0]["message"]

    def test_large_but_below_the_dollar_floor_is_not_flagged(self):
        state, _ = process_trades(CoinState(), "TESTUSDT", calm_history(), TH)

        _, alerts = process_trades(state, "TESTUSDT", [trade(999, T0 + 61_000, value=20_000)], TH)

        assert alerts == []

    def test_needs_history_before_judging(self):
        _, alerts = process_trades(CoinState(), "TESTUSDT", [trade(1, T0, value=500_000)], TH)

        assert alerts == []

    def test_ordinary_flow_raises_no_alerts(self):
        _, alerts = process_trades(CoinState(), "TESTUSDT", calm_history(200), TH)

        assert alerts == []


class TestPriceSpikes:
    def _run(self, prices):
        trades = [trade(i, T0 + i * 1000, price=p, value=100.0) for i, p in enumerate(prices)]
        return process_trades(CoinState(), "TESTUSDT", trades, TH)

    def test_fast_move_is_flagged_with_direction(self):
        _, up = self._run([100.0] * 6 + [100.4])
        _, down = self._run([100.0] * 6 + [99.6])

        assert types(up) == ["price_spike"] and up[0]["value"] > 0
        assert types(down) == ["price_spike"] and down[0]["value"] < 0

    def test_small_move_is_ignored(self):
        _, alerts = self._run([100.0] * 6 + [100.05])

        assert alerts == []

    def test_slow_drift_is_ignored(self):
        # +0.2% in total, but spread over two minutes: no 10-second window sees it
        _, alerts = self._run([100.0 + i * 0.002 for i in range(100)])

        assert alerts == []

    def test_cooldown_suppresses_repeat_alerts(self):
        _, alerts = self._run([100.0] * 6 + [100.4, 100.5, 100.6, 100.7])

        assert types(alerts) == ["price_spike"]


class TestVolumeSurges:
    def _minutes(self, values):
        """One trade per minute with the given USD values."""
        return [trade(i, T0 + i * 60_000 + 500, value=v) for i, v in enumerate(values)]

    def test_surge_after_normal_minutes(self):
        trades = self._minutes([10_000] * 8 + [200_000])

        _, alerts = process_trades(CoinState(), "TESTUSDT", trades, TH)

        assert "volume_surge" in types(alerts)
        surge = next(a for a in alerts if a["type"] == "volume_surge")
        assert surge["value"] > 3

    def test_needs_a_few_minutes_of_history(self):
        _, alerts = process_trades(CoinState(), "TESTUSDT", self._minutes([10_000, 200_000]), TH)

        assert "volume_surge" not in types(alerts)

    def test_only_one_alert_per_minute(self):
        base = self._minutes([10_000] * 8)
        burst = [trade(100 + i, T0 + 8 * 60_000 + i * 1000, value=100_000) for i in range(5)]

        _, alerts = process_trades(CoinState(), "TESTUSDT", base + burst, TH)

        assert types(alerts).count("volume_surge") == 1

    def test_quiet_market_below_the_dollar_floor_is_ignored(self):
        _, alerts = process_trades(CoinState(), "TESTUSDT", self._minutes([10] * 8 + [400]), TH)

        assert "volume_surge" not in types(alerts)


class TestState:
    def test_state_survives_a_round_trip(self):
        state, _ = process_trades(CoinState(), "TESTUSDT", calm_history(80), TH)

        restored = CoinState.from_tuple(state.to_tuple())

        assert restored.n == state.n and restored.prices == state.prices and restored.minutes == state.minutes

    def test_splitting_a_stream_across_batches_gives_the_same_alerts(self):
        trades = calm_history(60) + [trade(999, T0 + 61_000, value=400_000)]
        _, whole = process_trades(CoinState(), "TESTUSDT", trades, TH)

        state = CoinState()
        collected = []
        for chunk in (trades[:25], trades[25:50], trades[50:]):
            state, alerts = process_trades(CoinState.from_tuple(state.to_tuple()), "TESTUSDT", chunk, TH)
            collected += alerts

        assert [a["id"] for a in collected] == [a["id"] for a in whole]

    def test_out_of_order_trades_within_a_batch_are_sorted(self):
        trades = calm_history(60)
        random.Random(7).shuffle(trades)

        _, alerts = process_trades(CoinState(), "TESTUSDT", trades, TH)

        assert alerts == []
