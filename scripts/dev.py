"""Start, stop or inspect the whole stack: Kafka -> producer -> Spark -> API -> dashboard.

    python scripts/dev.py start      # start everything that is not already running, wait until it is ready
    python scripts/dev.py stop       # stop everything this script started
    python scripts/dev.py restart    # stop, then start
    python scripts/dev.py status     # show what is up

Each part runs as its own background process and writes to logs/<name>.log. Process ids are kept in
logs/pids.json so `stop` can end them later. Run it with the project's venv Python.
"""

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.common.config import settings  # noqa: E402

LOGS = ROOT / "logs"
PIDS = LOGS / "pids.json"
PY = sys.executable
JAVA_HOME = os.environ.get("JAVA_HOME") or r"C:\Program Files\Eclipse Adoptium\jdk-17.0.20.101-hotspot"
NPM = "npm.cmd" if os.name == "nt" else "npm"
API = f"http://127.0.0.1:{settings.api_port}"
ORDER = ("kafka", "api", "producer", "spark", "frontend")


# ---------------------------------------------------------------- helpers
def port_open(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0


def load_pids() -> dict:
    try:
        return json.loads(PIDS.read_text())
    except (OSError, ValueError):
        return {}


def save_pids(pids: dict) -> None:
    LOGS.mkdir(exist_ok=True)
    PIDS.write_text(json.dumps(pids, indent=2))


def alive(pid: int) -> bool:
    if os.name == "nt":
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True).stdout
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def api_json(path: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(API + path, timeout=timeout) as r:
            return json.load(r)
    except Exception:
        return None


def spawn(name: str, cmd: list, cwd: Path = ROOT, env: dict = None) -> int:
    LOGS.mkdir(exist_ok=True)
    log = open(LOGS / f"{name}.log", "ab")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    proc = subprocess.Popen(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT, env={**os.environ, **(env or {})},
                            creationflags=flags)
    return proc.pid


def wait_for(check, what: str, timeout: float = 120) -> None:
    end = time.time() + timeout
    while time.time() < end:
        if check():
            print(f"  ready: {what}")
            return
        time.sleep(1)
    raise SystemExit(f"Timed out after {timeout:.0f}s waiting for {what}. Look in logs/ for the reason.")


def kafka_cmd() -> list:
    script = ROOT / "kafka" / "bin" / ("windows/kafka-server-start.bat" if os.name == "nt" else "kafka-server-start.sh")
    if not script.exists():
        raise SystemExit(f"Kafka is not installed at {ROOT / 'kafka'}. See 'Setup' in the README (download Kafka, then run "
                         f"scripts/setup_kafka.py).")
    config = ROOT / "kafka" / "config" / "binance-kraft.properties"
    if not config.exists():
        raise SystemExit(f"{config} is missing. Run: python scripts/setup_kafka.py")
    return (["cmd", "/c"] if os.name == "nt" else []) + [str(script), str(config)]


def stop_process(pid: int, force: bool) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T"] + (["/F"] if force else []), capture_output=True)
    else:
        os.kill(pid, 9 if force else 15)


# ---------------------------------------------------------------- commands
def start() -> None:
    pids = load_pids()
    started = []

    def run(name, cmd, ready=None, **kw):
        if pids.get(name) and alive(pids[name]):
            print(f"  {name}: already running (pid {pids[name]})")
            return
        if ready and ready():
            print(f"  {name}: already running (started outside this script)")
            return
        pids[name] = spawn(name, cmd, **kw)
        save_pids(pids)
        started.append(name)
        print(f"  {name}: started (pid {pids[name]}) -> logs/{name}.log")

    print("Starting the stack")
    run("kafka", kafka_cmd(), ready=lambda: port_open(9092),
        env={"JAVA_HOME": JAVA_HOME, "KAFKA_HEAP_OPTS": "-Xmx512m -Xms512m", "LOG_DIR": str(LOGS / "kafka-server")})
    wait_for(lambda: port_open(9092), "Kafka on port 9092", 120)

    # The API creates the topics on start-up, so it goes before the producer and Spark.
    run("api", [PY, "-m", "backend.app.main"], ready=lambda: port_open(settings.api_port))
    wait_for(lambda: api_json("/api/health") is not None, f"the API on port {settings.api_port}", 60)
    wait_for(lambda: bool((api_json("/api/system") or {}).get("kafka", {}).get("topics")), "Kafka topics created", 60)
    run("producer", [PY, "-m", "backend.producer.binance_producer"])
    run("spark", [PY, "-m", "backend.streaming.jobs"])
    run("frontend", [NPM, "run", "dev"], cwd=ROOT / "frontend", ready=lambda: port_open(5173))

    wait_for(lambda: (api_json("/api/health") or {}).get("binance_feed") == "live", "trades arriving from Binance", 60)
    wait_for(lambda: (api_json("/api/health") or {}).get("spark") is True, "Spark producing results", 180)

    print("\nDashboard:  http://localhost:5173")
    print(f"API docs:   {API}/docs")


def stop() -> None:
    pids = load_pids()
    for name in reversed(ORDER):  # dashboard first, Kafka last so the others can disconnect cleanly
        pid = pids.get(name)
        if not pid or not alive(pid):
            continue
        stop_process(pid, force=False)  # ask politely first
        for _ in range(15):
            if not alive(pid):
                break
            time.sleep(0.5)
        if alive(pid):
            stop_process(pid, force=True)
        print(f"  stopped {name} (pid {pid})")
    save_pids({})


def status() -> None:
    pids = load_pids()
    health = api_json("/api/health") or {}
    for name, port in (("kafka", 9092), ("api", settings.api_port), ("frontend", 5173)):
        print(f"  {name:9} {'UP' if port_open(port) else 'down'} (port {port})")
    print(f"  {'producer':9} {'UP' if pids.get('producer') and alive(pids['producer']) else 'down'}"
          f"   Binance feed: {health.get('binance_feed', 'unknown')}")
    print(f"  {'spark':9} {'UP' if pids.get('spark') and alive(pids['spark']) else 'down'}"
          f"   producing results: {health.get('spark', 'unknown')}")


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "start"
    if action == "restart":
        stop()
        time.sleep(2)
        start()
    else:
        {"start": start, "stop": stop, "status": status}.get(action, lambda: sys.exit(__doc__))()
