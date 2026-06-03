#!/bin/bash
# Process all CCTV clips and feed events to the API
# Usage: ./pipeline/run.sh [API_URL]
API_URL=${1:-http://localhost:8000}
echo "Processing CCTV clips → $API_URL"

# Store 1 cameras
python pipeline/detect.py --video data/video/store1/cam_entry.mp4 --store-id STORE_BLR_001 --camera-id CAM_ENTRY_01 --output api --api-url $API_URL
python pipeline/detect.py --video data/video/store1/cam_floor.mp4 --store-id STORE_BLR_001 --camera-id CAM_FLOOR_01 --output api --api-url $API_URL
python pipeline/detect.py --video data/video/store1/cam_billing.mp4 --store-id STORE_BLR_001 --camera-id CAM_BILLING_01 --output api --api-url $API_URL

# Store 2 cameras
python pipeline/detect.py --video data/video/store2/cam_entry.mp4 --store-id STORE_BLR_002 --camera-id CAM_ENTRY_01 --output api --api-url $API_URL
python pipeline/detect.py --video data/video/store2/cam_floor.mp4 --store-id STORE_BLR_002 --camera-id CAM_FLOOR_01 --output api --api-url $API_URL
python pipeline/detect.py --video data/video/store2/cam_billing.mp4 --store-id STORE_BLR_002 --camera-id CAM_BILLING_01 --output api --api-url $API_URL

echo "Pipeline complete. Events ingested to $API_URL"
