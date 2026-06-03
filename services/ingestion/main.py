"""
NeuralEye — Ingestion Service
Reads video (or simulates), runs YOLOv8n + ByteTrack,
maps tracks to zones, publishes NeuralEvents to Redis Streams.
"""
import os, sys, time, json, asyncio, logging
from pathlib import Path

import numpy as np
import redis
from shapely.geometry import Point, Polygon

sys.path.insert(0, "/app")

sys.path.insert(0, "/app")
from events.schema import NeuralEvent, EventType, TrackSource, EVENTS_STREAM

logging.basicConfig(level=logging.INFO, format="%(asctime)s [INGEST] %(message)s")
log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379")
ZONE_CONFIG  = os.getenv("ZONE_CONFIG", "/app/config/zones.json")
VIDEO_SOURCE = os.getenv("VIDEO_SOURCE", "/data/cctv.mp4")
FPS_TARGET   = int(os.getenv("FPS_TARGET", "5"))
CAMERA_ID    = os.getenv("CAMERA_ID", "cam_01")
STORE_ID     = os.getenv("STORE_ID", "PUR_MUM_001")


def load_zones(path: str):
    with open(path) as f:
        cfg = json.load(f)
    zones = {}
    for z in cfg["zones"]:
        zones[z["id"]] = {
            **z,
            "poly": Polygon(z["polygon"]),
        }
    return zones, cfg


def point_to_zone(x: float, y: float, zones: dict) -> str | None:
    pt = Point(x, y)
    for zid, z in zones.items():
        if z["poly"].contains(pt):
            return zid
    return None


class TrackState:
    """Per-track state machine"""
    def __init__(self, track_id: int):
        self.id          = track_id
        self.zone        = None
        self.zone_enter  = None
        self.first_seen  = time.time()
        self.last_seen   = time.time()
        self.positions   = []

    def update(self, x, y, zone):
        self.last_seen = time.time()
        self.positions.append((x, y))
        if len(self.positions) > 30:
            self.positions.pop(0)
        return zone != self.zone


class IngestionPipeline:
    def __init__(self):
        self.r      = redis.from_url(REDIS_URL, decode_responses=True)
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Failed to import ultralytics. Check your requirements."
            ) from exc
        self.model = YOLO("yolov8n.pt")
        self.zones, self.cfg = load_zones(ZONE_CONFIG)
        self.tracks: dict[int, TrackState] = {}
        self.source = TrackSource(camera_id=CAMERA_ID, store_id=STORE_ID)
        log.info("Pipeline ready. Zones: %s", list(self.zones.keys()))

    def publish(self, event: NeuralEvent):
        self.r.xadd(EVENTS_STREAM, event.to_redis(), maxlen=10000)

    def process_frame(self, frame: np.ndarray, frame_id: int):
        results = self.model.track(
            frame,
            persist=True,
            classes=[0],          # person only
            conf=0.4,
            iou=0.5,
            tracker="bytetrack.yaml",
            verbose=False,
        )
        active_ids = set()

        if results[0].boxes.id is not None:
            boxes = results[0].boxes
            for box, tid in zip(boxes.xywh.cpu().numpy(),
                                boxes.id.cpu().numpy().astype(int)):
                cx, cy, w, h = box
                foot_y = cy + h / 2          # bottom-center = foot position
                zone   = point_to_zone(cx, foot_y, self.zones)
                active_ids.add(tid)

                if tid not in self.tracks:
                    # New person entered the store
                    self.tracks[tid] = TrackState(tid)
                    self.publish(NeuralEvent(
                        event_type=EventType.PERSON_ENTERED,
                        track_id=int(tid), zone_id=zone,
                        source=self.source,
                        payload={"bbox": [float(cx), float(cy), float(w), float(h)]},
                    ))

                st = self.tracks[tid]
                zone_changed = st.update(cx, foot_y, zone)

                if zone_changed:
                    if st.zone:
                        dwell = time.time() - (st.zone_enter or st.first_seen)
                        self.publish(NeuralEvent(
                            event_type=EventType.ZONE_EXITED,
                            track_id=int(tid), zone_id=st.zone,
                            source=self.source,
                            payload={"dwell_seconds": round(dwell, 1)},
                        ))
                    st.zone = zone
                    st.zone_enter = time.time()
                    if zone:
                        self.publish(NeuralEvent(
                            event_type=EventType.ZONE_ENTERED,
                            track_id=int(tid), zone_id=zone,
                            source=self.source,
                            payload={},
                        ))

        # People who disappeared
        gone = set(self.tracks) - active_ids
        for tid in gone:
            st = self.tracks.pop(tid)
            self.publish(NeuralEvent(
                event_type=EventType.PERSON_LEFT,
                track_id=int(tid),
                source=self.source,
                payload={"total_dwell": round(time.time() - st.first_seen, 1)},
            ))

        # Frame stats (heartbeat)
        if frame_id % 25 == 0:
            self.publish(NeuralEvent(
                event_type=EventType.FRAME_STATS,
                source=self.source,
                payload={"active_tracks": len(active_ids), "frame_id": frame_id},
            ))

        return results[0]

    def run_video(self, path: str):
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError("Video mode requires OpenCV.") from exc

        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            log.error("Failed to open video source: %s", path)
            return

        orig_fps = cap.get(cv2.CAP_PROP_FPS) or 25
        skip = max(1, int(orig_fps / FPS_TARGET))
        frame_id = 0
        log.info("Processing video at %sfps (skip=%s) from %s", FPS_TARGET, skip, path)

        # Setup VideoWriter to save the output so the user can see it
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        output_path = "/data/video/output_annotated.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out_writer = cv2.VideoWriter(output_path, fourcc, FPS_TARGET, (width, height))
        log.info("Saving annotated video to %s", output_path)

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            if frame_id % skip == 0:
                result = self.process_frame(frame, frame_id)
                annotated_frame = result.plot()
                out_writer.write(annotated_frame)
            frame_id += 1

        cap.release()
        out_writer.release()
        log.info("Video processing complete. %d frames. Saved to %s", frame_id, output_path)


if __name__ == "__main__":
    pipe = IngestionPipeline()
    pipe.run_video(VIDEO_SOURCE)
