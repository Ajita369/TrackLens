from fastapi import APIRouter, Depends, Query
from typing import Optional, Dict
from datetime import datetime, timezone
from app.models import MetricsResponse
from app.database import get_db
import sqlite3
import json

router = APIRouter()

@router.get("/stores/{store_id}/metrics", response_model=MetricsResponse)
def get_store_metrics(
    store_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to UTC today"),
    db: sqlite3.Connection = Depends(get_db)
):
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    # 1. Unique visitors (customers only)
    visitor_cursor = db.execute("""
        SELECT COUNT(DISTINCT visitor_id) as unique_visitors 
        FROM events 
        WHERE store_id = ? 
          AND event_type = 'ENTRY' 
          AND is_staff = 0 
          AND date(timestamp) = ?
    """, (store_id, date))
    row = visitor_cursor.fetchone()
    unique_visitors = row["unique_visitors"] if row else 0

    # 2. Avg dwell by zone (excluding staff)
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
    avg_dwell_by_zone = {}
    for r in dwell_cursor.fetchall():
        avg_dwell_by_zone[r["zone_id"]] = float(r["avg_dwell"]) if r["avg_dwell"] is not None else 0.0

    # 3. Current queue depth
    # Find the latest queue_depth from join events
    queue_cursor = db.execute("""
        SELECT metadata_json 
        FROM events 
        WHERE store_id = ? 
          AND event_type = 'BILLING_QUEUE_JOIN' 
          AND is_staff = 0
          AND date(timestamp) = ?
        ORDER BY timestamp_epoch DESC 
        LIMIT 1
    """, (store_id, date))
    queue_row = queue_cursor.fetchone()
    current_queue_depth = 0
    if queue_row:
        try:
            meta = json.loads(queue_row["metadata_json"])
            current_queue_depth = meta.get("queue_depth", 0) or 0
        except Exception:
            current_queue_depth = 0

    # 4. Abandonment rate (excluding staff)
    abandon_cursor = db.execute("""
        SELECT 
            SUM(CASE WHEN event_type = 'BILLING_QUEUE_ABANDON' THEN 1 ELSE 0 END) as abandon_count,
            SUM(CASE WHEN event_type = 'BILLING_QUEUE_JOIN' THEN 1 ELSE 0 END) as join_count
        FROM events 
        WHERE store_id = ? 
          AND is_staff = 0
          AND date(timestamp) = ?
    """, (store_id, date))
    abandon_row = abandon_cursor.fetchone()
    abandonment_rate = 0.0
    if abandon_row:
        abandon_count = abandon_row["abandon_count"] or 0
        join_count = abandon_row["join_count"] or 0
        if join_count > 0:
            abandonment_rate = float(abandon_count) / float(join_count)

    # 5. Conversion rate: correlated billing joins with POS transactions (time window)
    conversion_rate = 0.0
    if unique_visitors > 0:
        conversion_cursor = db.execute("""
            SELECT COUNT(DISTINCT e.visitor_id) as converted_visitors
            FROM events e
            JOIN pos_transactions p 
              ON p.store_id = e.store_id
              AND p.timestamp_epoch BETWEEN e.timestamp_epoch AND (e.timestamp_epoch + 300000)
            WHERE e.store_id = ?
              AND e.event_type = 'BILLING_QUEUE_JOIN'
              AND e.is_staff = 0
              AND date(e.timestamp) = ?
        """, (store_id, date))
        conv_row = conversion_cursor.fetchone()
        converted_visitors = conv_row["converted_visitors"] if conv_row else 0
        conversion_rate = float(converted_visitors) / float(unique_visitors)

    data_window = {
        "start": f"{date}T00:00:00Z",
        "end": f"{date}T23:59:59Z"
    }

    return MetricsResponse(
        store_id=store_id,
        unique_visitors=unique_visitors,
        conversion_rate=conversion_rate,
        avg_dwell_by_zone=avg_dwell_by_zone,
        current_queue_depth=current_queue_depth,
        abandonment_rate=abandonment_rate,
        data_window=data_window
    )
