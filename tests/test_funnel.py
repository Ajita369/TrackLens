# PROMPT: "Generate pytest tests for TrackLens GET /stores/{id}/funnel. Cover: normal progression, re-entry visitor counted once, visitor who enters but never visits zone, empty store."
# CHANGES MADE: Seeded transactional data for funnel stage 4 validation, and verified drop-off percentage arithmetic formulas.

import pytest
import sqlite3
import uuid
from fastapi.testclient import TestClient

def test_funnel_normal(test_client: TestClient, sample_events, db):
    test_client.post("/events/ingest", json={"events": sample_events})
    
    # Match the billing queue join at 10:01:45 (1775815305000) with a transaction
    db.execute("""
        INSERT INTO pos_transactions (transaction_id, store_id, timestamp, timestamp_epoch, basket_value_inr) 
        VALUES ('TX_FUN_01', 'ST1008', '2026-04-10T10:02:45Z', 1775815365000, 200.0)
    """)
    db.commit()
    
    response = test_client.get("/stores/ST1008/funnel?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["store_id"] == "ST1008"
    
    stages = {s["name"]: s for s in data["stages"]}
    
    assert stages["Entry"]["count"] == 1
    assert stages["Zone Visit"]["count"] == 1
    assert stages["Billing Queue"]["count"] == 1
    assert stages["Purchase"]["count"] == 1

def test_funnel_reentry_not_double_counted(test_client: TestClient, reentry_visitor_events):
    # Ingest visitor with ENTRY -> EXIT -> REENTRY sequence
    test_client.post("/events/ingest", json={"events": reentry_visitor_events})
    
    response = test_client.get("/stores/ST1008/funnel?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    stages = {s["name"]: s for s in data["stages"]}
    # Despite entry and reentry, distinct visitor count must remain 1
    assert stages["Entry"]["count"] == 1
    assert stages["Zone Visit"]["count"] == 1

def test_funnel_no_zone_visit(test_client: TestClient, sample_events):
    # Visitor has ENTRY and EXIT but no ZONE_ENTER
    e1 = sample_events[0].copy()  # ENTRY
    e2 = sample_events[9].copy()  # EXIT
    e2["timestamp"] = "2026-04-10T10:05:00Z"
    
    test_client.post("/events/ingest", json={"events": [e1, e2]})
    
    response = test_client.get("/stores/ST1008/funnel?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    stages = {s["name"]: s for s in data["stages"]}
    assert stages["Entry"]["count"] == 1
    assert stages["Zone Visit"]["count"] == 0
    assert stages["Billing Queue"]["count"] == 0
    assert stages["Purchase"]["count"] == 0

def test_funnel_empty(test_client: TestClient):
    response = test_client.get("/stores/ST1008/funnel?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    for stage in data["stages"]:
        assert stage["count"] == 0
        assert stage["drop_off_pct"] == 0.0

def test_funnel_dropoff_percentages(test_client: TestClient, sample_events, db):
    # Seed data to produce specific counts:
    # 3 Entry, 2 Zone Visit, 1 Billing Queue, 0 Purchase
    # Visitor A: Entry -> Zone Visit -> Billing Queue
    # Visitor B: Entry -> Zone Visit
    # Visitor C: Entry
    
    evts = []
    # Visitor A (Full queue, sample_events)
    for idx, e in enumerate(sample_events):
        ec = e.copy()
        ec["event_id"] = str(uuid.uuid4())
        ec["visitor_id"] = "V_A"
        evts.append(ec)
        
    # Visitor B
    vB_entry = sample_events[0].copy()
    vB_entry["event_id"] = str(uuid.uuid4())
    vB_entry["visitor_id"] = "V_B"
    vB_zone = sample_events[1].copy()
    vB_zone["event_id"] = str(uuid.uuid4())
    vB_zone["visitor_id"] = "V_B"
    evts.extend([vB_entry, vB_zone])
    
    # Visitor C
    vC_entry = sample_events[0].copy()
    vC_entry["event_id"] = str(uuid.uuid4())
    vC_entry["visitor_id"] = "V_C"
    evts.append(vC_entry)
    
    test_client.post("/events/ingest", json={"events": evts})
    
    response = test_client.get("/stores/ST1008/funnel?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    stages = {s["name"]: s for s in data["stages"]}
    
    # Check counts
    assert stages["Entry"]["count"] == 3
    assert stages["Zone Visit"]["count"] == 2
    assert stages["Billing Queue"]["count"] == 1
    assert stages["Purchase"]["count"] == 0
    
    # Check drop-offs
    # Entry -> Zone Visit: ((3 - 2) / 3) * 100 = 33.33%
    assert stages["Zone Visit"]["drop_off_pct"] == 33.33
    # Zone Visit -> Billing: ((2 - 1) / 2) * 100 = 50.0%
    assert stages["Billing Queue"]["drop_off_pct"] == 50.0
    # Billing -> Purchase: ((1 - 0) / 1) * 100 = 100.0%
    assert stages["Purchase"]["drop_off_pct"] == 100.0
