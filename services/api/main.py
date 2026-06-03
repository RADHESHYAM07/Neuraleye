"""
NeuralEye — Intelligence API
FastAPI service exposing all analytics endpoints + WebSocket live feed.
"""
import os, sys, json, sqlite3, asyncio, logging
from datetime import datetime, timedelta
from typing import Optional
from contextlib import asynccontextmanager
from collections import defaultdict

import redis.asyncio as aioredis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

sys.path.insert(0, "/app")
from events.schema import NeuralEvent, EventType, EVENTS_STREAM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [API] %(message)s")
log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_PATH   = os.getenv("DB_PATH", "/data/neuraleye.db")

# ── Globals ──────────────────────────────────────────────────────────────────
rdb: aioredis.Redis = None
ws_clients: list[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rdb
    rdb = aioredis.from_url(REDIS_URL, decode_responses=True)
    asyncio.create_task(alert_broadcaster())
    yield
    await rdb.aclose()


app = FastAPI(
    title="NeuralEye Store Intelligence API",
    version="1.2.0",
    description="Real-time store intelligence from CCTV footage",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)


def get_db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


# ── Live snapshot (Redis cache hit, <1ms) ────────────────────────────────────
@app.get("/api/v1/live", tags=["Live"])
async def live_snapshot():
    """Real-time store state — served from Redis cache, sub-millisecond latency"""
    raw = await rdb.get("neuraleye:snapshot")
    if not raw:
        return {"active_people": 0, "zone_visits": {}, "avg_dwell_seconds": {}}
    return json.loads(raw)


# ── Heatmap ──────────────────────────────────────────────────────────────────
@app.get("/api/v1/heatmap", tags=["Analytics"])
async def heatmap(hours: int = Query(1, ge=1, le=24)):
    """Zone visit counts over last N hours"""
    db  = get_db()
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    rows  = db.execute(
        "SELECT zone_id, COUNT(*) as visits, AVG(dwell_secs) as avg_dwell "
        "FROM zone_dwells WHERE entered_at > ? GROUP BY zone_id",
        (since,)
    ).fetchall()
    db.close()
    return {
        "hours": hours,
        "zones": [
            {"zone_id": r[0], "visits": r[1], "avg_dwell_seconds": round(r[2] or 0, 1)}
            for r in rows
        ]
    }


# ── Dwell Time ───────────────────────────────────────────────────────────────
@app.get("/api/v1/dwell-time", tags=["Analytics"])
async def dwell_time(zone_id: Optional[str] = None, hours: int = Query(1, ge=1, le=24)):
    """Average and distribution of dwell times per zone"""
    db    = get_db()
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    q     = "SELECT zone_id, dwell_secs FROM zone_dwells WHERE entered_at > ?"
    params: list = [since]
    if zone_id:
        q += " AND zone_id = ?"
        params.append(zone_id)

    rows = db.execute(q, params).fetchall()
    db.close()

    by_zone: dict[str, list] = defaultdict(list)
    for zone, d in rows:
        by_zone[zone].append(d)

    import numpy as np
    result = []
    for z, dwells in by_zone.items():
        arr = [d for d in dwells if d]
        if arr:
            result.append({
                "zone_id": z,
                "sample_count": len(arr),
                "avg_seconds": round(float(sum(arr) / len(arr)), 1),
                "p50_seconds": round(float(sorted(arr)[len(arr)//2]), 1),
                "p95_seconds": round(float(sorted(arr)[int(len(arr)*0.95)]), 1),
                "max_seconds": round(float(max(arr)), 1),
            })
    return {"hours": hours, "zones": result}


# ── Conversion Funnel ────────────────────────────────────────────────────────
@app.get("/api/v1/funnel", tags=["Analytics"])
async def conversion_funnel(hours: int = Query(1, ge=1, le=24)):
    """Store conversion funnel: Entry → Beauty → Skincare → Checkout"""
    db    = get_db()
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()

    # Get all tracks and their visited zones
    rows = db.execute(
        "SELECT track_id, zone_id FROM zone_dwells WHERE entered_at > ? ORDER BY entered_at",
        (since,)
    ).fetchall()
    db.close()

    funnel_zones = ["entry", "beauty", "skincare", "haircare", "checkout"]
    track_zones: dict[int, set] = defaultdict(set)
    for tid, z in rows:
        track_zones[tid].add(z)

    total = len(track_zones)
    funnel = []
    for i, z in enumerate(funnel_zones):
        count = sum(1 for zones in track_zones.values() if z in zones)
        funnel.append({
            "stage": i + 1,
            "zone_id": z,
            "visitors": count,
            "conversion_rate": round(count / total * 100, 1) if total > 0 else 0,
        })

    return {"hours": hours, "total_visitors": total, "funnel": funnel}


# ── Anomalies ────────────────────────────────────────────────────────────────
@app.get("/api/v1/anomalies", tags=["Intelligence"])
async def anomalies(hours: int = Query(1, ge=1, le=24), limit: int = 50):
    """Recent anomaly detections with scores"""
    db    = get_db()
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    rows  = db.execute(
        "SELECT detected_at, event_type, track_id, zone_id, score, payload "
        "FROM anomalies WHERE detected_at > ? ORDER BY score DESC LIMIT ?",
        (since, limit)
    ).fetchall()
    db.close()
    return {
        "hours": hours,
        "count": len(rows),
        "anomalies": [
            {
                "detected_at": r[0], "event_type": r[1],
                "track_id": r[2], "zone_id": r[3],
                "score": r[4], "detail": json.loads(r[5] or "{}")
            } for r in rows
        ]
    }


# ── Behavioral Graph ─────────────────────────────────────────────────────────
@app.get("/api/v1/behavioral-graph", tags=["Intelligence"])
async def behavioral_graph(hours: int = Query(1, ge=1, le=8)):
    """
    Zone-to-zone transition graph — which zones lead to which.
    Returns nodes + weighted edges for visualization.
    """
    db    = get_db()
    since = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    rows  = db.execute(
        "SELECT track_id, zone_id, entered_at FROM zone_dwells "
        "WHERE entered_at > ? ORDER BY track_id, entered_at",
        (since,)
    ).fetchall()
    db.close()

    # Build transitions
    track_seq: dict[int, list] = defaultdict(list)
    for tid, z, ts in rows:
        track_seq[tid].append(z)

    edges: dict[tuple, int] = defaultdict(int)
    nodes: set[str]         = set()
    for zones in track_seq.values():
        for i in range(len(zones) - 1):
            if zones[i] != zones[i+1]:
                edges[(zones[i], zones[i+1])] += 1
                nodes.add(zones[i])
                nodes.add(zones[i+1])

    return {
        "hours": hours,
        "nodes": [{"id": n} for n in nodes],
        "edges": [
            {"from": k[0], "to": k[1], "weight": v}
            for k, v in sorted(edges.items(), key=lambda x: -x[1])
        ],
    }


# ── Queue Prediction ─────────────────────────────────────────────────────────
@app.get("/api/v1/queue-prediction", tags=["Intelligence"])
async def queue_prediction():
    """Predict checkout queue size in next 5 minutes"""
    raw = await rdb.get("neuraleye:snapshot")
    if not raw:
        return {"predicted_queue": None, "trend": "unknown"}
    snap = json.loads(raw)
    return snap.get("queue_prediction", {"predicted_queue": None, "trend": "unknown"})


# ── People Count Timeseries ──────────────────────────────────────────────────
@app.get("/api/v1/traffic", tags=["Analytics"])
async def traffic(minutes: int = Query(60, ge=5, le=1440)):
    """Footfall over time — bucketed by minute"""
    db    = get_db()
    since = (datetime.utcnow() - timedelta(minutes=minutes)).isoformat()
    rows  = db.execute(
        "SELECT strftime('%Y-%m-%dT%H:%M', ts) as bucket, AVG(active_tracks) "
        "FROM frame_stats WHERE ts > ? GROUP BY bucket ORDER BY bucket",
        (since,)
    ).fetchall()
    db.close()
    return {
        "minutes": minutes,
        "series": [{"time": r[0], "count": round(r[1] or 0)} for r in rows]
    }


# ── WebSocket live feed ───────────────────────────────────────────────────────
@app.websocket("/ws/live")
async def websocket_live(ws: WebSocket):
    await ws.accept()
    ws_clients.append(ws)
    log.info("WS client connected. Total: %d", len(ws_clients))
    try:
        while True:
            raw = await rdb.get("neuraleye:snapshot")
            if raw:
                await ws.send_text(raw)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        ws_clients.remove(ws)
        log.info("WS client disconnected. Total: %d", len(ws_clients))


async def alert_broadcaster():
    """Push anomaly alerts to all WS clients in real-time"""
    alert_rdb = aioredis.from_url(REDIS_URL, decode_responses=True)
    last_id = "$"
    while True:
        try:
            msgs = await alert_rdb.xread({"neuraleye:alerts": last_id}, block=500, count=10)
            for _, records in msgs:
                for msg_id, data in records:
                    last_id = msg_id
                    alert   = {"type": "ALERT", **data}
                    dead    = []
                    for ws in ws_clients:
                        try:
                            await ws.send_text(json.dumps(alert))
                        except Exception:
                            dead.append(ws)
                    for ws in dead:
                        ws_clients.remove(ws)
        except Exception as e:
            log.error("Alert broadcast error: %s", e)
            await asyncio.sleep(1)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.2.0", "time": datetime.utcnow().isoformat()}
