# PROMPT: "Generate edge case tests for TrackLens. Cover: empty store, all-staff clip, zero purchases, re-entry in funnel."
# CHANGES MADE: Added multiple endpoint assertions to verify zero-data responses are structural and do not return HTTP 500 errors.

import pytest
from fastapi.testclient import TestClient

def test_empty_store_all_endpoints(test_client: TestClient):
    store_id = "EMPTY_STORE"
    date_str = "2026-04-10"
    
    # 1. Test metrics
    resp = test_client.get(f"/stores/{store_id}/metrics?date={date_str}")
    assert resp.status_code == 200
    m_data = resp.json()
    assert m_data["unique_visitors"] == 0
    assert m_data["conversion_rate"] == 0.0
    
    # 2. Test funnel
    resp = test_client.get(f"/stores/{store_id}/funnel?date={date_str}")
    assert resp.status_code == 200
    f_data = resp.json()
    for stage in f_data["stages"]:
        assert stage["count"] == 0
        
    # 3. Test heatmap
    resp = test_client.get(f"/stores/{store_id}/heatmap?date={date_str}")
    assert resp.status_code == 200
    h_data = resp.json()
    assert len(h_data["zones"]) == 0
    
    # 4. Test anomalies
    resp = test_client.get(f"/stores/{store_id}/anomalies?date={date_str}")
    assert resp.status_code == 200
    a_data = resp.json()
    # Should only return DEAD_ZONE anomalies if there are known zones, but since empty, returns nothing
    assert len(a_data["anomalies"]) == 0

def test_all_staff_metrics(test_client: TestClient, staff_only_events):
    test_client.post("/events/ingest", json={"events": staff_only_events})
    
    response = test_client.get("/stores/ST1008/metrics?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["unique_visitors"] == 0
    assert data["conversion_rate"] == 0.0
    assert len(data["avg_dwell_by_zone"]) == 0

def test_zero_purchases_conversion(test_client: TestClient, sample_events):
    # Ingest events but do not insert POS transactions
    test_client.post("/events/ingest", json={"events": sample_events})
    
    response = test_client.get("/stores/ST1008/metrics?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    assert data["unique_visitors"] == 1
    assert data["conversion_rate"] == 0.0

def test_reentry_funnel_dedup(test_client: TestClient, reentry_visitor_events):
    test_client.post("/events/ingest", json={"events": reentry_visitor_events})
    
    response = test_client.get("/stores/ST1008/funnel?date=2026-04-10")
    assert response.status_code == 200
    data = response.json()
    
    stages = {s["name"]: s for s in data["stages"]}
    # The distinct visitor count should be 1, not 2
    assert stages["Entry"]["count"] == 1
