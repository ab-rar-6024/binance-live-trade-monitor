"""Create the SparkSession used by the streaming job (Windows-safe, Kafka-enabled)."""

import os
import sys
from pathlib import Path
from typing import Optional

from pyspark.sql import SparkSession

from .kafka_jars import ensure_kafka_jars
from .winsafe import build_shim, spark_windows_conf

DEFAULT_JAVA_HOMES = [
    r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot",
]


def _prepare_environment() -> None:
    """Java, hostname and Python settings that Spark reads from the environment."""
    if not os.environ.get("JAVA_HOME"):
        for candidate in DEFAULT_JAVA_HOMES:
            if Path(candidate).exists():
                os.environ["JAVA_HOME"] = candidate
                break
    if os.environ.get("JAVA_HOME"):
        os.environ["PATH"] = str(Path(os.environ["JAVA_HOME"]) / "bin") + os.pathsep + os.environ["PATH"]
    # Spark builds URLs from the hostname; a name containing "_" is rejected, so bind to localhost
    os.environ.setdefault("SPARK_LOCAL_HOSTNAME", "localhost")
    os.environ.setdefault("SPARK_LOCAL_IP", "127.0.0.1")
    # Python workers import backend.* (pickled functions refer to it), so they need the project root
    root = str(Path(__file__).resolve().parents[2])
    os.environ["PYTHONPATH"] = root + os.pathsep + os.environ.get("PYTHONPATH", "")
    os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
    os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)


def create_spark_session(app_name: str = "binance-stream", cores: Optional[int] = None,
                         shuffle_partitions: Optional[int] = None, extra: Optional[dict] = None) -> SparkSession:
    # Streaming micro-batches are tiny, so per-batch overhead (tasks, Python workers, state commits)
    # dominates: a few cores and few shuffle partitions keep batches short.
    cores = cores or int(os.environ.get("SPARK_CORES", "6"))
    shuffle_partitions = shuffle_partitions or int(os.environ.get("SPARK_SHUFFLE_PARTITIONS", "2"))
    _prepare_environment()
    classpath = [str(p) for p in ensure_kafka_jars()]
    if sys.platform == "win32":
        classpath.insert(0, str(build_shim()))

    builder = (
        SparkSession.builder.master(f"local[{cores}]")
        .appName(app_name)
        .config("spark.driver.extraClassPath", os.pathsep.join(classpath))
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", str(shuffle_partitions))
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.sql.execution.arrow.pyspark.enabled", "true")
        # the stateful (applyInPandasWithState) operators keep their state here
        .config("spark.sql.streaming.stateStore.providerClass",
                "org.apache.spark.sql.execution.streaming.state.HDFSBackedStateStoreProvider")
    )
    for key, value in {**spark_windows_conf(), **(extra or {})}.items():
        builder = builder.config(key, value)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark
