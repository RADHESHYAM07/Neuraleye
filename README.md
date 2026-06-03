# 🧠 NeuralEye — Store Intelligence API

Real-time store analytics from CCTV footage. Converts raw video into actionable business intelligence: visitor counting, conversion funnels, zone heatmaps, and anomaly detection.

## Quick Start (3 commands)

```bash
docker compose up --build -d
# API live at http://localhost:8000 | Dashboard at http://localhost:3000
```

## Run Simulation

You can test the system without GPU/CCTV using our simulator:
```bash
# Start sending real-time synthetic events to the API
pip install requests
python scripts/simulate_feed.py --mode realtime --store-id STORE_BLR_002
```

## Running the Actual Pipeline (Local)
To process the provided CCTV MP4 files:
```bash
pip install -r pipeline/requirements.txt
python pipeline/detect.py --video data/video/store2/cam_entry.mp4 --store-id STORE_BLR_002 --camera-id CAM_ENTRY_01 --output api
```

## API Endpoints

- `POST /events/ingest`
- `GET /stores/{store_id}/metrics`
- `GET /stores/{store_id}/funnel`
- `GET /stores/{store_id}/heatmap`
- `GET /stores/{store_id}/anomalies`
- `GET /health`

## Documentation
- `DESIGN.md` - System Architecture and design
- `CHOICES.md` - Technical choices and AI decisions
