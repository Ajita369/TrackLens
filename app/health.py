from fastapi import APIRouter, Depends
from datetime import datetime, timezone
from app.models import HealthResponse, StoreHealth
from app.database import get_db
import sqlite3

router = APIRouter()

# Track start time for uptime calculation
START_TIME = datetime.now(timezone.utc)
VERSION = "1.0.0"

@router.get("/health", response_model=HealthResponse)
def get_health(db: sqlite3.Connection = Depends(get_db)):
    status = "healthy"
    stores = {}
    
    try:
        # Check database connectivity
        db.execute("SELECT 1")
    except Exception as e:
        return HealthResponse(
            status="unhealthy",
            stores={},
            uptime_seconds=(datetime.now(timezone.utc) - START_TIME).total_seconds(),
            version=VERSION
        )

    now = datetime.now(timezone.utc)
    
    try:
        # Query last event timestamp and total count per store
        cursor = db.execute("""
            SELECT store_id, MAX(timestamp) as last_event_time, COUNT(*) as event_cnt 
            FROM events 
            GROUP BY store_id
        """)
        
        for row in cursor.fetchall():
            store_id = row["store_id"]
            last_event_str = row["last_event_time"]
            event_cnt = row["event_cnt"]
            
            last_event_dt = None
            feed_status = "STALE_FEED"
            
            if last_event_str:
                try:
                    # Remove 'Z' or offset if needed for parsing, or use fromisoformat
                    # datetime.fromisoformat handles ISO-8601 strings in Python 3.11+
                    # replace Z with +00:00
                    clean_str = last_event_str.replace("Z", "+00:00")
                    last_event_dt = datetime.fromisoformat(clean_str)
                    
                    # Check if last event is within 10 minutes of current time
                    time_diff = (now - last_event_dt).total_seconds()
                    if time_diff >= 0 and time_diff <= 600:
                        feed_status = "LIVE"
                    else:
                        feed_status = "STALE_FEED"
                except Exception:
                    feed_status = "STALE_FEED"
                    
            if feed_status == "STALE_FEED":
                status = "degraded"
                
            stores[store_id] = StoreHealth(
                last_event_at=last_event_dt,
                feed_status=feed_status,
                event_count=event_cnt
            )
            
    except Exception as e:
        status = "degraded"

    uptime_seconds = (now - START_TIME).total_seconds()
    
    return HealthResponse(
        status=status,
        stores=stores,
        uptime_seconds=uptime_seconds,
        version=VERSION
    )
