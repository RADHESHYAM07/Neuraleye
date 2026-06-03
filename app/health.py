import time
from datetime import datetime, timezone
from .models import HealthResponse, StoreHealth
from .database import get_last_event_per_store

START_TIME = time.time()

def get_health() -> HealthResponse:
    last_events = get_last_event_per_store()
    now = datetime.now(timezone.utc)
    
    stores = []
    overall_status = "ok"
    
    for store_id, last_ts_str in last_events.items():
        status = "OK"
        if last_ts_str:
            last_dt = datetime.fromisoformat(last_ts_str.replace('Z', '+00:00'))
            if (now - last_dt).total_seconds() > 600:
                status = "STALE_FEED"
                overall_status = "degraded"
        stores.append(StoreHealth(store_id=store_id, last_event_at=last_ts_str, status=status))
        
    return HealthResponse(status=overall_status, version="1.0.0", uptime_seconds=time.time() - START_TIME, stores=stores)
