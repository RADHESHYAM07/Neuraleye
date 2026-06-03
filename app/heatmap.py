from collections import defaultdict
from .models import HeatmapResponse, HeatmapZone
from .database import get_events_by_store

def compute_heatmap(store_id: str, date: str = 'today') -> HeatmapResponse:
    events = get_events_by_store(store_id)
    zone_visits = defaultdict(set)
    dwell_times = defaultdict(list)
    
    for e in events:
        if not e['zone_id']: continue
        if e['event_type'] == 'ZONE_ENTER':
            zone_visits[e['zone_id']].add(e['visitor_id'])
        elif e['event_type'] in ('ZONE_DWELL', 'ZONE_EXIT') and e['dwell_ms'] > 0:
            dwell_times[e['zone_id']].append(e['dwell_ms'])
                
    zones_list = []
    max_visits = max([len(v) for v in zone_visits.values()] + [1])
    
    for zone_id, visitors in zone_visits.items():
        v_count = len(visitors)
        intensity = int((v_count / max_visits) * 100)
        times = dwell_times.get(zone_id, [])
        avg_dwell = sum(times) / len(times) if times else 0
        data_conf = 'LOW' if v_count < 20 else None
        
        zones_list.append(HeatmapZone(
            zone_id=zone_id, visit_count=v_count, avg_dwell_ms=avg_dwell,
            intensity=intensity, data_confidence=data_conf
        ))
        
    return HeatmapResponse(store_id=store_id, period=date, zones=zones_list)
