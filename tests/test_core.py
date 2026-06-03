"""
NeuralEye — Test Suite
Run: pytest tests/ -v
"""
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from services.events.schema import NeuralEvent, EventType, TrackSource


# ── Event Schema Tests ────────────────────────────────────────────────────────
class TestEventSchema:
    def _src(self):
        return TrackSource(camera_id="cam_01", store_id="PUR_TEST")

    def test_event_roundtrip(self):
        ev = NeuralEvent(
            event_type=EventType.ZONE_ENTERED,
            track_id=42, zone_id="skincare",
            source=self._src(),
            payload={"test": True}
        )
        redis_dict = ev.to_redis()
        assert isinstance(redis_dict, dict)
        assert all(isinstance(v, str) for v in redis_dict.values())

        recovered = NeuralEvent.from_redis(redis_dict)
        assert recovered.event_id   == ev.event_id
        assert recovered.track_id   == 42
        assert recovered.zone_id    == "skincare"
        assert recovered.event_type == EventType.ZONE_ENTERED
        assert recovered.payload    == {"test": True}

    def test_event_has_uuid(self):
        e1 = NeuralEvent(event_type=EventType.PERSON_ENTERED, source=self._src())
        e2 = NeuralEvent(event_type=EventType.PERSON_ENTERED, source=self._src())
        assert e1.event_id != e2.event_id

    def test_event_has_timestamp(self):
        ev = NeuralEvent(event_type=EventType.FRAME_STATS, source=self._src())
        assert "T" in ev.timestamp_utc  # ISO format

    def test_schema_version(self):
        ev = NeuralEvent(event_type=EventType.QUEUE_ALERT, source=self._src())
        assert ev.schema_version == "1.2"


# ── Anomaly Detector Tests ────────────────────────────────────────────────────
class TestAnomalyDetector:
    def setup_method(self):
        from services.analytics.main import AnomalyDetector
        self.det = AnomalyDetector()

    def test_no_score_before_min_samples(self):
        for i in range(15):
            score = self.det.record("beauty", 60.0)
        assert score is None  # needs 20 samples

    def test_score_after_min_samples(self):
        for i in range(25):
            self.det.record("beauty", 60.0 + i * 0.5)
        score = self.det.record("beauty", 62.0)
        assert score is not None
        assert 0.0 <= score <= 1.0

    def test_anomaly_high_score_for_outlier(self):
        # Train on normal dwells ~60s
        for i in range(50):
            self.det.record("skincare", 60.0 + (i % 10))
        # Very long dwell should score high
        score = self.det.record("skincare", 1200.0)
        assert score is not None
        assert score > 0.5

    def test_queue_prediction_rising(self):
        from services.analytics.main import AnomalyDetector
        det = AnomalyDetector()
        result = det.predict_queue([1, 2, 3, 4, 5, 6, 7])
        assert result["trend"] == "rising"

    def test_queue_prediction_stable(self):
        from services.analytics.main import AnomalyDetector
        det = AnomalyDetector()
        result = det.predict_queue([5, 5, 5, 5, 5])
        assert result["trend"] == "stable"


# ── Behavioral Graph Tests ────────────────────────────────────────────────────
class TestBehavioralGraph:
    def setup_method(self):
        from services.analytics.main import BehavioralGraph
        self.g = BehavioralGraph()

    def test_zone_entry_counted(self):
        self.g.add_zone_entry(1, "beauty")
        self.g.add_zone_entry(2, "beauty")
        self.g.add_zone_entry(3, "skincare")
        hm = self.g.heatmap()
        assert hm["beauty"] == 2
        assert hm["skincare"] == 1

    def test_dwell_average(self):
        self.g.add_dwell("beauty", 60.0)
        self.g.add_dwell("beauty", 120.0)
        avg = self.g.avg_dwell()
        assert avg["beauty"] == 90.0

    def test_funnel_conversion(self):
        # 3 people visit entry, 2 visit beauty, 1 visits checkout
        self.g.add_zone_entry(1, "entry"); self.g.add_zone_entry(1, "beauty"); self.g.add_zone_entry(1, "checkout")
        self.g.add_zone_entry(2, "entry"); self.g.add_zone_entry(2, "beauty")
        self.g.add_zone_entry(3, "entry")
        funnel = self.g.funnel(["entry", "beauty", "checkout"])
        assert funnel["entry"] == 3
        assert funnel["beauty"] == 2
        assert funnel["checkout"] == 1

    def test_active_tracks(self):
        self.g.add_track_active(1)
        self.g.add_track_active(2)
        snap = self.g.snapshot()
        assert snap["active_people"] == 2
        self.g.remove_track(1)
        assert self.g.snapshot()["active_people"] == 1
