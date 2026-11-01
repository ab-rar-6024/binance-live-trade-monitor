"""
Spark's Kafka connector jars, fetched once from Maven Central and put on the driver classpath.

Why not `spark.jars.packages`? Spark copies resolved packages with a chmod that needs
winutils.exe on Windows (see winsafe.py). Jars on the driver classpath skip that step.

The four artifacts match PySpark 3.4.4 (Scala 2.12). Each download is verified against the
SHA-1 that Maven Central publishes next to it.
"""

import hashlib
import urllib.request
from pathlib import Path
from typing import List

JARS_DIR = Path(__file__).resolve().parent / "jars"
MAVEN = "https://repo1.maven.org/maven2"
SPARK = "3.4.4"
ARTIFACTS = [
    f"org/apache/spark/spark-sql-kafka-0-10_2.12/{SPARK}/spark-sql-kafka-0-10_2.12-{SPARK}.jar",
    f"org/apache/spark/spark-token-provider-kafka-0-10_2.12/{SPARK}/spark-token-provider-kafka-0-10_2.12-{SPARK}.jar",
    "org/apache/kafka/kafka-clients/3.3.2/kafka-clients-3.3.2.jar",
    "org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar",
]


def _fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as resp:  # nosec - fixed https URLs on Maven Central
        return resp.read()


def ensure_kafka_jars() -> List[Path]:
    """Download any missing connector jar (verifying SHA-1) and return their paths."""
    JARS_DIR.mkdir(exist_ok=True)
    paths = []
    for artifact in ARTIFACTS:
        target = JARS_DIR / artifact.rsplit("/", 1)[1]
        if not target.exists():
            data = _fetch(f"{MAVEN}/{artifact}")
            expected = _fetch(f"{MAVEN}/{artifact}.sha1").decode().split()[0].strip()
            actual = hashlib.sha1(data).hexdigest()  # nosec - integrity check against Maven's published value
            if actual != expected:
                raise RuntimeError(f"Checksum mismatch for {artifact}: {actual} != {expected}")
            target.write_bytes(data)
        paths.append(target)
    return paths


if __name__ == "__main__":
    for p in ensure_kafka_jars():
        print(p.name, p.stat().st_size)
