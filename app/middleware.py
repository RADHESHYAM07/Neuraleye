import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import json

logger = logging.getLogger("neuraleye.request")

class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = str(uuid.uuid4())
        start_time = time.time()
        response = await call_next(request)
        latency_ms = (time.time() - start_time) * 1000
        
        store_id = None
        if "stores/" in request.url.path:
            parts = request.url.path.split("/")
            if "stores" in parts:
                idx = parts.index("stores")
                if idx + 1 < len(parts):
                    store_id = parts[idx+1]
                    
        log_data = {
            "trace_id": trace_id, "store_id": store_id,
            "endpoint": request.url.path, "method": request.method,
            "latency_ms": round(latency_ms, 2), "status_code": response.status_code,
            "event_count": None
        }
        
        logger.info(json.dumps(log_data))
        response.headers["X-Trace-ID"] = trace_id
        return response
