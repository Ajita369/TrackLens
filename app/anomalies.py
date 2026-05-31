from fastapi import APIRouter, Depends, Query
from datetime import datetime, timedelta, timezone
from typing import Optional, List
import sqlite3
import json
import numpy as np
from app.models import AnomalyResponse, Anomaly
from app.database import get_db

router = APIRouter()

@router.get("/stores/{store_id}/anomalies", response_model=AnomalyResponse)
def get_store_anomalies(
    store_id: str,
    date: Optional[str] = Query(None, description="Date in YYYY-MM-DD format, defaults to UTC today"),
    db: sqlite3.Connection = Depends(get_db)
):
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        
    anomalies = []
    now = datetime.now(timezone.utc)
    
    # 1. QUEUE_SPIKE Check (CRITICAL)
    # Find latest queue depth
    queue_cursor = db.execute("""
        SELECT metadata_json, timestamp_epoch 
        FROM events 
        WHERE store_id = ? 
          AND event_type = 'BILLING_QUEUE_JOIN' 
          AND is_staff = 0
          AND date(timestamp) = ?
        ORDER BY timestamp_epoch DESC 
        LIMIT 1
    """, (store_id, date))
    queue_row = queue_cursor.fetchone()
    
    if queue_row:
        try:
            meta = json.loads(queue_row["metadata_json"])
            current_q = meta.get("queue_depth", 0) or 0
            
            # Query historical average queue depth (all time for this store)
            hist_cursor = db.execute("""
                SELECT metadata_json 
                FROM events 
                WHERE store_id = ? 
                  AND event_type = 'BILLING_QUEUE_JOIN' 
                  AND is_staff = 0
            """, (store_id,))
            
            depths = []
            for r in hist_cursor.fetchall():
                try:
                    m = json.loads(r["metadata_json"])
                    d_val = m.get("queue_depth")
                    if d_val is not None:
                        depths.append(d_val)
                except Exception:
                    pass
                    
            avg_q = np.mean(depths) if depths else 1.0
            
            # Trigger if current is 2x average and current depth is significant (> 2)
            if current_q > 2 * avg_q and current_q > 2:
                anomalies.append(Anomaly(
                    type="QUEUE_SPIKE",
                    severity="CRITICAL",
                    details=f"Checkout queue depth spike detected: currently {current_q} people (historical average: {avg_q:.1f}).",
                    detected_at=datetime.fromtimestamp(queue_row["timestamp_epoch"] / 1000.0, tz=timezone.utc),
                    suggested_action="Open additional billing counter or deploy floor staff to manage queue."
                ))
        except Exception:
            pass

    # 2. CONVERSION_DROP Check (WARN)
    # Today's conversion rate
    visitor_cursor = db.execute("""
        SELECT COUNT(DISTINCT visitor_id) as unique_visitors 
        FROM events 
        WHERE store_id = ? 
          AND event_type = 'ENTRY' 
          AND is_staff = 0 
          AND date(timestamp) = ?
    """, (store_id, date))
    v_row = visitor_cursor.fetchone()
    today_visitors = v_row["unique_visitors"] if v_row else 0
    
    today_conv = 0.0
    if today_visitors > 0:
        conv_cursor = db.execute("""
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
        conv_row = conv_cursor.fetchone()
        converted_visitors = conv_row["converted_visitors"] if conv_row else 0
        today_conv = float(converted_visitors) / float(today_visitors)
        
        # Calculate historical conversion rates by date (excluding today)
        hist_cursor = db.execute("""
            SELECT date(timestamp) as dt, COUNT(DISTINCT visitor_id) as unique_v
            FROM events
            WHERE store_id = ? 
              AND event_type = 'ENTRY' 
              AND is_staff = 0 
              AND date(timestamp) != ?
            GROUP BY date(timestamp)
        """, (store_id, date))
        
        daily_convs = []
        for r in hist_cursor.fetchall():
            dt = r["dt"]
            u_v = r["unique_v"]
            if u_v > 0:
                c_cursor = db.execute("""
                    SELECT COUNT(DISTINCT e.visitor_id) as converted_v
                    FROM events e
                    JOIN pos_transactions p 
                      ON p.store_id = e.store_id
                      AND p.timestamp_epoch BETWEEN e.timestamp_epoch AND (e.timestamp_epoch + 300000)
                    WHERE e.store_id = ?
                      AND e.event_type = 'BILLING_QUEUE_JOIN'
                      AND e.is_staff = 0
                      AND date(e.timestamp) = ?
                """, (store_id, dt))
                c_row = c_cursor.fetchone()
                c_v = c_row["converted_v"] if c_row else 0
                daily_convs.append(float(c_v) / float(u_v))
                
        if len(daily_convs) >= 3:
            mean_conv = np.mean(daily_convs)
            std_conv = np.std(daily_convs)
            
            # Anomaly trigger: today's conversion is lower than average by 1.5 standard deviations
            if today_conv < (mean_conv - 1.5 * std_conv):
                anomalies.append(Anomaly(
                    type="CONVERSION_DROP",
                    severity="WARN",
                    details=f"Conversion rate drop detected: today's rate {today_conv:.1%} is significantly below historical average ({mean_conv:.1%}).",
                    detected_at=now,
                    suggested_action="Review in-store promotions and staff engagement on floor."
                ))
        elif today_conv < 0.05 and today_visitors >= 10:
            # Fallback if insufficient historical dates: static warning for low conversion (< 5%)
            anomalies.append(Anomaly(
                type="CONVERSION_DROP",
                severity="WARN",
                details=f"Conversion rate warning: today's conversion is low at {today_conv:.1%} (visitors: {today_visitors}).",
                detected_at=now,
                suggested_action="Review in-store promotions and staff engagement on floor."
            ))

    # 3. DEAD_ZONE Check (INFO)
    # Find the maximum timestamp in the database for this store to determine simulation "now"
    max_time_cursor = db.execute("SELECT MAX(timestamp_epoch) as max_epoch FROM events WHERE store_id = ?", (store_id,))
    max_row = max_time_cursor.fetchone()
    
    if max_row and max_row["max_epoch"] is not None:
        sim_now_epoch = max_row["max_epoch"]
        thirty_min_ago_epoch = sim_now_epoch - 1800000  # 30 min in ms
        
        # Get list of all known zones that have ever been entered in this store
        all_zones_cursor = db.execute("""
            SELECT DISTINCT zone_id 
            FROM events 
            WHERE store_id = ? 
              AND zone_id IS NOT NULL
        """, (store_id,))
        known_zones = [r["zone_id"] for r in all_zones_cursor.fetchall()]
        
        # Get zones with active visits in the last 30 minutes
        active_zones_cursor = db.execute("""
            SELECT DISTINCT zone_id 
            FROM events 
            WHERE store_id = ? 
              AND event_type = 'ZONE_ENTER' 
              AND zone_id IS NOT NULL 
              AND timestamp_epoch BETWEEN ? AND ?
        """, (store_id, thirty_min_ago_epoch, sim_now_epoch))
        active_zones = {r["zone_id"] for r in active_zones_cursor.fetchall()}
        
        # If there are active visits in the store during this window, find dead zones
        if active_zones:
            dead_zones = set(known_zones) - active_zones
            for dz in dead_zones:
                anomalies.append(Anomaly(
                    type="DEAD_ZONE",
                    severity="INFO",
                    details=f"Zone '{dz}' has detected zero customer entries in the last 30 minutes.",
                    detected_at=datetime.fromtimestamp(sim_now_epoch / 1000.0, tz=timezone.utc),
                    suggested_action=f"Check if zone display for '{dz}' is accessible and properly merchandised."
                ))
                
    return AnomalyResponse(store_id=store_id, anomalies=anomalies)
