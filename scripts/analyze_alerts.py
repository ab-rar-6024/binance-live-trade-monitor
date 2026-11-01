#!/usr/bin/env python3
"""
Is the alerting too noisy or too quiet?

Replays every trade still stored in Kafka (`trades.raw`, 72 hours of retention) through the same detector code
Spark uses, once per threshold setting, and counts the alerts each setting would have produced. Nothing is sent
anywhere and Spark is not involved, so it is safe to run while the pipeline is live.

    python scripts/analyze_alerts.py                 # all stored trades
    python scripts/analyze_alerts.py --hours 6       # only the most recent 6 hours
    python scripts/analyze_alerts.py --top 8         # show 8 busiest coins per kind

How to read it: the number to look at is "alerts per hour" for the whole market and for the single noisiest coin.
As a rule of thumb a person reading a dashboard wants a handful of alerts an hour, not hundreds, and no one coin
dominating the list.
"""

import argparse
import dataclasses
import json
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from confluent_kafka import Consumer, TopicPartition  # noqa: E402

from backend.common.config import Thresholds, settings  # noqa: E402
from backend.streaming.detectors import CoinState, process_trades  # noqa: E402

BASE = Thresholds()
SWEEPS = [
    ("whale_min_usd", [10_000, 25_000, 50_000, 100_000]),
    ("whale_z", [3.0, 4.0, 5.0]),
    ("spike_pct", [0.10, 0.15, 0.25, 0.40]),
    ("surge_ratio", [2.0, 3.0, 5.0]),
]
KIND_OF = {"whale_min_usd": "whale_trade", "whale_z": "whale_trade", "spike_pct": "price_spike", "surge_ratio": "volume_surge"}


def load_trades(since_ms: int) -> Dict[str, List[dict]]:
    """Reads trades.raw from the start (or `since_ms`) up to the end offsets at the moment the script starts."""
    topic = settings.topics.raw
    consumer = Consumer({"bootstrap.servers": settings.bootstrap, "group.id": f"analyze-{int(time.time())}",
                         "enable.auto.commit": False, "auto.offset.reset": "earliest"})
    meta = consumer.list_topics(topic, timeout=10).topics[topic]
    parts = [TopicPartition(topic, p, since_ms) for p in meta.partitions]
    starts = {tp.partition: tp.offset for tp in consumer.offsets_for_times(parts, timeout=20)}
    ends = {p: consumer.get_watermark_offsets(TopicPartition(topic, p), timeout=10)[1] for p in meta.partitions}
    assign = []
    for p in meta.partitions:
        low = starts[p] if starts[p] >= 0 else ends[p]
        assign.append(TopicPartition(topic, p, low))
    consumer.assign(assign)
    remaining = {p for p in meta.partitions if assign[p].offset < ends[p]}
    by_symbol: Dict[str, List[dict]] = defaultdict(list)
    while remaining:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        if msg.offset() + 1 >= ends[msg.partition()]:
            remaining.discard(msg.partition())
        rec = json.loads(msg.value())
        by_symbol[rec["s"]].append(rec)
    consumer.close()
    for trades in by_symbol.values():
        trades.sort(key=lambda t: t["ts"])
    return by_symbol


def replay(by_symbol: Dict[str, List[dict]], th: Thresholds) -> Dict[str, Dict[str, int]]:
    """alerts[kind][symbol] -> count, using the same per-coin state machine as Spark."""
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for symbol, trades in by_symbol.items():
        _, alerts = process_trades(CoinState(), symbol, trades, th)
        for a in alerts:
            counts[a["type"]][symbol] += 1
    return counts


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hours", type=float, default=None, help="only look at the most recent N hours")
    ap.add_argument("--top", type=int, default=5, help="how many noisy coins to list")
    args = ap.parse_args()

    since = int((time.time() - args.hours * 3600) * 1000) if args.hours else 0
    print("Reading stored trades from Kafka ...")
    by_symbol = load_trades(since)
    total = sum(len(v) for v in by_symbol.values())
    if not total:
        sys.exit("No trades found. Start the producer first.")
    first = min(t[0]["ts"] for t in by_symbol.values())
    last = max(t[-1]["ts"] for t in by_symbol.values())
    hours = max((last - first) / 3_600_000, 1 / 60)
    print(f"{total:,} trades, {len(by_symbol)} coins, {hours:.1f} hours "
          f"({total / hours / 3600:.1f} trades/s on average)\n")

    # how big are trades, per coin: context for the whale settings
    print("Typical trade sizes (USD)        median      99.9th pct     largest")
    for symbol in sorted(by_symbol, key=lambda s: -len(by_symbol[s]))[:args.top]:
        sizes = sorted(t["n"] for t in by_symbol[symbol])
        p999 = sizes[min(len(sizes) - 1, int(len(sizes) * 0.999))]
        print(f"  {symbol:<12} {len(sizes):>9,} trades {statistics.median(sizes):>10,.0f} {p999:>14,.0f} {sizes[-1]:>12,.0f}")
    print()

    base_counts = replay(by_symbol, BASE)
    print(f"Current settings: whale >= ${BASE.whale_min_usd:,.0f} and z>{BASE.whale_z}, spike >= {BASE.spike_pct}% in 10 s, "
          f"surge >= {BASE.surge_ratio}x")
    for kind in ("whale_trade", "price_spike", "volume_surge"):
        per_coin = base_counts.get(kind, {})
        n = sum(per_coin.values())
        top = sorted(per_coin.items(), key=lambda kv: -kv[1])[:args.top]
        noisiest = f", noisiest {top[0][0]} {top[0][1] / hours:.1f}/h" if top else ""
        print(f"  {kind:<13} {n:>5} alerts = {n / hours:6.1f}/hour{noisiest}")
        for symbol, c in top:
            print(f"      {symbol:<12} {c:>4}  ({c / hours:.1f}/h)")
    print()

    print("What would change if a setting moved (all other settings unchanged):")
    print(f"  {'setting':<16}{'value':>9}   {'alerts':>7} {'per hour':>9}   {'noisiest coin':<20}")
    for name, values in SWEEPS:
        kind = KIND_OF[name]
        for value in values:
            th = dataclasses.replace(BASE, **{name: value})
            per_coin = replay(by_symbol, th).get(kind, {})
            n = sum(per_coin.values())
            top = max(per_coin.items(), key=lambda kv: kv[1]) if per_coin else None
            mark = "  <- current" if getattr(BASE, name) == value else ""
            noisiest = f"{top[0]} ({top[1] / hours:.1f}/h)" if top else "-"
            print(f"  {name:<16}{value:>9}   {n:>7} {n / hours:>9.1f}   {noisiest:<20}{mark}")
        print()
    print("Note: only the trades stored in Kafka are replayed, so quiet periods and the first minutes after a start")
    print("(when detectors are still learning each coin's normal) are part of the result.")


if __name__ == "__main__":
    main()
