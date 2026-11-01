"""Settings shared by the producer, the Spark job and the API (override with environment variables)."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

ROOT = Path(__file__).resolve().parents[2]


def _list(name: str, default: str) -> List[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


@dataclass(frozen=True)
class Topics:
    raw: str = "trades.raw"          # every trade, as received from Binance
    agg: str = "trades.agg1m"        # per-coin one-minute windows (Spark)
    alerts: str = "trades.alerts"    # whale trades, price spikes, volume surges (Spark)
    progress: str = "spark.progress"  # Spark's own batch statistics (Spark)

    def all(self) -> List[str]:
        return [self.raw, self.agg, self.alerts, self.progress]


@dataclass(frozen=True)
class Thresholds:
    """Detection settings used by the Spark job. Tune with environment variables."""

    # whale trade: notional far above this coin's recent trades AND big in absolute terms
    whale_z: float = float(os.environ.get("WHALE_Z", "4.0"))
    whale_ratio: float = float(os.environ.get("WHALE_RATIO", "10.0"))
    whale_min_usd: float = float(os.environ.get("WHALE_MIN_USD", "50000"))
    whale_min_history: int = int(os.environ.get("WHALE_MIN_HISTORY", "30"))
    # price spike: move inside a 10-second window
    spike_pct: float = float(os.environ.get("SPIKE_PCT", "0.25"))
    # volume surge: this minute vs the median of the previous minutes
    surge_ratio: float = float(os.environ.get("SURGE_RATIO", "5.0"))
    surge_history: int = int(os.environ.get("SURGE_HISTORY", "30"))
    surge_min_history: int = int(os.environ.get("SURGE_MIN_HISTORY", "5"))
    surge_min_usd: float = float(os.environ.get("SURGE_MIN_USD", "50000"))


@dataclass(frozen=True)
class Settings:
    bootstrap: str = os.environ.get("KAFKA_BOOTSTRAP", "127.0.0.1:9092")
    binance_ws: str = os.environ.get("BINANCE_WS", "wss://data-stream.binance.vision")
    symbols: List[str] = field(default_factory=lambda: _list(
        "SYMBOLS", ",".join(f"{c}USDT" for c in (
            "BTC ETH BNB SOL XRP DOGE ADA AVAX LINK TRX DOT LTC BCH ATOM NEAR UNI APT ARB OP FIL "
            "INJ SUI SHIB PEPE ETC XLM HBAR AAVE ICP CRV").split())))
    partitions: int = int(os.environ.get("TOPIC_PARTITIONS", "3"))
    topics: Topics = field(default_factory=Topics)
    thresholds: Thresholds = field(default_factory=Thresholds)
    # API server (see "Putting it online" in the README)
    api_host: str = os.environ.get("API_HOST", "127.0.0.1")
    api_port: int = int(os.environ.get("API_PORT", "8100"))
    api_cors_origins: List[str] = field(default_factory=lambda: _list(
        "API_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173"))
    api_rate_limit_per_min: int = int(os.environ.get("API_RATE_LIMIT", "600"))   # per client IP, REST only; 0 = off
    api_max_ws_per_ip: int = int(os.environ.get("API_MAX_WS_PER_IP", "10"))
    api_docs: bool = os.environ.get("API_DOCS", "1") != "0"
    db_path: Path = Path(os.environ.get("DB_PATH", str(ROOT / "data" / "market.db")))
    checkpoint_dir: Path = ROOT / "data" / "checkpoints"
    kafka_home: Path = ROOT / "kafka"
    kafka_data: Path = ROOT / "data" / "kafka-logs"


settings = Settings()
