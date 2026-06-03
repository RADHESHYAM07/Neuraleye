import requests
import time

def emit_events(events, api_url):
    try:
        res = requests.post(f"{api_url}/events/ingest", json={"events": events})
        return res.status_code == 200
    except Exception as e:
        print(f"Failed to emit events: {e}")
        return False
