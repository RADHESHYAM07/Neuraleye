from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
from contextlib import asynccontextmanager

from .database import init_db
from .models import IngestRequest, IngestResponse, MetricsResponse, FunnelResponse, HeatmapResponse, AnomaliesResponse, HealthResponse
from .ingestion import ingest_events
from .metrics import compute_metrics
from .funnel import compute_funnel
from .heatmap import compute_heatmap
from .anomalies import detect_anomalies
from .health import get_health
from .middleware import StructuredLoggingMiddleware

logger = logging.getLogger("neuraleye")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Store Intelligence API", lifespan=lifespan)
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

@app.post("/events/ingest", response_model=IngestResponse)
async def api_ingest(request: IngestRequest):
    try:
        return ingest_events(request.events)
    except Exception as e:
        logger.error(f"Ingest error: {e}")
        raise HTTPException(status_code=503, detail={"error": "service_unavailable", "detail": str(e), "retry_after_seconds": 5})

@app.get("/stores/{store_id}/metrics", response_model=MetricsResponse)
async def api_metrics(store_id: str):
    try:
        return compute_metrics(store_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable", "detail": str(e)})

@app.get("/stores/{store_id}/funnel", response_model=FunnelResponse)
async def api_funnel(store_id: str):
    try:
        return compute_funnel(store_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable", "detail": str(e)})

@app.get("/stores/{store_id}/heatmap", response_model=HeatmapResponse)
async def api_heatmap(store_id: str):
    try:
        return compute_heatmap(store_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable", "detail": str(e)})

@app.get("/stores/{store_id}/anomalies", response_model=AnomaliesResponse)
async def api_anomalies(store_id: str):
    try:
        return detect_anomalies(store_id)
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable", "detail": str(e)})

@app.get("/health", response_model=HealthResponse)
async def api_health():
    try:
        return get_health()
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "service_unavailable", "detail": str(e)})
