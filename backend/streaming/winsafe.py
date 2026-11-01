"""
Make Spark Structured Streaming checkpoints work on Windows without winutils.exe.

Builds a tiny Java class (hadoop_shim/src/.../WinSafeFileSystem.java) with the JDK's
`javac`, and returns the Spark settings that route local file access through it.
On Linux/macOS nothing is needed and no settings are returned.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Dict

SHIM_DIR = Path(__file__).resolve().parent / "hadoop_shim"
SRC = SHIM_DIR / "src" / "binance" / "hadoop" / "WinSafeFileSystem.java"
JAR = SHIM_DIR / "winsafe-fs.jar"


def _java_tool(name: str) -> str:
    java_home = os.environ.get("JAVA_HOME")
    if java_home:
        exe = Path(java_home) / "bin" / (name + (".exe" if os.name == "nt" else ""))
        if exe.exists():
            return str(exe)
    return name  # fall back to PATH


def build_shim(force: bool = False) -> Path:
    """Compile and package the shim if the jar is missing or older than the source."""
    if JAR.exists() and not force and JAR.stat().st_mtime >= SRC.stat().st_mtime:
        return JAR
    import pyspark

    hadoop_api = next(Path(pyspark.__file__).parent.joinpath("jars").glob("hadoop-client-api-*.jar"))
    out = SHIM_DIR / "classes"
    out.mkdir(exist_ok=True)
    subprocess.run([_java_tool("javac"), "-cp", str(hadoop_api), "-d", str(out), str(SRC)], check=True)
    subprocess.run([_java_tool("jar"), "cf", str(JAR), "-C", str(out), "."], check=True)
    return JAR


def spark_windows_conf() -> Dict[str, str]:
    """Spark config needed for local checkpoints on Windows ({} elsewhere)."""
    if sys.platform != "win32":
        return {}
    jar = build_shim()
    return {
        "spark.hadoop.fs.file.impl": "binance.hadoop.WinSafeFileSystem",
        "spark.hadoop.fs.file.impl.disable.cache": "true",
        # the FileContext-based manager hardcodes RawLocalFileSystem; use the FileSystem-based one
        "spark.sql.streaming.checkpointFileManagerClass": (
            "org.apache.spark.sql.execution.streaming.FileSystemBasedCheckpointFileManager"
        ),
    }


if __name__ == "__main__":
    print(build_shim(force=True))
