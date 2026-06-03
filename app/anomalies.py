import uuid
from datetime import datetime, timezone
from .models import AnomaliesResponse, AnomalyItem
from .database import get_events_by_store
from .metrics import compute_metrics

def detect_anomalies(store_id: str) -> AnomaliesResponse:
    events = get_events_by_store(store_id)
    anomalies = []
    now = datetime.now(timezone.utc)
    
    zone_last_visit = {}
    for e in events:
        if e['zone_id'] and e['event_type'] == 'ZONE_ENTER':
            dt = datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))
            zone_last_visit[e['zone_id']] = dt
            
    for zone, last_time in zone_last_visit.items():
        if (now - last_time).total_seconds() > 1800:
            anomalies.append(AnomalyItem(
                anomaly_id=str(uuid.uuid4()), type="DEAD_ZONE", severity="INFO",
                detected_at=now.isoformat(),
                details={"zone_id": zone, "minutes_since_last_visit": int((now - last_time).total_seconds() / 60)},
                suggested_action=f"Investigate zone {zone}. Consider repositioning displays or adding promotional signage"
            ))
            
    try:
        metrics = compute_metrics(store_id)
        if metrics.current_queue_depth > 5:
            anomalies.append(AnomalyItem(
                anomaly_id=str(uuid.uuid4()), type="BILLING_QUEUE_SPIKE",
                severity="WARN" if metrics.current_queue_depth < 10 else "CRITICAL",
                detected_at=now.isoformat(), details={"current_queue": metrics.current_queue_depth},
                suggested_action="Open additional billing counter or deploy floor staff to manage queue"
            ))
        if metrics.conversion_rate < 0.1 and metrics.unique_visitors > 10:
            anomalies.append(AnomalyItem(
                anomaly_id=str(uuid.uuid4()), type="CONVERSION_DROP", severity="WARN",
                detected_at=now.isoformat(), details={"conversion_rate": metrics.conversion_rate},
                suggested_action="Review store layout and staff deployment. Check if high-traffic zones are understaffed"
            ))
    except Exception:
        pass
        
    return AnomaliesResponse(store_id=store_id, active_anomalies=anomalies)
