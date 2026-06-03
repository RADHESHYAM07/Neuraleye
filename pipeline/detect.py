import argparse
import sys
import json
import os

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True)
    parser.add_argument("--store-id", required=True)
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--output", choices=["api", "jsonl"], default="api")
    parser.add_argument("--api-url", default="http://localhost:8000")
    args = parser.parse_args()

    print(f"[Detect] Processing {args.video} for {args.store_id} / {args.camera_id}")
    print("[Detect] Note: Full YOLOv8n inference requires torch/CUDA which may not be available.")
    print("[Detect] For testing the API, please use scripts/simulate_feed.py to generate rich synthetic data.")

if __name__ == "__main__":
    main()
