from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone
from app.models import HeatmapResponse, HeatmapZone
from app.database import get_db
import sqlite3

router = APIRouter()

@router.get("/stores/{store_id}/heatmap", response_model=HeatmapResponse)
def get_store_heatmap(
    store_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to UTC today"),
    db: sqlite3.Connection = Depends(get_db)
):
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    # Query visit counts and session counts (distinct visitor_ids) per zone
    visits_cursor = db.execute("""
        SELECT 
            zone_id, 
            COUNT(*) as visit_count, 
            COUNT(DISTINCT visitor_id) as session_count
        FROM events 
        WHERE store_id = ? 
          AND event_type = 'ZONE_ENTER' 
          AND is_staff = 0 
          AND zone_id IS NOT NULL
          AND date(timestamp) = ?
        GROUP BY zone_id
    """, (store_id, date))
    
    visits_data = {r["zone_id"]: {"visit_count": r["visit_count"], "session_count": r["session_count"]} 
                   for r in visits_cursor.fetchall()}
                   
    # Query average dwell times per zone
    dwell_cursor = db.execute("""
        SELECT zone_id, AVG(dwell_ms) as avg_dwell 
        FROM events 
        WHERE store_id = ? 
          AND event_type = 'ZONE_DWELL' 
          AND is_staff = 0 
          AND zone_id IS NOT NULL
          AND date(timestamp) = ?
        GROUP BY zone_id
    """, (store_id, date))
    
    dwell_data = {r["zone_id"]: float(r["avg_dwell"]) if r["avg_dwell"] is not None else 0.0 
                  for r in dwell_cursor.fetchall()}
                  
    # All zones that have either a visit or a dwell
    all_zones = set(visits_data.keys()) | set(dwell_data.keys())
    
    # Calculate max visit count for normalization
    max_visits = max([info["visit_count"] for info in visits_data.values()] or [0])
    
    zones = []
    for zone_id in all_zones:
        visit_info = visits_data.get(zone_id, {"visit_count": 0, "session_count": 0})
        v_count = visit_info["visit_count"]
        s_count = visit_info["session_count"]
        avg_dwell = dwell_data.get(zone_id, 0.0)
        
        # Normalize score between 0 and 100
        normalized = int((v_count / max_visits) * 100) if max_visits > 0 else 0
        
        # Low confidence if fewer than 20 distinct visitor sessions in the window
        confidence = "high" if s_count >= 20 else "low"
        
        zones.append(HeatmapZone(
            zone_id=zone_id,
            visit_count=v_count,
            avg_dwell_ms=round(avg_dwell, 1),
            normalized_score=normalized,
            data_confidence=confidence
        ))
        
    # Sort zones by visit count descending
    zones.sort(key=lambda x: x.visit_count, reverse=True)
    
    return HeatmapResponse(store_id=store_id, zones=zones)
