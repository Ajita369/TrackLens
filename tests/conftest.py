import pytest
import sqlite3
import uuid
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from typing import Generator, List, Dict, Any

from app.main import app
from app.database import get_db

@pytest.fixture
def db() -> Generator[sqlite3.Connection, None, None]:
    """
    Creates an in-memory SQLite database connection and sets up tables and indexes.
    Connection is kept open for the duration of the test.
    """
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;") # WAL will fail on :memory: sometimes, but memory is fine
    conn.execute("PRAGMA foreign_keys=ON;")
    
    # Create tables
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            event_id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            camera_id TEXT NOT NULL,
            visitor_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            timestamp_epoch INTEGER NOT NULL,
            zone_id TEXT,
            dwell_ms INTEGER,
            is_staff INTEGER NOT NULL DEFAULT 0,
            confidence REAL NOT NULL,
            metadata_json TEXT NOT NULL,
            ingested_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );
    """)
    
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pos_transactions (
            transaction_id TEXT PRIMARY KEY,
            store_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            timestamp_epoch INTEGER NOT NULL,
            basket_value_inr REAL NOT NULL,
            ingested_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
        );
    """)
    
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_store_time ON events (store_id, timestamp_epoch);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_store_visitor ON events (store_id, visitor_id);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_store_type ON events (store_id, event_type);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_store_time ON pos_transactions (store_id, timestamp_epoch);")
    
    conn.commit()
    yield conn
    conn.close()

@pytest.fixture
def test_client(db: sqlite3.Connection) -> Generator[TestClient, None, None]:
    """
    FastAPI TestClient with overridden get_db dependency to point to the in-memory DB.
    """
    def override_get_db():
        yield db
        
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()

@pytest.fixture
def sample_events() -> List[Dict[str, Any]]:
    """
    Returns 10 valid event dicts covering all event types.
    """
    store_id = "ST1008"
    base_time = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    visitor_id = "VIS_ST1008_20260410_0001"
    
    event_types = [
        ("ENTRY", "CAM 3", None, None),
        ("ZONE_ENTER", "CAM 1", "Lakme", None),
        ("ZONE_DWELL", "CAM 1", "Lakme", 30000),
        ("ZONE_EXIT", "CAM 1", "Lakme", None),
        ("ZONE_ENTER", "CAM 2", "Minimalist", None),
        ("ZONE_EXIT", "CAM 2", "Minimalist", None),
        ("ZONE_ENTER", "CAM 5", "Cash Counter", None),
        ("BILLING_QUEUE_JOIN", "CAM 5", "Cash Counter", None),
        ("BILLING_QUEUE_ABANDON", "CAM 5", "Cash Counter", None),
        ("EXIT", "CAM 3", None, None)
    ]
    
    evts = []
    for idx, (etype, cam, zone, dwell) in enumerate(event_types):
        evt_time = base_time + timedelta(seconds=idx * 15)
        evt_str = evt_time.isoformat().replace("+00:00", "Z")
        
        q_depth = 2 if etype == "BILLING_QUEUE_JOIN" else None
        sku = "makeup" if zone == "Lakme" else ("skin" if zone == "Minimalist" else ("billing" if zone == "Cash Counter" else None))
        
        evts.append({
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": cam,
            "visitor_id": visitor_id,
            "event_type": etype,
            "timestamp": evt_str,
            "zone_id": zone,
            "dwell_ms": dwell,
            "is_staff": False,
            "confidence": 0.95,
            "metadata": {
                "queue_depth": q_depth,
                "sku_zone": sku,
                "session_seq": idx + 1
            }
        })
    return evts

@pytest.fixture
def empty_store_events() -> List[Dict[str, Any]]:
    return []

@pytest.fixture
def staff_only_events() -> List[Dict[str, Any]]:
    """
    Returns 5 events all with is_staff=true.
    """
    store_id = "ST1008"
    base_time = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    visitor_id = "STAFF_01"
    
    types = [
        ("ENTRY", "CAM 3", None, None),
        ("ZONE_ENTER", "CAM 1", "Lakme", None),
        ("ZONE_DWELL", "CAM 1", "Lakme", 30000),
        ("ZONE_EXIT", "CAM 1", "Lakme", None),
        ("EXIT", "CAM 3", None, None)
    ]
    
    evts = []
    for idx, (etype, cam, zone, dwell) in enumerate(types):
        evt_time = base_time + timedelta(seconds=idx * 30)
        evt_str = evt_time.isoformat().replace("+00:00", "Z")
        evts.append({
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": cam,
            "visitor_id": visitor_id,
            "event_type": etype,
            "timestamp": evt_str,
            "zone_id": zone,
            "dwell_ms": dwell,
            "is_staff": True,
            "confidence": 0.99,
            "metadata": {
                "queue_depth": None,
                "sku_zone": "makeup" if zone else None,
                "session_seq": idx + 1
            }
        })
    return evts

@pytest.fixture
def reentry_visitor_events() -> List[Dict[str, Any]]:
    """
    Returns events for one visitor entering, exiting, re-entering, and exiting.
    """
    store_id = "ST1008"
    base_time = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    visitor_id = "VIS_REENTRY_01"
    
    # 1. Entry 1
    # 2. Zone visit
    # 3. Zone exit
    # 4. Exit 1
    # 5. Reentry
    # 6. Zone visit
    # 7. Exit 2
    types = [
        ("ENTRY", "CAM 3", None, None, 1),
        ("ZONE_ENTER", "CAM 1", "Lakme", None, 2),
        ("ZONE_EXIT", "CAM 1", "Lakme", None, 3),
        ("EXIT", "CAM 3", None, None, 4),
        ("REENTRY", "CAM 3", None, None, 5),
        ("ZONE_ENTER", "CAM 1", "Lakme", None, 6),
        ("EXIT", "CAM 3", None, None, 7)
    ]
    
    evts = []
    for idx, (etype, cam, zone, dwell, seq) in enumerate(types):
        # 1 hour gap between exits and re-entries
        gap = 3600 if idx >= 4 else 0
        evt_time = base_time + timedelta(seconds=idx * 10 + gap)
        evt_str = evt_time.isoformat().replace("+00:00", "Z")
        
        evts.append({
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": cam,
            "visitor_id": visitor_id,
            "event_type": etype,
            "timestamp": evt_str,
            "zone_id": zone,
            "dwell_ms": dwell,
            "is_staff": False,
            "confidence": 0.95,
            "metadata": {
                "queue_depth": None,
                "sku_zone": "makeup" if zone else None,
                "session_seq": seq
            }
        })
    return evts

@pytest.fixture
def queue_abandon_events() -> List[Dict[str, Any]]:
    """
    Returns events for a visitor joining and abandoning the queue.
    """
    store_id = "ST1008"
    base_time = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    visitor_id = "VIS_ABANDON_01"
    
    types = [
        ("ENTRY", "CAM 3", None, None),
        ("ZONE_ENTER", "CAM 5", "Cash Counter", None),
        ("BILLING_QUEUE_JOIN", "CAM 5", "Cash Counter", None),
        ("ZONE_EXIT", "CAM 5", "Cash Counter", None),
        ("BILLING_QUEUE_ABANDON", "CAM 5", "Cash Counter", None),
        ("EXIT", "CAM 3", None, None)
    ]
    
    evts = []
    for idx, (etype, cam, zone, dwell) in enumerate(types):
        evt_time = base_time + timedelta(seconds=idx * 20)
        evt_str = evt_time.isoformat().replace("+00:00", "Z")
        
        evts.append({
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": cam,
            "visitor_id": visitor_id,
            "event_type": etype,
            "timestamp": evt_str,
            "zone_id": zone,
            "dwell_ms": dwell,
            "is_staff": False,
            "confidence": 0.95,
            "metadata": {
                "queue_depth": 3 if etype == "BILLING_QUEUE_JOIN" else None,
                "sku_zone": "billing" if zone else None,
                "session_seq": idx + 1
            }
        })
    return evts
