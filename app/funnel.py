from fastapi import APIRouter, Depends, Query
from typing import Optional, List
from datetime import datetime, timezone
from app.models import FunnelResponse, FunnelStage
from app.database import get_db
import sqlite3

router = APIRouter()

@router.get("/stores/{store_id}/funnel", response_model=FunnelResponse)
def get_store_funnel(
    store_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to UTC today"),
    db: sqlite3.Connection = Depends(get_db)
):
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    # 1. Entry count (Unique customer sessions)
    entry_cursor = db.execute("""
        SELECT COUNT(DISTINCT visitor_id) as cnt 
        FROM events 
        WHERE store_id = ? 
          AND event_type IN ('ENTRY', 'REENTRY') 
          AND is_staff = 0 
          AND date(timestamp) = ?
    """, (store_id, date))
    entry_count = entry_cursor.fetchone()["cnt"] or 0
    
    # 2. Zone Visit count (Customers who browsed any zone)
    zone_cursor = db.execute("""
        SELECT COUNT(DISTINCT visitor_id) as cnt 
        FROM events 
        WHERE store_id = ? 
          AND event_type IN ('ZONE_ENTER', 'ZONE_DWELL', 'ZONE_EXIT') 
          AND is_staff = 0 
          AND date(timestamp) = ?
          AND visitor_id IN (
              SELECT DISTINCT visitor_id 
              FROM events 
              WHERE store_id = ? 
                AND event_type IN ('ENTRY', 'REENTRY') 
                AND is_staff = 0 
                AND date(timestamp) = ?
          )
    """, (store_id, date, store_id, date))
    zone_count = zone_cursor.fetchone()["cnt"] or 0
    
    # 3. Billing Queue count (Customers who joined checkout queue)
    queue_cursor = db.execute("""
        SELECT COUNT(DISTINCT visitor_id) as cnt 
        FROM events 
        WHERE store_id = ? 
          AND event_type = 'BILLING_QUEUE_JOIN' 
          AND is_staff = 0 
          AND date(timestamp) = ?
          AND visitor_id IN (
              SELECT DISTINCT visitor_id 
              FROM events 
              WHERE store_id = ? 
                AND event_type IN ('ENTRY', 'REENTRY') 
                AND is_staff = 0 
                AND date(timestamp) = ?
          )
    """, (store_id, date, store_id, date))
    queue_count = queue_cursor.fetchone()["cnt"] or 0
    
    # 4. Purchase count (Correlated checkout sessions)
    purchase_cursor = db.execute("""
        SELECT COUNT(DISTINCT e.visitor_id) as cnt
        FROM events e
        JOIN pos_transactions p 
          ON p.store_id = e.store_id
          AND p.timestamp_epoch BETWEEN e.timestamp_epoch AND (e.timestamp_epoch + 300000)
        WHERE e.store_id = ?
          AND e.event_type = 'BILLING_QUEUE_JOIN'
          AND e.is_staff = 0
          AND date(e.timestamp) = ?
    """, (store_id, date))
    purchase_count = purchase_cursor.fetchone()["cnt"] or 0
    
    # Calculate drop-off percentages
    drop_off_1 = 0.0
    
    drop_off_2 = 0.0
    if entry_count > 0:
        drop_off_2 = ((entry_count - zone_count) / entry_count) * 100.0
        
    drop_off_3 = 0.0
    if zone_count > 0:
        drop_off_3 = ((zone_count - queue_count) / zone_count) * 100.0
        
    drop_off_4 = 0.0
    if queue_count > 0:
        drop_off_4 = ((queue_count - purchase_count) / queue_count) * 100.0
        
    stages = [
        FunnelStage(name="Entry", count=entry_count, drop_off_pct=round(drop_off_1, 2)),
        FunnelStage(name="Zone Visit", count=zone_count, drop_off_pct=round(drop_off_2, 2)),
        FunnelStage(name="Billing Queue", count=queue_count, drop_off_pct=round(drop_off_3, 2)),
        FunnelStage(name="Purchase", count=purchase_count, drop_off_pct=round(drop_off_4, 2))
    ]
    
    return FunnelResponse(store_id=store_id, stages=stages)
