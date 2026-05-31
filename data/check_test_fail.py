from fastapi.testclient import TestClient
import sqlite3
import json

from app.main import app
from app.database import get_db

# Create in-memory DB
conn = sqlite3.connect(":memory:", check_same_thread=False)
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
        metadata_json TEXT NOT NULL
    );
""")
conn.commit()

def override_get_db():
    yield conn

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

# Create 3 events
events = [
    {
        "event_id": "ee7d1012-6db8-406a-81d7-783f5befdd38",
        "store_id": "ST1008",
        "camera_id": "CAM 1",
        "visitor_id": "V1",
        "event_type": "ENTRY",
        "timestamp": "2026-04-10T10:00:15Z",
        "zone_id": None,
        "dwell_ms": None,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {"queue_depth": None, "sku_zone": None, "session_seq": 1}
    },
    {
        "event_id": "ee7d1012-6db8-406a-81d7-783f5befdd39",
        "store_id": "ST1008",
        "camera_id": "CAM 1",
        "visitor_id": "V1",
        "event_type": "ZONE_DWELL",
        "timestamp": "2026-04-10T10:00:45Z",
        "zone_id": "Lakme",
        "dwell_ms": 30000,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {"queue_depth": None, "sku_zone": "makeup", "session_seq": 2}
    },
    {
        "event_id": "ee7d1012-6db8-406a-81d7-783f5befdd40",
        "store_id": "ST1008",
        "camera_id": "CAM 1",
        "visitor_id": "V1",
        "event_type": "ZONE_DWELL",
        "timestamp": "2026-04-10T10:01:45Z",
        "zone_id": "Lakme",
        "dwell_ms": 60000,
        "is_staff": False,
        "confidence": 0.95,
        "metadata": {"queue_depth": None, "sku_zone": "makeup", "session_seq": 3}
    }
]

resp = client.post("/events/ingest", json={"events": events})
print("Status:", resp.status_code)
print("Response:", json.dumps(resp.json(), indent=2))
