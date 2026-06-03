from .models import FunnelResponse, FunnelStage
from .database import get_events_by_store, get_pos_transactions
from datetime import datetime, timedelta

def compute_funnel(store_id: str, date: str = 'today') -> FunnelResponse:
    events = get_events_by_store(store_id, exclude_staff=True)
    
    entry_visitors = set()
    zone_visitors = set()
    billing_visitors = set()
    billing_times = {}
    
    for e in events:
        vid = e['visitor_id']
        if e['event_type'] in ('ENTRY', 'REENTRY'):
            entry_visitors.add(vid)
        elif e['event_type'] == 'ZONE_ENTER':
            zone_visitors.add(vid)
            if e['zone_id'] == 'BILLING':
                billing_visitors.add(vid)
                billing_times[vid] = datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))
        elif e['event_type'] == 'BILLING_QUEUE_JOIN':
            billing_visitors.add(vid)
            billing_times[vid] = datetime.fromisoformat(e['timestamp'].replace('Z', '+00:00'))
            
    transactions = get_pos_transactions(store_id)
    purchasers = set()
    for txn in transactions:
        txn_time = datetime.fromisoformat(txn['timestamp'].replace('Z', '+00:00'))
        for visitor_id, entry_time in billing_times.items():
            if entry_time <= txn_time <= entry_time + timedelta(minutes=5):
                purchasers.add(visitor_id)
                
    stages_data = [
        ("Entry", len(entry_visitors)),
        ("Zone Visit", len(zone_visitors)),
        ("Billing Queue", len(billing_visitors)),
        ("Purchase", len(purchasers))
    ]
    
    stages = []
    prev_count = 0
    for i, (name, count) in enumerate(stages_data):
        drop_pct = (prev_count - count) / prev_count * 100 if i > 0 and prev_count > 0 else 0.0
        stages.append(FunnelStage(stage=name, visitors=count, drop_off_pct=drop_pct))
        prev_count = count
        
    return FunnelResponse(store_id=store_id, period=date, stages=stages)
