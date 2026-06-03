# Technical Choices — Store Intelligence API

## Decision 1: Detection Model — YOLOv8n (nano)

### Options Considered
1. **YOLOv8n** — Smallest variant, ~80ms/frame CPU, ~72% person mAP
2. **YOLOv8s** — Small variant, ~200ms/frame CPU, ~76% person mAP
3. **RT-DETR** — Transformer-based, high accuracy, slow on CPU

### What AI Suggested
The AI recommended YOLOv8s as a balance between accuracy and speed, arguing the 4% mAP improvement over nano was worth the latency increase.

### What I Chose & Why
I chose YOLOv8n because:
- At a 5fps processing target, the nano model provides 10x headroom on CPU.
- Production retail NVRs run on Intel NUCs, not GPU servers — CPU inference speed is the main constraint.
- The 4% mAP difference is practically irrelevant for bounding box person counting (we don't need fine-grained classification).
- Lower compute translates directly to lower cloud costs when scaling to 40 stores with 3 cameras each (120 parallel streams).

## Decision 2: Event Schema — Flat with Metadata Object

### Options Considered
1. Fully flat schema (all fields top-level)
2. Nested schema (event → detection → context → zone)
3. Flat core + metadata object (chosen)

### What AI Suggested
The AI suggested a purely flat schema for simplicity, as it maps directly to SQL columns without JSON parsing.

### What I Chose & Why
I chose a hybrid approach (Flat core + metadata object) because it guarantees backward compatibility for edge devices. Core fields (store_id, timestamp, event_type) remain rigid, but the `metadata` JSON object allows us to add fields like `sku_zone` or `cart_items` in the future without modifying the Pydantic root model or database schema.

## Decision 3: API Architecture — FastAPI + SQLite

### Options Considered
1. FastAPI + PostgreSQL + Kafka
2. FastAPI + SQLite + Redis (chosen)
3. Node.js + MongoDB

### What AI Suggested
The AI suggested PostgreSQL for "production readiness" and Kafka for ingestion streams.

### What I Chose & Why
I chose FastAPI + SQLite in WAL mode because:
- **Zero-config deployment**: `docker compose up` works instantly without waiting for a heavy database to initialize.
- **Throughput**: SQLite in WAL mode can easily handle thousands of inserts per second, far exceeding our target of ~50 events per store per second.
- **Complexity**: Operating Kafka clusters is overkill for a 40-store retail chain. We achieve the same real-time behavior using direct SQLite reads for historical metrics and Redis Streams for the live dashboard feed.
