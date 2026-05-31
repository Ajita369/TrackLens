# PROMPT: "Generate pytest tests for TrackLens GET /stores/{id}/metrics. Cover: store with typical events, store with no events, store where all events are staff (0 visitors), store with zero purchases, correct dwell averages."
# CHANGES MADE: Integrated POS transactions seeding inside tests to correctly check conversion calculations, and set up assertions for JSON properties.

import pytest
import sqlite3
from fastapi.testclient import TestClient

def test_metrics_typical_store(test_client: TestClient, sample_events, db):
    # Ingest sample events
    test_client.post("/events/ingest", json={"events": sample_events})
    
    # Insert a POS transaction matching one of the billing joins in the database
    # VIS_ST1008_20260410_0001 joined checkout queue at 2026-04-10T10:01:45Z (epoch 1775815305000)
    # We place a transaction 1 minute later at epoch 1775815365000
    db.execute("""
        INSERT INTO pos_transactions (transaction_id, store_id, timestamp, timestamp_epoch, basket_value_inr) 
        VALUES ('TX_VAL_01', 'ST1008', '2026-04-10T10:02:45Z', 1775815365000, 1500.0)
    """)
    db.commit()
    
    response = test_client.get("/stores/ST1008/metrics?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["store_id"] == "ST1008"
    assert data["unique_visitors"] == 1
    assert data["conversion_rate"] == 1.0
    assert data["current_queue_depth"] == 2
    assert data["abandonment_rate"] == 1.0  # 1 join, 1 abandon in sample events
    assert "Lakme" in data["avg_dwell_by_zone"]
    assert data["avg_dwell_by_zone"]["Lakme"] == 30000.0

def test_metrics_empty_store(test_client: TestClient):
    response = test_client.get("/stores/ST1008/metrics?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["unique_visitors"] == 0
    assert data["conversion_rate"] == 0.0
    assert data["current_queue_depth"] == 0
    assert data["abandonment_rate"] == 0.0
    assert len(data["avg_dwell_by_zone"]) == 0

def test_metrics_all_staff(test_client: TestClient, staff_only_events):
    test_client.post("/events/ingest", json={"events": staff_only_events})
    response = test_client.get("/stores/ST1008/metrics?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["unique_visitors"] == 0
    assert len(data["avg_dwell_by_zone"]) == 0

def test_metrics_zero_purchases(test_client: TestClient, sample_events):
    # Ingest events but do NOT seed pos transactions
    test_client.post("/events/ingest", json={"events": sample_events})
    response = test_client.get("/stores/ST1008/metrics?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["unique_visitors"] == 1
    assert data["conversion_rate"] == 0.0

def test_metrics_dwell_averages(test_client: TestClient, sample_events, db):
    # Inject multiple ZONE_DWELL events with different dwell durations
    # Clear events and ingest manually
    import uuid
    e1 = sample_events[2].copy()  # Dwell event at Lakme, 30000ms
    e1["event_id"] = str(uuid.uuid4())
    
    e2 = sample_events[2].copy()  # Dwell event at Lakme, 60000ms
    e2["event_id"] = str(uuid.uuid4())
    e2["dwell_ms"] = 60000
    
    test_client.post("/events/ingest", json={"events": [sample_events[0], e1, e2]})
    
    response = test_client.get("/stores/ST1008/metrics?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["avg_dwell_by_zone"]["Lakme"] == 45000.0  # Average of 30000 and 60000
