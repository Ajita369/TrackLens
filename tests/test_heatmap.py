# PROMPT: "Generate pytest tests for TrackLens GET /stores/{id}/heatmap. Cover: normalized scores, low confidence flag, zero-visit zones."
# CHANGES MADE: Seeded multiple visitor sessions to verify the high/low confidence boundaries, and verified max-score normalization logic.

import pytest
import sqlite3
import uuid
from fastapi.testclient import TestClient

def test_heatmap_normalized(test_client: TestClient, sample_events):
    # Seed: Zone A has 3 entries, Zone B has 1 entry
    evts = []
    
    # Zone A (Lakme) -> 3 entries (Visitor V1, V2, V3)
    for idx, vid in enumerate(["V1", "V2", "V3"]):
        # Entry event
        e1 = sample_events[0].copy()
        e1["event_id"] = str(uuid.uuid4())
        e1["visitor_id"] = vid
        
        # Zone enter event (Lakme)
        e2 = sample_events[1].copy()
        e2["event_id"] = str(uuid.uuid4())
        e2["visitor_id"] = vid
        evts.extend([e1, e2])
        
    # Zone B (Minimalist) -> 1 entry (Visitor V4)
    v4_entry = sample_events[0].copy()
    v4_entry["event_id"] = str(uuid.uuid4())
    v4_entry["visitor_id"] = "V4"
    
    v4_zone = sample_events[4].copy()  # Minimalist
    v4_zone["event_id"] = str(uuid.uuid4())
    v4_zone["visitor_id"] = "V4"
    evts.extend([v4_entry, v4_zone])
    
    test_client.post("/events/ingest", json={"events": evts})
    
    response = test_client.get("/stores/ST1008/heatmap?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    zones = {z["zone_id"]: z for z in data["zones"]}
    
    # Lakme is the max (3 visits) -> normalized_score should be 100
    assert zones["Lakme"]["normalized_score"] == 100
    # Minimalist has 1 visit -> normalized_score should be 1/3 of 100 = 33
    assert zones["Minimalist"]["normalized_score"] == 33

def test_heatmap_low_confidence(test_client: TestClient, sample_events):
    # Less than 20 unique sessions visit the zone
    # We seed 5 sessions visiting 'Lakme'
    evts = []
    for idx in range(5):
        vid = f"VIS_CONF_{idx}"
        e_entry = sample_events[0].copy()
        e_entry["event_id"] = str(uuid.uuid4())
        e_entry["visitor_id"] = vid
        
        e_zone = sample_events[1].copy()
        e_zone["event_id"] = str(uuid.uuid4())
        e_zone["visitor_id"] = vid
        evts.extend([e_entry, e_zone])
        
    test_client.post("/events/ingest", json={"events": evts})
    
    response = test_client.get("/stores/ST1008/heatmap?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    zones = {z["zone_id"]: z for z in data["zones"]}
    # 5 sessions < 20 sessions -> low data_confidence
    assert zones["Lakme"]["data_confidence"] == "low"

def test_heatmap_high_confidence(test_client: TestClient, sample_events):
    # Exactly 20 sessions visit the zone
    evts = []
    for idx in range(20):
        vid = f"VIS_CONF_{idx}"
        e_entry = sample_events[0].copy()
        e_entry["event_id"] = str(uuid.uuid4())
        e_entry["visitor_id"] = vid
        
        e_zone = sample_events[1].copy()
        e_zone["event_id"] = str(uuid.uuid4())
        e_zone["visitor_id"] = vid
        evts.extend([e_entry, e_zone])
        
    test_client.post("/events/ingest", json={"events": evts})
    
    response = test_client.get("/stores/ST1008/heatmap?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    zones = {z["zone_id"]: z for z in data["zones"]}
    # 20 sessions >= 20 sessions -> high data_confidence
    assert zones["Lakme"]["data_confidence"] == "high"

def test_heatmap_empty(test_client: TestClient):
    response = test_client.get("/stores/ST1008/heatmap?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["zones"]) == 0
