"""
NeuralEye — Analytics Service
Consumes Redis Stream events → builds behavioral graph →
runs anomaly detection → persists to SQLite → updates Redis cache.
"""
import os, sys, json, time, logging, sqlite3
from collections import defaultdict, deque
from datetime import datetime, timedelta

import redis
import numpy as np
from sklearn.ensemble import IsolationForest

sys.path.insert(0, "/app")
from events.schema import NeuralEvent, EventType, EVENTS_STREAM, CONSUMER_GROUP

logging.basicConfig(level=logging.INFO, format="%(asctime)s [ANALYTICS] %(message)s")
log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DB_PATH   = os.getenv("DB_PATH", "/data/neuraleye.db")

# ── SQLite Schema ────────────────────────────────────────────────────────────
SCHEMA = """
CREATE TABLE IF NOT EXISTS visits (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER,
    store_id    TEXT,
    entered_at  TEXT,
    left_at     TEXT,
    total_dwell REAL,
    zones_visited TEXT
);
CREATE TABLE IF NOT EXISTS zone_dwells (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id    INTEGER,
    zone_id     TEXT,
    entered_at  TEXT,
    dwell_secs  REAL,
    store_id    TEXT
);
CREATE TABLE IF NOT EXISTS anomalies (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    detected_at TEXT,
    event_type  TEXT,
    track_id    INTEGER,
    zone_id     TEXT,
    score       REAL,
    payload     TEXT
);
CREATE TABLE IF NOT EXISTS frame_stats (
    ts          TEXT,
    active_tracks INTEGER,
    camera_id   TEXT
);
CREATE INDEX IF NOT EXISTS idx_zone_dwells_zone ON zone_dwells(zone_id);
CREATE INDEX IF NOT EXISTS idx_zone_dwells_ts   ON zone_dwells(entered_at);
"""


class BehavioralGraph:
    """Lightweight in-memory graph: track → zones visited"""
    def __init__(self):
        self.track_zones: dict[int, list[str]] = defaultdict(list)
        self.zone_counts: dict[str, int]       = defaultdict(int)
        self.zone_dwell_samples: dict[str, deque] = defaultdict(lambda: deque(maxlen=200))
        self.active_tracks: set[int]            = set()
        self.checkout_queue: deque              = deque(maxlen=60)  # 1 reading/sec, 1min

    def add_zone_entry(self, track_id: int, zone_id: str):
        self.track_zones[track_id].append(zone_id)
        self.zone_counts[zone_id] += 1
        self.active_tracks.add(track_id)

    def add_dwell(self, zone_id: str, dwell_secs: float):
        self.zone_dwell_samples[zone_id].append(dwell_secs)

    def add_track_active(self, track_id: int):
        self.active_tracks.add(track_id)

    def remove_track(self, track_id: int):
        self.active_tracks.discard(track_id)

    def funnel(self, zone_order: list[str]) -> dict:
        """Conversion funnel across ordered zones"""
        counts = {z: 0 for z in zone_order}
        for zones in self.track_zones.values():
            visited = set(zones)
            for z in zone_order:
                if z in visited:
                    counts[z] += 1
        return counts

    def heatmap(self) -> dict[str, int]:
        return dict(self.zone_counts)

    def avg_dwell(self) -> dict[str, float]:
        return {
            z: round(float(np.mean(list(v))), 1)
            for z, v in self.zone_dwell_samples.items() if v
        }

    def snapshot(self) -> dict:
        return {
            "active_people": len(self.active_tracks),
            "zone_visits": self.heatmap(),
            "avg_dwell_seconds": self.avg_dwell(),
        }


class AnomalyDetector:
    """
    IsolationForest on dwell-time per zone.
    Retrained every 100 samples to adapt to store patterns.
    """
    def __init__(self):
        self.models:   dict[str, IsolationForest] = {}
        self.buffers:  dict[str, list]             = defaultdict(list)
        self.min_fit   = 20

    def record(self, zone_id: str, dwell: float) -> float | None:
        """Returns anomaly score (0-1) or None if not enough data"""
        self.buffers[zone_id].append([dwell])
        buf = self.buffers[zone_id]

        if len(buf) >= self.min_fit and len(buf) % 10 == 0:
            self.models[zone_id] = IsolationForest(
                contamination=0.08, random_state=42, n_estimators=50
            )
            self.models[zone_id].fit(buf[-200:])

        if zone_id in self.models:
            score = self.models[zone_id].score_samples([[dwell]])[0]
            # Normalize: more negative = more anomalous → flip to 0-1
            norm = 1 - (score + 0.5)
            return round(float(np.clip(norm, 0, 1)), 3)
        return None

    def predict_queue(self, checkout_counts: list[int]) -> dict:
        """Simple linear trend prediction for checkout queue"""
        if len(checkout_counts) < 5:
            return {"predicted_queue": None, "trend": "unknown"}
        x = np.arange(len(checkout_counts))
        y = np.array(checkout_counts)
        coeffs = np.polyfit(x, y, 1)
        slope  = coeffs[0]
        next_5 = max(0, round(float(y[-1] + slope * 5)))
        trend  = "rising" if slope > 0.2 else "falling" if slope < -0.2 else "stable"
        return {"predicted_queue": next_5, "trend": trend, "slope": round(float(slope), 3)}


class AnalyticsConsumer:
    def __init__(self):
        self.r       = redis.from_url(REDIS_URL, decode_responses=True)
        self.db      = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()
        self.graph   = BehavioralGraph()
        self.anomaly = AnomalyDetector()
        self._init_stream()

    def _init_stream(self):
        try:
            self.r.xgroup_create(EVENTS_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
        except redis.exceptions.ResponseError:
            pass  # Group already exists

    def _push_snapshot(self):
        """Push live snapshot to Redis for API to read — zero DB query for live calls"""
        snap = self.graph.snapshot()
        snap["queue_prediction"] = self.anomaly.predict_queue(
            list(self.graph.checkout_queue)
        )
        snap["updated_at"] = datetime.utcnow().isoformat()
        self.r.set("neuraleye:snapshot", json.dumps(snap), ex=30)

    def handle(self, event: NeuralEvent):
        t   = event.track_id
        z   = event.zone_id
        pay = event.payload

        match event.event_type:
            case EventType.PERSON_ENTERED:
                self.graph.add_track_active(t)

            case EventType.PERSON_LEFT:
                self.graph.remove_track(t)
                dwell = pay.get("total_dwell", 0)
                zones = json.dumps(self.graph.track_zones.get(t, []))
                self.db.execute(
                    "INSERT INTO visits(track_id,store_id,entered_at,left_at,total_dwell,zones_visited) "
                    "VALUES(?,?,?,?,?,?)",
                    (t, event.source.store_id, event.timestamp_utc,
                     datetime.utcnow().isoformat(), dwell, zones)
                )
                self.db.commit()

            case EventType.ZONE_ENTERED:
                if z:
                    self.graph.add_zone_entry(t, z)

            case EventType.ZONE_EXITED:
                if z:
                    dwell = float(pay.get("dwell_seconds", 0))
                    self.graph.add_dwell(z, dwell)
                    score = self.anomaly.record(z, dwell)
                    self.db.execute(
                        "INSERT INTO zone_dwells(track_id,zone_id,entered_at,dwell_secs,store_id) "
                        "VALUES(?,?,?,?,?)",
                        (t, z, event.timestamp_utc, dwell, event.source.store_id)
                    )
                    self.db.commit()

                    # Anomaly alert
                    if score and score > 0.80:
                        alert = NeuralEvent(
                            event_type=EventType.DWELL_ANOMALY,
                            track_id=t, zone_id=z,
                            source=event.source,
                            payload={"dwell_seconds": dwell, "anomaly_score": score},
                        )
                        self.r.xadd("neuraleye:alerts", alert.to_redis(), maxlen=500)
                        self.db.execute(
                            "INSERT INTO anomalies(detected_at,event_type,track_id,zone_id,score,payload) "
                            "VALUES(?,?,?,?,?,?)",
                            (datetime.utcnow().isoformat(), "DWELL_ANOMALY",
                             t, z, score, json.dumps(pay))
                        )
                        self.db.commit()
                        log.warning("ANOMALY track=%s zone=%s score=%.2f dwell=%.0fs", t, z, score, dwell)

            case EventType.FRAME_STATS:
                active = pay.get("active_tracks", 0)
                # Track checkout queue
                if "checkout" in (z or ""):
                    self.graph.checkout_queue.append(active)
                self.db.execute(
                    "INSERT INTO frame_stats(ts,active_tracks,camera_id) VALUES(?,?,?)",
                    (event.timestamp_utc, active, event.source.camera_id)
                )
                self.db.commit()

        self._push_snapshot()

    def run(self):
        log.info("Analytics consumer started")
        while True:
            try:
                msgs = self.r.xreadgroup(
                    CONSUMER_GROUP, "worker-1", {EVENTS_STREAM: ">"},
                    count=50, block=1000
                )
                if not msgs:
                    continue
                for _, records in msgs:
                    for msg_id, data in records:
                        try:
                            event = NeuralEvent.from_redis(data)
                            self.handle(event)
                            self.r.xack(EVENTS_STREAM, CONSUMER_GROUP, msg_id)
                        except Exception as e:
                            log.error("Event error: %s | data: %s", e, data)
            except Exception as e:
                log.error("Stream error: %s", e)
                time.sleep(2)


if __name__ == "__main__":
    AnalyticsConsumer().run()
