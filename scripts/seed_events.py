import json
import os
import urllib.request
import urllib.error
import uuid
import random
from datetime import datetime, timedelta, timezone

SAMPLE_EVENTS_PATH = "data/sample_events.jsonl"
API_URL = "http://localhost:8000/events/ingest"

def generate_mock_events(path: str, count: int = 200):
    print(f"Generating {count} mock events in {path}...")
    
    # Store ID matches our dataset CSV
    store_id = "ST1008"
    camera_ids = ["CAM 1", "CAM 2", "CAM 3", "CAM 4", "CAM 5"]
    zones = ["Maybelline", "Lakme", "Minimalist", "Good Vibes", "Cash Counter"]
    sku_zones = {"Maybelline": "makeup", "Lakme": "makeup", "Minimalist": "skin", "Good Vibes": "skin", "Cash Counter": "billing"}
    
    events = []
    base_time = datetime(2026, 4, 10, 10, 0, 0, tzinfo=timezone.utc)
    
    # Simulate multiple visitors
    for visitor_idx in range(1, 41):
        visitor_id = f"VIS_{store_id}_20260410_{visitor_idx:04d}"
        is_staff = (visitor_idx == 40)  # Make one visitor a staff member
        
        # Visitor start time
        visitor_time = base_time + timedelta(minutes=random.randint(0, 100), seconds=random.randint(0, 59))
        
        # 1. ENTRY event
        entry_event = {
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": "CAM 1", # Entrance cam
            "visitor_id": visitor_id,
            "event_type": "ENTRY",
            "timestamp": visitor_time.isoformat().replace("+00:00", "Z"),
            "zone_id": None,
            "dwell_ms": None,
            "is_staff": is_staff,
            "confidence": round(random.uniform(0.85, 0.99), 2),
            "metadata": {
                "queue_depth": None,
                "sku_zone": None,
                "session_seq": 1
            }
        }
        events.append(entry_event)
        
        # 2. ZONE_ENTER / DWELL / ZONE_EXIT events
        curr_time = visitor_time + timedelta(seconds=random.randint(5, 30))
        num_zones = random.randint(1, 3) if not is_staff else 5
        
        for seq, zone in enumerate(random.sample(zones, min(num_zones, len(zones))), 2):
            camera_id = random.choice(camera_ids[1:4]) if zone != "Cash Counter" else "CAM 5"
            sku_zone = sku_zones[zone]
            
            # Enter zone
            events.append({
                "event_id": str(uuid.uuid4()),
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": visitor_id,
                "event_type": "ZONE_ENTER",
                "timestamp": curr_time.isoformat().replace("+00:00", "Z"),
                "zone_id": zone,
                "dwell_ms": None,
                "is_staff": is_staff,
                "confidence": round(random.uniform(0.80, 0.99), 2),
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": sku_zone,
                    "session_seq": seq
                }
            })
            
            # Dwell inside zone (if visited for > 30s)
            dwell_duration = random.randint(10, 90)
            if dwell_duration >= 30:
                dwell_time = curr_time + timedelta(seconds=30)
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "store_id": store_id,
                    "camera_id": camera_id,
                    "visitor_id": visitor_id,
                    "event_type": "ZONE_DWELL",
                    "timestamp": dwell_time.isoformat().replace("+00:00", "Z"),
                    "zone_id": zone,
                    "dwell_ms": 30000,
                    "is_staff": is_staff,
                    "confidence": round(random.uniform(0.80, 0.99), 2),
                    "metadata": {
                        "queue_depth": None,
                        "sku_zone": sku_zone,
                        "session_seq": seq + 1
                    }
                })
            
            curr_time += timedelta(seconds=dwell_duration)
            
            # Exit zone
            events.append({
                "event_id": str(uuid.uuid4()),
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": visitor_id,
                "event_type": "ZONE_EXIT",
                "timestamp": curr_time.isoformat().replace("+00:00", "Z"),
                "zone_id": zone,
                "dwell_ms": None,
                "is_staff": is_staff,
                "confidence": round(random.uniform(0.80, 0.99), 2),
                "metadata": {
                    "queue_depth": None,
                    "sku_zone": sku_zone,
                    "session_seq": seq + 2
                }
            })
            
            # Special Queue Join for cash counter (if visitor is customer)
            if zone == "Cash Counter" and not is_staff:
                queue_time = curr_time - timedelta(seconds=dwell_duration)
                events.append({
                    "event_id": str(uuid.uuid4()),
                    "store_id": store_id,
                    "camera_id": camera_id,
                    "visitor_id": visitor_id,
                    "event_type": "BILLING_QUEUE_JOIN",
                    "timestamp": queue_time.isoformat().replace("+00:00", "Z"),
                    "zone_id": zone,
                    "dwell_ms": None,
                    "is_staff": False,
                    "confidence": round(random.uniform(0.80, 0.99), 2),
                    "metadata": {
                        "queue_depth": random.randint(1, 4),
                        "sku_zone": sku_zone,
                        "session_seq": seq + 3
                    }
                })
                
                # Check if visitor abandoned
                if random.choice([True, False]):
                    events.append({
                        "event_id": str(uuid.uuid4()),
                        "store_id": store_id,
                        "camera_id": camera_id,
                        "visitor_id": visitor_id,
                        "event_type": "BILLING_QUEUE_ABANDON",
                        "timestamp": curr_time.isoformat().replace("+00:00", "Z"),
                        "zone_id": zone,
                        "dwell_ms": None,
                        "is_staff": False,
                        "confidence": round(random.uniform(0.80, 0.99), 2),
                        "metadata": {
                            "queue_depth": 0,
                            "sku_zone": sku_zone,
                            "session_seq": seq + 4
                        }
                    })

            curr_time += timedelta(seconds=random.randint(5, 15))
            
        # 3. EXIT event
        events.append({
            "event_id": str(uuid.uuid4()),
            "store_id": store_id,
            "camera_id": "CAM 1",
            "visitor_id": visitor_id,
            "event_type": "EXIT",
            "timestamp": curr_time.isoformat().replace("+00:00", "Z"),
            "zone_id": None,
            "dwell_ms": None,
            "is_staff": is_staff,
            "confidence": round(random.uniform(0.85, 0.99), 2),
            "metadata": {
                "queue_depth": None,
                "sku_zone": None,
                "session_seq": 99
            }
        })
        
    # Trim or pad to get exactly count events
    events = events[:count]
    
    # Save events to file
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")
            
    print(f"Successfully generated {len(events)} events.")

def seed_events():
    if not os.path.exists(SAMPLE_EVENTS_PATH):
        generate_mock_events(SAMPLE_EVENTS_PATH, 200)
        
    print(f"Reading events from {SAMPLE_EVENTS_PATH}...")
    events = []
    with open(SAMPLE_EVENTS_PATH, "r") as f:
        for line in f:
            if line.strip():
                events.append(json.loads(line.strip()))
                
    total_events = len(events)
    print(f"Loaded {total_events} events from file.")
    
    batch_size = 100
    for i in range(0, total_events, batch_size):
        batch = events[i : i + batch_size]
        payload = {"events": batch}
        
        req = urllib.request.Request(
            API_URL,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        try:
            with urllib.request.urlopen(req) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                print(f"Batch {i//batch_size + 1}: Status {resp.status} - "
                      f"Accepted: {resp_data.get('accepted', 0)}, "
                      f"Rejected: {resp_data.get('rejected', 0)}, "
                      f"Errors: {len(resp_data.get('errors', []))}")
        except urllib.error.HTTPError as e:
            print(f"Batch {i//batch_size + 1} HTTP Error: {e.code} - {e.reason}")
            try:
                error_body = e.read().decode("utf-8")
                print("Error body:", error_body)
            except Exception:
                pass
        except urllib.error.URLError as e:
            print(f"Batch {i//batch_size + 1} Connection Error: {e.reason}")

if __name__ == "__main__":
    seed_events()
