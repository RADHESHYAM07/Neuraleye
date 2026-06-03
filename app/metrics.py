from datetime import datetime, timezone, timedelta
from collections import defaultdict
from .models import MetricsResponse
from .database import get_events_by_store, get_pos_transactions

def compute_metrics(store_id: str, date: str = 'today') -> MetricsResponse:
    events = get_events_by_store(store_id, exclude_staff=True)
    
    unique_visitors = set()
    queue_joins = 0
    queue_abandons = 0
    dwell_times = defaultdict(list)
    billing_entries = {}
    
    for e in events:
        if e['event_type'] == 'ENTRY':
            unique_visitors.add(e['visitor_id'])
        elif e['event_type'] == 'BILLING_QUEUE_JOIN':
            queue_joins += 1
            billing_entries[e['visitor_id']] = datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))
        elif e['event_type'] == 'BILLING_QUEUE_ABANDON':
            queue_abandons += 1
        elif e['event_type'] in ('ZONE_DWELL', 'ZONE_EXIT'):
            if e['zone_id'] and e['dwell_ms'] > 0:
                dwell_times[e['zone_id']].append(e['dwell_ms'])
        elif e['event_type'] == 'ZONE_ENTER' and e['zone_id'] == 'BILLING':
            billing_entries[e['visitor_id']] = datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))

    avg_dwell = {}
    for zone, times in dwell_times.items():
        if times:
            avg_dwell[zone] = sum(times) / len(times)
            
    transactions = get_pos_transactions(store_id)
    purchasers = set()
    
    for txn in transactions:
        txn_time = datetime.fromisoformat(txn['timestamp'].replace('Z', '+00:00'))
        for visitor_id, entry_time in billing_entries.items():
            if entry_time <= txn_time <= entry_time + timedelta(minutes=5):
                purchasers.add(visitor_id)
                
    conversion_rate = len(purchasers) / len(unique_visitors) if unique_visitors else 0.0
    abandonment_rate = queue_abandons / queue_joins if queue_joins > 0 else 0.0
    current_queue = max(0, queue_joins - queue_abandons - len(purchasers))
    
    return MetricsResponse(
        store_id=store_id, period=date, unique_visitors=len(unique_visitors),
        conversion_rate=conversion_rate, avg_dwell_by_zone=avg_dwell,
        current_queue_depth=current_queue, abandonment_rate=abandonment_rate
    )
