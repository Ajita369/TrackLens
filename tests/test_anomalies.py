# PROMPT: "Generate pytest tests for TrackLens GET /stores/{id}/anomalies. Cover: queue spike detected, no anomalies, dead zone detection."
# CHANGES MADE: Added database fixtures to simulate historical rolling average queue depths, and mocked simulation timestamp values.

import pytest
import sqlite3
import json
import uuid
from fastapi.testclient import TestClient

def test_queue_spike_detected(test_client: TestClient, sample_events):
    # Historical baseline queue join events (queue depth 1)
    hist_events = []
    for idx in range(5):
        evt = sample_events[7].copy()  # BILLING_QUEUE_JOIN
        evt["event_id"] = str(uuid.uuid4())
        evt["visitor_id"] = f"vis_hist_{idx}"
        evt["metadata"] = {"queue_depth": 1, "sku_zone": "billing", "session_seq": 1}
        hist_events.append(evt)
        
    # Seed historical records
    test_client.post("/events/ingest", json={"events": hist_events})
    
    # Trigger a spike join event (queue depth 4, 4x average depth)
    spike_evt = sample_events[7].copy()
    spike_evt["event_id"] = str(uuid.uuid4())
    spike_evt["visitor_id"] = "vis_spike_01"
    spike_evt["metadata"] = {"queue_depth": 4, "sku_zone": "billing", "session_seq": 1}
    
    test_client.post("/events/ingest", json={"events": [spike_evt]})
    
    response = test_client.get("/stores/ST1008/anomalies?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    # We should have a QUEUE_SPIKE anomaly with CRITICAL severity
    queue_anomalies = [a for a in data["anomalies"] if a["type"] == "QUEUE_SPIKE"]
    assert len(queue_anomalies) == 1
    assert queue_anomalies[0]["severity"] == "CRITICAL"
    assert " suggested_action" in queue_anomalies[0] or "suggested_action" in queue_anomalies[0]

def test_no_anomalies(test_client: TestClient, sample_events):
    # Seed normal events that don't trigger spikes or dead zones
    # We inject visit activities for Lakme and Cash Counter
    test_client.post("/events/ingest", json={"events": sample_events})
    
    response = test_client.get("/stores/ST1008/anomalies?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    # QUEUE_SPIKE shouldn't trigger because queue depth was 2 (historical average is 2)
    queue_anomalies = [a for a in data["anomalies"] if a["type"] == "QUEUE_SPIKE"]
    assert len(queue_anomalies) == 0

def test_dead_zone_detection(test_client: TestClient, sample_events):
    # Seed events. We have activities in 'Lakme' and 'Cash Counter'.
    # In conftest.py, sample_events contains:
    # - ZONE_ENTER at 'Lakme' at index 1 (10:00:15)
    # - ZONE_ENTER at 'Minimalist' at index 4 (10:01:00)
    # - ZONE_ENTER at 'Cash Counter' at index 6 (10:01:30)
    
    # To check dead zones, the anomalies code finds the maximum event timestamp_epoch (simulation now)
    # and checks which zones had NO entries in the 30 minutes preceding it.
    # Let's seed:
    # 1. ZONE_ENTER at 'Lakme' at 10:00:00
    # 2. ZONE_ENTER at 'Cash Counter' at 10:45:00 (this makes max_epoch = 10:45:00)
    # Zone 'Minimalist' has NO entries in the last 30 minutes (its last entry was at 10:01:00, which is 44 mins ago)
    
    e_entry = sample_events[0].copy()
    e_entry["timestamp"] = "2026-04-10T10:00:00Z"
    
    e_lakme = sample_events[1].copy()
    e_lakme["timestamp"] = "2026-04-10T10:00:15Z"
    
    e_min = sample_events[4].copy()
    e_min["timestamp"] = "2026-04-10T10:01:00Z"
    
    e_cash = sample_events[6].copy()
    e_cash["timestamp"] = "2026-04-10T10:45:00Z"
    
    test_client.post("/events/ingest", json={"events": [e_entry, e_lakme, e_min, e_cash]})
    
    response = test_client.get("/stores/ST1008/anomalies?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    # We should have a DEAD_ZONE anomaly for 'Minimalist' and 'Lakme' (since their last visits were >30 mins before 10:45:00)
    dead_zones = [a for a in data["anomalies"] if a["type"] == "DEAD_ZONE"]
    assert len(dead_zones) > 0
    zone_ids = [a["details"] for a in dead_zones]
    # Verify that the zone names are flagged
    assert any("Minimalist" in detail for detail in zone_ids)
