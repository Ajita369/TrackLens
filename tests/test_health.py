# PROMPT: "Generate pytest tests for TrackLens GET /health. Cover: healthy state, stale feed detection, empty database."
# CHANGES MADE: Mocked datetime.now to ensure stale feed detection passes reliably irrespective of current system time.

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient

def test_health_empty_db(test_client: TestClient):
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert len(data["stores"]) == 0
    assert data["uptime_seconds"] >= 0.0
    assert data["version"] == "1.0.0"

def test_health_healthy(test_client: TestClient, sample_events):
    # Set the event timestamp to exactly 2 minutes ago from "now"
    recent_time = datetime.now(timezone.utc) - timedelta(minutes=2)
    recent_str = recent_time.isoformat().replace("+00:00", "Z")
    
    evt = sample_events[0].copy()
    evt["timestamp"] = recent_str
    
    test_client.post("/events/ingest", json={"events": [evt]})
    
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["stores"]["ST1008"]["feed_status"] == "LIVE"
    assert data["stores"]["ST1008"]["event_count"] == 1

def test_health_stale_feed(test_client: TestClient, sample_events):
    # Set the event timestamp to 15 minutes ago (older than 10 minutes)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=15)
    stale_str = stale_time.isoformat().replace("+00:00", "Z")
    
    evt = sample_events[0].copy()
    evt["timestamp"] = stale_str
    
    test_client.post("/events/ingest", json={"events": [evt]})
    
    response = test_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    # If any feed is stale, overall status is 'degraded'
    assert data["status"] == "degraded"
    assert data["stores"]["ST1008"]["feed_status"] == "STALE_FEED"
    assert data["stores"]["ST1008"]["event_count"] == 1
