"""
FastAPI service for the dashboard.

REST (JSON) for snapshots and history, and one WebSocket (/ws) that pushes a fresh "tick"
about once a second: prices, ranking, buyer/seller pressure, pipeline health, plus the trades
and alerts that arrived since the previous tick.

    python -m backend.app.main          # http://127.0.0.1:8100  (docs at /docs)
"""

import asyncio
import contextlib
import json
import logging
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.common.config import settings
from backend.common.kafka_admin import ensure_topics, wait_for_broker

from .hub import Hub
from .security import ConnectionLimiter, RateLimiter, client_ip
from .store import Store

log = logging.getLogger("api")
hub = Hub(Store(settings.db_path))
rate_limiter = RateLimiter(settings.api_rate_limit_per_min)
ws_limiter = ConnectionLimiter(settings.api_max_ws_per_ip)


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    if await asyncio.to_thread(wait_for_broker, 30):
        await asyncio.to_thread(ensure_topics)
    else:
        log.warning("Kafka is not reachable at %s; the API will keep retrying", settings.bootstrap)
    hub.start()
    yield
    hub.close()


app = FastAPI(title="Binance real-time trade analytics", version="1.1.0", lifespan=lifespan,
              docs_url="/docs" if settings.api_docs else None, redoc_url=None,
              openapi_url="/openapi.json" if settings.api_docs else None)
app.add_middleware(CORSMiddleware, allow_origins=settings.api_cors_origins, allow_methods=["GET"], allow_headers=["*"])


@app.middleware("http")
async def protect(request: Request, call_next):
    """Per-client request limit, plus a few safe response headers."""
    ip = client_ip(request.client and (request.client.host, request.client.port), request.headers.get("x-forwarded-for"))
    if not rate_limiter.allow(ip):
        return JSONResponse({"detail": "Too many requests. Please slow down."}, status_code=429,
                            headers={"Retry-After": "10"})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store"
    return response


def known_symbol(symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in settings.symbols and symbol not in hub.aggs:
        raise HTTPException(404, f"unknown symbol {symbol}")
    return symbol


@app.get("/api/health")
def health():
    system = hub.system()
    ok = system["kafka"]["connected"] and system["binance_feed"]["status"] == "live"
    return {"status": "ok" if ok else "degraded", "kafka": system["kafka"]["connected"],
            "binance_feed": system["binance_feed"]["status"], "spark": system["spark"]["alive"]}


@app.get("/api/overview")
def overview():
    """Latest price, 5-minute change, this minute's volume and buyer/seller split for every coin."""
    return {"coins": hub.overview(), "ts": int(time.time() * 1000)}


@app.get("/api/series/{symbol}")
def series(symbol: str, minutes: int = Query(60, ge=1, le=1440), bucket: Optional[int] = Query(None, ge=1, le=60)):
    """Candles (Spark's one-minute windows, merged into `bucket`-minute candles for long ranges) for a coin."""
    symbol = known_symbol(symbol)
    candles = hub.series(symbol, minutes, bucket)
    return {"symbol": symbol, "minutes": minutes, "bucket_min": candles[0]["bucket_min"] if candles else bucket, "candles": candles}


@app.get("/api/coin/{symbol}")
def coin(symbol: str):
    """Headline numbers for one coin: price, 5-minute/1-hour/24-hour change, 24-hour range, volume, buyer share, rank."""
    symbol = known_symbol(symbol)
    summary = hub.coin_summary(symbol)
    if summary is None:
        raise HTTPException(404, f"no data yet for {symbol}")
    return summary


@app.get("/api/hot")
def hot(minutes: int = Query(5, ge=1, le=60)):
    """Most active coins by traded value over the last N minutes, with change vs the N minutes before."""
    return {"minutes": minutes, "coins": hub.hot(minutes)}


@app.get("/api/pressure")
def pressure(minutes: int = Query(5, ge=1, le=60)):
    """Share of buyer-initiated vs seller-initiated volume per coin."""
    return hub.pressure(minutes)


@app.get("/api/alerts")
def alerts(limit: int = Query(100, ge=1, le=1500), type: Optional[str] = None, symbol: Optional[str] = None,
           since: Optional[int] = Query(None, description="only alerts at or after this time (ms since epoch)")):
    return {"alerts": hub.recent_alerts(limit, type, symbol.upper() if symbol else None, since)}


@app.get("/api/stats/alerts")
def alert_stats(days: int = Query(7, ge=1, le=30)):
    """How many alerts of each kind fired per coin per day (UTC), from the history store."""
    return {"days": days, "rows": hub.store.alert_stats(days) if hub.store else []}


@app.get("/api/trades")
def trades(limit: int = Query(100, ge=1, le=400), symbol: Optional[str] = None):
    return {"trades": hub.recent_trades(limit, symbol.upper() if symbol else None)}


@app.get("/api/system")
def system():
    return hub.system()


@app.get("/api/config")
def config():
    th = settings.thresholds
    return {"symbols": settings.symbols, "topics": settings.topics.all(),
            "thresholds": {"whale_min_usd": th.whale_min_usd, "whale_z": th.whale_z, "whale_ratio": th.whale_ratio,
                           "spike_pct": th.spike_pct, "surge_ratio": th.surge_ratio, "surge_min_usd": th.surge_min_usd}}


def tick(last_trade_ts: float, last_alert_seq: int):
    """Everything the UI needs for one second of updates."""
    with hub.lock:
        new_trades = [t for t in hub.feed if t["ing"] / 1000 > last_trade_ts][-60:]
        new_alerts = [a for a in hub.alerts if a["seq"] > last_alert_seq]
        alert_seq = hub.alert_seq
    return {
        "type": "tick", "ts": int(time.time() * 1000), "overview": hub.overview(), "hot": hub.hot(5),
        "pressure": hub.pressure(5), "system": hub.system(),
        "trades": new_trades[::-1], "alerts": sorted(new_alerts, key=lambda a: a["ts"], reverse=True),
    }, (new_trades[-1]["ing"] / 1000 if new_trades else last_trade_ts), alert_seq


@app.websocket("/ws")
async def ws(socket: WebSocket):
    ip = client_ip(socket.client and (socket.client.host, socket.client.port), socket.headers.get("x-forwarded-for"))
    if not ws_limiter.acquire(ip):
        await socket.close(code=1013)  # "try again later"
        return
    try:
        await socket.accept()
        await socket.send_text(json.dumps({"type": "snapshot", "alerts": hub.recent_alerts(300),
                                           "trades": hub.recent_trades(60), "config": config()}))
        last_trade_ts, last_alert_seq = time.time(), hub.alert_seq
        while True:
            payload, last_trade_ts, last_alert_seq = await asyncio.to_thread(tick, last_trade_ts, last_alert_seq)
            await socket.send_text(json.dumps(payload))
            await asyncio.sleep(1.0)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        ws_limiter.release(ip)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    uvicorn.run(app, host=settings.api_host, port=settings.api_port, log_level="warning")


if __name__ == "__main__":
    main()
