from typing import List
import json
import logging
import redis
import os
from .models import StoreEvent, IngestResponse
from .database import insert_events_bulk

logger = logging.getLogger("neuraleye.ingestion")

redis_client = None
if "REDIS_URL" in os.environ:
    try:
        redis_client = redis.from_url(os.environ["REDIS_URL"])
    except Exception as e:
        logger.error(f"Failed to connect to Redis: {e}")

def ingest_events(events: List[StoreEvent]) -> IngestResponse:
    accepted = 0
    rejected = 0
    errors = []
    
    valid_events = []
    for event in events:
        try:
            valid_events.append(event.model_dump())
            accepted += 1
            if redis_client:
                try:
                    redis_client.xadd(
                        f"events:{event.store_id}", 
                        {"event": json.dumps(event.model_dump())}, 
                        maxlen=1000
                    )
                except Exception:
                    pass
        except Exception as e:
            rejected += 1
            errors.append({"event_id": event.event_id, "error": str(e)})

    if valid_events:
        insert_events_bulk(valid_events)

    return IngestResponse(accepted=accepted, rejected=rejected, errors=errors)
