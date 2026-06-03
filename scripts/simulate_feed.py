import time
import uuid
import random
import argparse
import requests
from datetime import datetime, timezone, timedelta

ZONES = ["SKINCARE", "HAIRCARE", "BEAUTY", "MOISTURISER", "FLOOR"]

def generate_session(store_id: str, start_time: datetime, is_staff: bool = False, is_reentry: bool = False):
    visitor_id = f"VIS_{uuid.uuid4().hex[:6]}"
    events = []
    current_time = start_time
    
    events.append({
        "event_id": str(uuid.uuid4()), "store_id": store_id, "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id, "event_type": "REENTRY" if is_reentry else "ENTRY",
        "timestamp": current_time.isoformat(), "zone_id": None, "dwell_ms": 0,
        "is_staff": is_staff, "confidence": round(random.uniform(0.7, 0.99), 2),
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
    })
    
    num_zones = random.randint(1, 4) if not is_staff else 5
    visited = set()
    
    for _ in range(num_zones):
        zone = random.choice([z for z in ZONES if z not in visited] or ZONES)
        visited.add(zone)
        
        current_time += timedelta(seconds=random.randint(10, 60))
        events.append({
            "event_id": str(uuid.uuid4()), "store_id": store_id, "camera_id": "CAM_FLOOR_01",
            "visitor_id": visitor_id, "event_type": "ZONE_ENTER",
            "timestamp": current_time.isoformat(), "zone_id": zone, "dwell_ms": 0,
            "is_staff": is_staff, "confidence": round(random.uniform(0.7, 0.99), 2),
            "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
        })
        
        dwell_s = random.randint(30, 180)
        current_time += timedelta(seconds=dwell_s)
        
        events.append({
            "event_id": str(uuid.uuid4()), "store_id": store_id, "camera_id": "CAM_FLOOR_01",
            "visitor_id": visitor_id, "event_type": "ZONE_DWELL",
            "timestamp": current_time.isoformat(), "zone_id": zone, "dwell_ms": dwell_s * 1000,
            "is_staff": is_staff, "confidence": round(random.uniform(0.7, 0.99), 2),
            "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
        })
        
        events.append({
            "event_id": str(uuid.uuid4()), "store_id": store_id, "camera_id": "CAM_FLOOR_01",
            "visitor_id": visitor_id, "event_type": "ZONE_EXIT",
            "timestamp": current_time.isoformat(), "zone_id": zone, "dwell_ms": dwell_s * 1000,
            "is_staff": is_staff, "confidence": round(random.uniform(0.7, 0.99), 2),
            "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
        })

    if not is_staff and random.random() < 0.6:
        current_time += timedelta(seconds=random.randint(10, 30))
        queue_depth = random.randint(0, 5)
        events.append({
            "event_id": str(uuid.uuid4()), "store_id": store_id, "camera_id": "CAM_BILLING_01",
            "visitor_id": visitor_id, "event_type": "BILLING_QUEUE_JOIN",
            "timestamp": current_time.isoformat(), "zone_id": "BILLING", "dwell_ms": 0,
            "is_staff": False, "confidence": round(random.uniform(0.7, 0.99), 2),
            "metadata": {"queue_depth": queue_depth, "sku_zone": None, "session_seq": 1}
        })
        
        current_time += timedelta(seconds=random.randint(60, 300))
        if random.random() < 0.2:
            events.append({
                "event_id": str(uuid.uuid4()), "store_id": store_id, "camera_id": "CAM_BILLING_01",
                "visitor_id": visitor_id, "event_type": "BILLING_QUEUE_ABANDON",
                "timestamp": current_time.isoformat(), "zone_id": "BILLING", "dwell_ms": 0,
                "is_staff": False, "confidence": round(random.uniform(0.7, 0.99), 2),
                "metadata": {"queue_depth": queue_depth, "sku_zone": None, "session_seq": 1}
            })

    current_time += timedelta(seconds=random.randint(10, 30))
    events.append({
        "event_id": str(uuid.uuid4()), "store_id": store_id, "camera_id": "CAM_ENTRY_01",
        "visitor_id": visitor_id, "event_type": "EXIT",
        "timestamp": current_time.isoformat(), "zone_id": None, "dwell_ms": 0,
        "is_staff": is_staff, "confidence": round(random.uniform(0.7, 0.99), 2),
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
    })
    
    return events, current_time

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["batch", "realtime"], default="batch")
    parser.add_argument("--store-id", default="STORE_BLR_002")
    parser.add_argument("--api-url", default="http://localhost:8000")
    parser.add_argument("--num-visitors", type=int, default=50)
    args = parser.parse_args()
    
    all_events = []
    base_time = datetime.now(timezone.utc) - timedelta(hours=2)
    
    print(f"Generating {args.num_visitors} visitor sessions...")
    for i in range(args.num_visitors):
        is_staff = random.random() < 0.05
        is_reentry = random.random() < 0.1
        start = base_time + timedelta(minutes=random.randint(0, 120))
        evs, _ = generate_session(args.store_id, start, is_staff, is_reentry)
        all_events.extend(evs)
        
    all_events.sort(key=lambda x: x["timestamp"])
    
    if args.mode == "batch":
        for i in range(0, len(all_events), 100):
            batch = all_events[i:i+100]
            try:
                res = requests.post(f"{args.api_url}/events/ingest", json={"events": batch})
                print(f"Sent {len(batch)} events. Response: {res.status_code}")
            except Exception as e:
                print(f"Failed to send: {e}")
    else:
        for ev in all_events:
            ev["timestamp"] = datetime.now(timezone.utc).isoformat()
            try:
                requests.post(f"{args.api_url}/events/ingest", json={"events": [ev]})
                print(f"Sent event {ev['event_type']} for {ev['visitor_id']}")
            except Exception as e:
                print(f"Failed: {e}")
            time.sleep(0.5)

if __name__ == "__main__":
    main()
