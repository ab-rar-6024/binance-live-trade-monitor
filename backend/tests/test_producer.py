"""Tests for the Binance message normalisation."""

from backend.producer.binance_producer import normalize, stream_url

BINANCE_TRADE = {
    "stream": "btcusdt@trade",
    "data": {"e": "trade", "E": 1793460395540, "s": "BTCUSDT", "t": 6808962706, "p": "77475.83000000",
             "q": "0.00328000", "T": 1793460395540, "m": False, "M": True},
}


def test_trade_is_normalised():
    rec = normalize(BINANCE_TRADE, ingest_ms=1793460395600)

    assert rec == {"s": "BTCUSDT", "id": 6808962706, "p": 77475.83, "q": 0.00328, "n": 254.1207, "ts": 1793460395540,
                   "side": "buy", "ing": 1793460395600}


def test_buyer_is_maker_means_the_taker_sold():
    message = {"data": {**BINANCE_TRADE["data"], "m": True}}

    assert normalize(message)["side"] == "sell"


def test_notional_is_price_times_quantity():
    rec = normalize(BINANCE_TRADE)

    assert abs(rec["n"] - rec["p"] * rec["q"]) < 1e-3


def test_non_trade_messages_are_ignored():
    assert normalize({"result": None, "id": 1}) is None
    assert normalize({"data": {"e": "kline"}}) is None


def test_unwrapped_message_is_accepted():
    assert normalize(BINANCE_TRADE["data"])["s"] == "BTCUSDT"


def test_stream_url_lists_every_symbol_lowercase():
    url = stream_url(["BTCUSDT", "ETHUSDT"], "wss://example.test")

    assert url == "wss://example.test/stream?streams=btcusdt@trade/ethusdt@trade"
