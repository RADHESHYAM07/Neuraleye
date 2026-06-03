# NeuralEye — Store Intelligence API

## System Overview
The Store Intelligence API transforms raw CCTV video frames into real-time business intelligence for retail operations. The system captures physical shopper activity, links it to digital transaction data (POS), and exposes metrics via a REST API.

```
[ CCTV Streams ] -> [ YOLOv8n + ByteTrack ] -> (JSON Events) -> [ FastAPI Ingestion ] -> SQLite (WAL)
                                                                           |
                                                                           v
                                                         Dashboard <--- Metrics API
```

## Architecture
The system employs a 3-tier architecture:
1. **Edge Detection Pipeline**: Operates locally on CCTV feeds to detect persons and their trajectories. Produces lightweight JSON events (entries, zone dwells, queue joins).
2. **Intelligence API**: A FastAPI service that ingests events, stores them durably, and provides rich analytics such as conversion funnels and anomaly detection.
3. **Live Dashboard**: A real-time WebSocket and REST-driven UI presenting actionable insights.

## Data Model
The system uses a highly structured Event Schema consisting of 8 types (ENTRY, EXIT, ZONE_ENTER, ZONE_EXIT, ZONE_DWELL, BILLING_QUEUE_JOIN, BILLING_QUEUE_ABANDON, REENTRY). All metrics and funnels use the "visitor session" as the atomic unit, mapping disparate events to a single `visitor_id`.

## Detection Pipeline
We leverage YOLOv8n for fast inference (suitable for CPU-constrained environments) paired with ByteTrack for maintaining persistent IDs across frames. Zone boundaries are defined via polygons, allowing the pipeline to emit ZONE_ENTER/EXIT events automatically when tracking centroids cross boundaries.

## AI-Assisted Decisions

### 1. Event Schema Design
I used an AI assistant to evaluate different event schema approaches. The AI initially suggested a flat schema with all fields at the top level. I disagreed and implemented a schema with a nested `metadata` object because it separates core identification fields from contextual data, making the API extensible without breaking consumers.

### 2. Anomaly Detection Approach
I prompted an LLM to compare IsolationForest vs fixed thresholds vs Z-score for retail anomaly detection. The AI recommended IsolationForest for dwell-time anomalies but suggested simple threshold-based detection for queue spikes and conversion drops. I agreed because queue spikes are best detected with rolling averages and don't require pre-training.

### 3. Database Choice: SQLite over PostgreSQL
I asked the AI to evaluate SQLite vs PostgreSQL. The AI identified that at <100 events/sec, SQLite with WAL mode handles the load perfectly. I agreed but added the caveat that scaling beyond 40 stores would necessitate PostgreSQL.

## Scaling Considerations
As Apex Retail scales from 40 to 400 stores:
1. **Database Migration**: Move from SQLite to PostgreSQL + TimescaleDB for time-series aggregation.
2. **Message Broker**: Introduce Apache Kafka between the Edge pipeline and the API for robust backpressure and decoupled processing.
