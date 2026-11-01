"""
Spark Structured Streaming job: Kafka `trades.raw` -> analytics -> Kafka.

Two queries run side by side:

  aggregates  one-minute windows per coin (trade count, volume, VWAP, open/high/low/close,
              buyer vs seller pressure, largest trade)            -> topic trades.agg1m
  detectors   stateful per-coin anomaly detection (whale trades,
              price spikes, volume surges)                         -> topic trades.alerts

and the driver publishes Spark's own batch statistics to topic spark.progress.

    python -m backend.streaming.jobs               # start from the newest trades
    python -m backend.streaming.jobs --from earliest --reset   # reprocess everything in Kafka
"""

import argparse
import json
import logging
import shutil
import time
from typing import Iterator, Tuple

import pandas as pd
from confluent_kafka import Producer
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql import types as T
from pyspark.sql.streaming.state import GroupState, GroupStateTimeout

from backend.common.config import settings
from backend.streaming.detectors import STATE_SCHEMA, CoinState, process_trades
from backend.streaming.spark_session import create_spark_session

log = logging.getLogger("spark-job")

TRADE_SCHEMA = T.StructType([
    T.StructField("s", T.StringType()), T.StructField("id", T.LongType()), T.StructField("p", T.DoubleType()),
    T.StructField("q", T.DoubleType()), T.StructField("n", T.DoubleType()), T.StructField("ts", T.LongType()),
    T.StructField("side", T.StringType()), T.StructField("ing", T.LongType()),
])
ALERT_SCHEMA = "id string, type string, s string, ts long, severity string, value double, message string, detail string, ing long"
ALERT_COLUMNS = ["id", "type", "s", "ts", "severity", "value", "message", "detail", "ing"]  # keep in sync with ALERT_SCHEMA
THRESHOLDS = settings.thresholds


def read_trades(spark: SparkSession, starting: str) -> DataFrame:
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", settings.bootstrap)
        .option("subscribe", settings.topics.raw)
        .option("startingOffsets", starting)
        .option("maxOffsetsPerTrigger", 50_000)
        .option("failOnDataLoss", "false")
        .load()
    )
    return (
        raw.select(F.from_json(F.col("value").cast("string"), TRADE_SCHEMA).alias("t")).select("t.*")
        .where(F.col("s").isNotNull() & F.col("ts").isNotNull())
        .withColumn("event_time", (F.col("ts") / 1000).cast("timestamp"))
    )


def build_aggregates(trades: DataFrame) -> DataFrame:
    """One-minute window per coin. Update mode re-emits a window whenever it changes."""
    buy = F.col("side") == "buy"
    agg = (
        trades.withWatermark("event_time", "15 seconds")
        .groupBy(F.window("event_time", "1 minute").alias("w"), "s")
        .agg(
            F.count("*").alias("trades"), F.sum("q").alias("volume"), F.sum("n").alias("notional"),
            F.min("p").alias("low"), F.max("p").alias("high"),
            F.min_by("p", "ts").alias("open"), F.max_by("p", "ts").alias("close"),
            F.sum(F.when(buy, F.col("n")).otherwise(0.0)).alias("buy_notional"),
            F.sum(F.when(~buy, F.col("n")).otherwise(0.0)).alias("sell_notional"),
            F.sum(F.when(buy, 1).otherwise(0)).alias("buy_trades"),
            F.max("n").alias("largest"), F.max("ts").alias("last_ts"), F.max("ing").alias("last_ing"),
        )
    )
    return agg.select(
        F.col("s").alias("key"),
        F.to_json(F.struct(
            (F.col("w.start").cast("long") * 1000).alias("ws"), (F.col("w.end").cast("long") * 1000).alias("we"),
            F.col("s"), "trades", "volume", "notional", (F.col("notional") / F.col("volume")).alias("vwap"),
            "open", "high", "low", "close", "buy_notional", "sell_notional", "buy_trades", "largest", "last_ts",
            "last_ing",
        )).alias("value"),
    )


def detect(key: Tuple, frames: Iterator[pd.DataFrame], state: GroupState) -> Iterator[pd.DataFrame]:
    """Stateful per-coin detection (runs in a Python worker once per coin per micro-batch)."""
    symbol = key[0]
    coin_state = CoinState.from_tuple(state.get) if state.exists else CoinState()
    batches = [f for f in frames if len(f)]
    if not batches:
        return
    rows = pd.concat(batches).to_dict("records")
    coin_state, alerts = process_trades(coin_state, symbol, rows, THRESHOLDS)
    state.update(coin_state.to_tuple())
    if alerts:
        yield pd.DataFrame(alerts, columns=ALERT_COLUMNS)


def build_detectors(trades: DataFrame) -> DataFrame:
    alerts = trades.select("s", "id", "p", "q", "n", "ts", "side", "ing").groupBy("s").applyInPandasWithState(
        detect, ALERT_SCHEMA, STATE_SCHEMA, "append", GroupStateTimeout.NoTimeout)
    return alerts.select(F.col("s").alias("key"), F.to_json(F.struct(*ALERT_COLUMNS)).alias("value"))


def to_kafka(df: DataFrame, topic: str, name: str, mode: str, trigger: str):
    return (
        df.writeStream.queryName(name).format("kafka")
        .option("kafka.bootstrap.servers", settings.bootstrap).option("topic", topic)
        .option("checkpointLocation", str(settings.checkpoint_dir / name))
        .outputMode(mode).trigger(processingTime=trigger).start()
    )


def publish_progress(producer: Producer, queries) -> None:
    """Forward Spark's per-query batch statistics to Kafka so the API/UI can show them."""
    for q in queries:
        p = q.lastProgress
        if not p:
            continue
        producer.produce(settings.topics.progress, key=q.name, value=json.dumps({
            "ts": int(time.time() * 1000), "query": q.name, "batch": p.get("batchId"), "rows": p.get("numInputRows"),
            "in_rps": p.get("inputRowsPerSecond"), "proc_rps": p.get("processedRowsPerSecond"),
            "duration_ms": (p.get("durationMs") or {}).get("triggerExecution"),
        }, separators=(",", ":")))
    producer.poll(0)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--from", dest="starting", choices=["latest", "earliest"], default="latest")
    parser.add_argument("--reset", action="store_true", help="delete checkpoints (forget Spark's progress and state)")
    args = parser.parse_args()

    if args.reset and settings.checkpoint_dir.exists():
        shutil.rmtree(settings.checkpoint_dir)
        log.info("checkpoints deleted")
    settings.checkpoint_dir.mkdir(parents=True, exist_ok=True)

    spark = create_spark_session("binance-stream")
    trades = read_trades(spark, args.starting)
    queries = [
        to_kafka(build_aggregates(trades), settings.topics.agg, "aggregates", "update", "1 second"),
        to_kafka(build_detectors(trades), settings.topics.alerts, "detectors", "append", "5 seconds"),
    ]
    log.info("streaming queries started: %s", [q.name for q in queries])
    progress = Producer({"bootstrap.servers": settings.bootstrap, "client.id": "spark-progress"})
    try:
        while True:
            time.sleep(2)
            for q in queries:
                if q.exception() is not None:
                    raise RuntimeError(f"query {q.name} failed: {q.exception()}")
            publish_progress(progress, queries)
    except KeyboardInterrupt:
        pass
    finally:
        for q in queries:
            q.stop()
        progress.flush(5)
        spark.stop()


if __name__ == "__main__":
    main()
