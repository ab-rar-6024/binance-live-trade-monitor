"""
Binance trades -> Kafka.

Opens one websocket to Binance's public market-data stream (no API key needed), turns each
trade into a compact JSON message and writes it to the `trades.raw` topic, keyed by symbol so
that all trades of one coin stay in order inside one partition.

    python -m backend.producer.binance_producer
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, Optional

import websockets
from confluent_kafka import Producer

from backend.common.config import settings

log = logging.getLogger("producer")


def stream_url(symbols, host: str) -> str:
    streams = "/".join(f"{s.lower()}@trade" for s in symbols)
    return f"{host}/stream?streams={streams}"


def normalize(message: Dict[str, Any], ingest_ms: Optional[int] = None) -> Optional[Dict[str, Any]]:
    """Binance combined-stream message -> our trade record (None if it is not a trade).

    Binance trade fields: s symbol, t trade id, p price, q quantity, T trade time (ms),
    E event time (ms), m "buyer is the market maker". When m is true the buyer was resting in
    the order book and the *seller* crossed the spread, so the aggressive (taker) side is a sell.
    """
    data = message.get("data", message)
    if data.get("e") != "trade":
        return None
    price, qty = float(data["p"]), float(data["q"])
    return {
        "s": data["s"],
        "id": int(data["t"]),
        "p": price,
        "q": qty,
        "n": round(price * qty, 4),  # notional value in the quote currency (USDT ~ USD)
        "ts": int(data["T"]),
        "side": "sell" if data["m"] else "buy",
        "ing": ingest_ms if ingest_ms is not None else int(time.time() * 1000),
    }


class TradeProducer:
    def __init__(self) -> None:
        self.producer = Producer({
            "bootstrap.servers": settings.bootstrap,
            "linger.ms": 50,
            "compression.type": "lz4",
            "acks": "1",
            "client.id": "binance-producer",
        })
        self.sent = 0
        self.failed = 0

    def _delivered(self, err, _msg) -> None:
        if err is not None:
            self.failed += 1
            log.warning("delivery failed: %s", err)

    def send(self, trade: Dict[str, Any]) -> None:
        self.producer.produce(
            settings.topics.raw,
            key=trade["s"],
            value=json.dumps(trade, separators=(",", ":")),
            on_delivery=self._delivered,
        )
        self.sent += 1
        self.producer.poll(0)

    def close(self) -> None:
        self.producer.flush(10)


async def run(symbols=None) -> None:
    symbols = symbols or settings.symbols
    url = stream_url(symbols, settings.binance_ws)
    producer = TradeProducer()
    last_report, last_count, backoff = time.time(), 0, 1.0
    log.info("streaming %d symbols from %s", len(symbols), settings.binance_ws)
    try:
        while True:
            try:
                async with websockets.connect(url, max_size=2**20, open_timeout=15) as ws:
                    log.info("connected to Binance")
                    backoff = 1.0
                    async for raw in ws:
                        trade = normalize(json.loads(raw))
                        if trade:
                            producer.send(trade)
                        now = time.time()
                        if now - last_report >= 10:
                            log.info("%.1f trades/s (total %d, failed %d)", (producer.sent - last_count) / (now - last_report),
                                     producer.sent, producer.failed)
                            last_report, last_count = now, producer.sent
            except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as exc:
                # Binance closes long-lived connections (about every 24 h): reconnect with backoff
                log.warning("connection lost (%s); reconnecting in %.0fs", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30.0)
    finally:
        producer.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
