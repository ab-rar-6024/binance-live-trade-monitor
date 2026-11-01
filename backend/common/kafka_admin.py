"""Topic creation and broker health, using confluent-kafka's AdminClient."""

import time
from typing import Dict, Optional

from confluent_kafka import Consumer, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic

from .config import settings


def admin() -> AdminClient:
    return AdminClient({"bootstrap.servers": settings.bootstrap, "socket.timeout.ms": 5000})


def wait_for_broker(timeout: float = 60.0) -> bool:
    """Block until the broker answers a metadata request (True) or the timeout passes (False)."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if admin().list_topics(timeout=3).brokers:
                return True
        except Exception:
            pass
        time.sleep(1.0)
    return False


def ensure_topics() -> Dict[str, str]:
    """Create the project's topics if missing; returns {topic: 'created' | 'exists'}."""
    client = admin()
    existing = set(client.list_topics(timeout=10).topics)
    wanted = [t for t in settings.topics.all() if t not in existing]
    result = {t: "exists" for t in settings.topics.all() if t in existing}
    if wanted:
        futures = client.create_topics(
            [NewTopic(t, num_partitions=settings.partitions, replication_factor=1) for t in wanted]
        )
        for topic, future in futures.items():
            future.result()  # raises if creation failed
            result[topic] = "created"
    return result


def topic_offsets(topic: str, group: str = "binance-admin") -> Optional[Dict[str, int]]:
    """Total messages ever written to `topic` (sum of partition high watermarks minus low watermarks)."""
    consumer = Consumer({"bootstrap.servers": settings.bootstrap, "group.id": group, "enable.auto.commit": False})
    try:
        meta = consumer.list_topics(topic, timeout=5).topics.get(topic)
        if meta is None or meta.error is not None:
            return None
        low = high = 0
        for partition in meta.partitions:
            lo, hi = consumer.get_watermark_offsets(TopicPartition(topic, partition), timeout=5)
            low, high = low + lo, high + hi
        return {"partitions": len(meta.partitions), "messages": high - low, "end_offset": high}
    finally:
        consumer.close()


if __name__ == "__main__":
    if not wait_for_broker():
        raise SystemExit(f"Kafka is not reachable at {settings.bootstrap}")
    for topic, state in ensure_topics().items():
        print(f"{topic:16s} {state}")
