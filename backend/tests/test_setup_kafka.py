"""The Kafka installer's safety checks (no network)."""

import importlib.util
import io
import tarfile
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("setup_kafka", Path(__file__).resolve().parents[2] / "scripts" / "setup_kafka.py")
setup_kafka = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(setup_kafka)


def make_tar(path: Path, entries: dict) -> None:
    with tarfile.open(path, "w:gz") as tar:
        for name, data in entries.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))


def test_normal_archive_extracts(tmp_path):
    make_tar(tmp_path / "a.tgz", {"kafka_2.13-3.9.1/bin/x.sh": b"echo hi"})

    setup_kafka.safe_extract(tmp_path / "a.tgz", tmp_path / "out")

    assert (tmp_path / "out" / "kafka_2.13-3.9.1" / "bin" / "x.sh").read_bytes() == b"echo hi"


def test_path_traversal_is_refused(tmp_path):
    make_tar(tmp_path / "evil.tgz", {"../escape.txt": b"x"})

    with pytest.raises(ValueError, match="outside"):
        setup_kafka.safe_extract(tmp_path / "evil.tgz", tmp_path / "out")
    assert not (tmp_path / "escape.txt").exists()


def test_links_are_refused(tmp_path):
    with tarfile.open(tmp_path / "link.tgz", "w:gz") as tar:
        info = tarfile.TarInfo("kafka/link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        tar.addfile(info)

    with pytest.raises(ValueError, match="link"):
        setup_kafka.safe_extract(tmp_path / "link.tgz", tmp_path / "out")


def test_checksum_helper_matches_hashlib(tmp_path):
    f = tmp_path / "f"
    f.write_bytes(b"hello")

    assert setup_kafka.sha512_of(f) == "9b71d224bd62f3785d96d46ad3ea3d73319bfbc2890caadae2dff72519673ca72323c3d99ba5c11d7c7acc6e14b8c5da0c4663475c2e5c3adef46f73bcdec043"


def test_pinned_checksum_is_the_verified_one():
    assert len(setup_kafka.KAFKA_SHA512) == 128
    assert setup_kafka.KAFKA_SHA512.startswith("1ea204ba") and setup_kafka.KAFKA_SHA512.endswith("23fa2cfe")
