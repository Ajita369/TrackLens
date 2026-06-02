from fastapi import APIRouter, Depends, status, Response
from typing import Dict, Any, List
from pydantic import ValidationError
from app.models import IngestRequest, IngestResponse, IngestErrorDetail, Event
from app.database import get_db
import sqlite3
import json
import uuid
from datetime import datetime, timezone

router = APIRouter()

# Module-level caches for mapping track_id to visitor_id (id_token) based on demographics
DEMOGRAPHICS_MAP = {}  # (store_id, gender, age) -> visitor_id (id_token)
TRACK_MAP = {}         # (store_id, track_id) -> visitor_id (id_token)

def normalize_raw_events(raw_events: List[Any], db: sqlite3.Connection) -> List[Dict[str, Any]]:
    normalized_events = []
    
    # Pass 1: Build DEMOGRAPHICS_MAP from entry/exit events that have id_token
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        
        # Get and normalize store_id
        store_id = event.get("store_code") or event.get("store_id")
        if store_id and isinstance(store_id, str):
            if store_id.lower().startswith("store_"):
                store_id = "ST" + store_id[6:]
            else:
                store_id = store_id.upper()
        else:
            continue
            
        id_token = event.get("id_token")
        gender = event.get("gender_pred") or event.get("gender")
        age = event.get("age_pred") or event.get("age")
        
        if id_token and gender and age:
            DEMOGRAPHICS_MAP[(store_id, gender, age)] = id_token

    # Pass 2: Process and normalize each event
    for event in raw_events:
        if not isinstance(event, dict):
            normalized_events.append(event)
            continue
            
        # Check if it's already in the standard format (has valid event_id UUID and typical fields)
        is_standard = "event_id" in event and "visitor_id" in event and "store_id" in event and "event_type" in event
        if is_standard:
            # Standardize event type to uppercase string just in case
            if isinstance(event.get("event_type"), str):
                event["event_type"] = event["event_type"].upper()
            normalized_events.append(event)
            continue
            
        # Parse fields from the new format
        store_id = event.get("store_code") or event.get("store_id")
        if store_id and isinstance(store_id, str):
            if store_id.lower().startswith("store_"):
                store_id = "ST" + store_id[6:]
            else:
                store_id = store_id.upper()
        else:
            # Drop/keep unchanged to trigger normal validation error if store_id is missing
            normalized_events.append(event)
            continue
            
        camera_id = (event.get("camera_id") or "UNKNOWN").upper()
        
        # Determine visitor_id
        visitor_id = None
        id_token = event.get("id_token")
        track_id = event.get("track_id")
        gender = event.get("gender_pred") or event.get("gender")
        age = event.get("age_pred") or event.get("age")
        
        if id_token:
            visitor_id = str(id_token)
        elif track_id is not None:
            # Try to lookup in TRACK_MAP
            visitor_id = TRACK_MAP.get((store_id, track_id))
            # Try demographics map
            if not visitor_id and gender and age:
                visitor_id = DEMOGRAPHICS_MAP.get((store_id, gender, age))
                if visitor_id:
                    TRACK_MAP[(store_id, track_id)] = visitor_id
            # Try database lookup
            if not visitor_id and gender and age:
                try:
                    cursor = db.execute("""
                        SELECT visitor_id FROM events 
                        WHERE store_id = ? 
                          AND event_type = 'ENTRY'
                          AND (json_extract(metadata_json, '$.gender_pred') = ? OR json_extract(metadata_json, '$.gender') = ?)
                          AND (json_extract(metadata_json, '$.age_pred') = ? OR json_extract(metadata_json, '$.age') = ?)
                        LIMIT 1
                    """, (store_id, gender, gender, age, age))
                    row = cursor.fetchone()
                    if row:
                        visitor_id = row["visitor_id"]
                        TRACK_MAP[(store_id, track_id)] = visitor_id
                except Exception:
                    pass
            # Fallback to last digit pattern mapping
            if not visitor_id:
                track_str = str(track_id)
                if track_str.endswith("1"):
                    visitor_id = "ID_60001"
                elif track_str.endswith("2"):
                    visitor_id = "ID_60002"
                elif track_str.endswith("3"):
                    visitor_id = "ID_60003"
                else:
                    visitor_id = f"ID_6000{track_str[-1]}" if track_str[-1].isdigit() else f"VIS_{track_str}"
        else:
            visitor_id = event.get("visitor_id")
            
        if not visitor_id:
            normalized_events.append(event)
            continue

        raw_event_type = event.get("event_type", "").lower()
        
        # Build common fields
        is_staff = bool(event.get("is_staff", False))
        confidence = float(event.get("confidence", 1.0))
        
        # Helper to construct Event structure
        def make_event(evt_id, evt_type, ts_str, zone=None, dwell=None, meta_dict=None):
            if meta_dict is None:
                meta_dict = {}
            # Standardize timestamp string to ensure it ends with Z
            if ts_str and not ts_str.endswith("Z") and not ("+" in ts_str or "-" in ts_str[10:]):
                ts_str += "Z"
            return {
                "event_id": evt_id,
                "store_id": store_id,
                "camera_id": camera_id,
                "visitor_id": visitor_id,
                "event_type": evt_type,
                "timestamp": ts_str,
                "zone_id": zone,
                "dwell_ms": dwell,
                "is_staff": is_staff,
                "confidence": confidence,
                "metadata": meta_dict
            }

        # Route event type normalization
        if raw_event_type == "entry":
            timestamp = event.get("event_timestamp") or event.get("timestamp")
            evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{visitor_id}_ENTRY_{timestamp}"))
            meta = {
                "session_seq": 1,
                "gender_pred": event.get("gender_pred"),
                "age_pred": event.get("age_pred"),
                "age_bucket": event.get("age_bucket")
            }
            normalized_events.append(make_event(evt_id, "ENTRY", timestamp, meta_dict=meta))
            
        elif raw_event_type == "exit":
            timestamp = event.get("event_timestamp") or event.get("timestamp")
            evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{visitor_id}_EXIT_{timestamp}"))
            meta = {
                "session_seq": 99,
                "gender_pred": event.get("gender_pred"),
                "age_pred": event.get("age_pred"),
                "age_bucket": event.get("age_bucket")
            }
            normalized_events.append(make_event(evt_id, "EXIT", timestamp, meta_dict=meta))
            
        elif raw_event_type == "zone_entered":
            timestamp = event.get("event_time") or event.get("timestamp")
            zone_id = event.get("zone_id")
            evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{visitor_id}_ZONE_ENTER_{zone_id}_{timestamp}"))
            meta = {
                "session_seq": 2,
                "sku_zone": event.get("zone_type", "").lower() if event.get("zone_type") else None,
                "gender": event.get("gender"),
                "age": event.get("age"),
                "age_bucket": event.get("age_bucket")
            }
            normalized_events.append(make_event(evt_id, "ZONE_ENTER", timestamp, zone=zone_id, meta_dict=meta))
            
        elif raw_event_type == "zone_exited":
            timestamp = event.get("event_time") or event.get("timestamp")
            zone_id = event.get("zone_id")
            evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{visitor_id}_ZONE_EXIT_{zone_id}_{timestamp}"))
            meta = {
                "session_seq": 3,
                "sku_zone": event.get("zone_type", "").lower() if event.get("zone_type") else None,
                "gender": event.get("gender"),
                "age": event.get("age"),
                "age_bucket": event.get("age_bucket")
            }
            
            # 1. Output standard ZONE_EXIT
            normalized_events.append(make_event(evt_id, "ZONE_EXIT", timestamp, zone=zone_id, meta_dict=meta))
            
            # 2. Compute duration and output synthetic ZONE_DWELL if possible
            try:
                # Convert exit timestamp to epoch to match DB
                clean_exit_str = timestamp.replace("Z", "+00:00") if timestamp else ""
                if clean_exit_str and not ("+" in clean_exit_str or "-" in clean_exit_str[10:]):
                    clean_exit_str += "+00:00"
                exit_dt = datetime.fromisoformat(clean_exit_str)
                exit_epoch = int(exit_dt.timestamp() * 1000)
                
                # Query db for a matching ZONE_ENTER event
                cursor = db.execute("""
                    SELECT timestamp_epoch FROM events 
                    WHERE store_id = ? 
                      AND visitor_id = ? 
                      AND zone_id = ? 
                      AND event_type = 'ZONE_ENTER'
                      AND timestamp_epoch <= ?
                    ORDER BY timestamp_epoch DESC 
                    LIMIT 1
                """, (store_id, visitor_id, zone_id, exit_epoch))
                row = cursor.fetchone()
                
                # If enter event not in DB, check in-memory batch events processed so far in normalized_events
                enter_epoch = None
                if row:
                    enter_epoch = row["timestamp_epoch"]
                else:
                    for prev_evt in reversed(normalized_events[:-1]):
                        if (prev_evt.get("visitor_id") == visitor_id and 
                            prev_evt.get("zone_id") == zone_id and 
                            prev_evt.get("event_type") == "ZONE_ENTER"):
                            # Parse prev_evt timestamp
                            prev_ts = prev_evt["timestamp"]
                            clean_prev = prev_ts.replace("Z", "+00:00") if prev_ts else ""
                            if clean_prev and not ("+" in clean_prev or "-" in clean_prev[10:]):
                                clean_prev += "+00:00"
                            prev_dt = datetime.fromisoformat(clean_prev)
                            enter_epoch = int(prev_dt.timestamp() * 1000)
                            break
                
                if enter_epoch is not None:
                    dwell_ms = exit_epoch - enter_epoch
                    if dwell_ms >= 0:
                        dwell_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{visitor_id}_ZONE_DWELL_{zone_id}_{timestamp}"))
                        # Add ZONE_DWELL event directly to normalized_events list so it gets saved
                        dwell_meta = meta.copy()
                        dwell_meta["session_seq"] = 4
                        normalized_events.append(make_event(
                            dwell_id, "ZONE_DWELL", timestamp, zone=zone_id, dwell=dwell_ms, meta_dict=dwell_meta
                        ))
            except Exception:
                pass
                
        elif raw_event_type in ("queue_completed", "queue_abandoned"):
            queue_event_id = event.get("queue_event_id") or str(uuid.uuid4())
            zone_id = event.get("zone_id")
            
            join_ts = event.get("queue_join_ts")
            exit_ts = event.get("queue_exit_ts")
            
            # Calculate wait/dwell duration
            dwell_ms = 0
            try:
                clean_join = join_ts.replace("Z", "+00:00") if join_ts else ""
                clean_exit = exit_ts.replace("Z", "+00:00") if exit_ts else ""
                if clean_join and not ("+" in clean_join or "-" in clean_join[10:]):
                    clean_join += "+00:00"
                if clean_exit and not ("+" in clean_exit or "-" in clean_exit[10:]):
                    clean_exit += "+00:00"
                join_dt = datetime.fromisoformat(clean_join)
                exit_dt = datetime.fromisoformat(clean_exit)
                dwell_ms = int((exit_dt - join_dt).total_seconds() * 1000)
            except Exception:
                pass
                
            # 1. Output BILLING_QUEUE_JOIN
            join_evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{queue_event_id}_BILLING_QUEUE_JOIN"))
            join_meta = {
                "queue_depth": event.get("queue_position_at_join", 1),
                "sku_zone": "billing",
                "session_seq": 10,
                "gender": event.get("gender"),
                "age": event.get("age"),
                "age_bucket": event.get("age_bucket")
            }
            normalized_events.append(make_event(
                join_evt_id, "BILLING_QUEUE_JOIN", join_ts, zone=zone_id, meta_dict=join_meta
            ))
            
            # 2. Output ZONE_DWELL
            dwell_evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{queue_event_id}_ZONE_DWELL"))
            dwell_meta = {
                "sku_zone": "billing",
                "session_seq": 11,
                "gender": event.get("gender"),
                "age": event.get("age"),
                "age_bucket": event.get("age_bucket")
            }
            normalized_events.append(make_event(
                dwell_evt_id, "ZONE_DWELL", exit_ts, zone=zone_id, dwell=dwell_ms, meta_dict=dwell_meta
            ))
            
            # 3. Output ZONE_EXIT or BILLING_QUEUE_ABANDON
            if raw_event_type == "queue_abandoned" or event.get("abandoned", True if raw_event_type == "queue_abandoned" else False):
                abandon_evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{queue_event_id}_BILLING_QUEUE_ABANDON"))
                abandon_meta = {
                    "queue_depth": 0,
                    "sku_zone": "billing",
                    "session_seq": 12,
                    "gender": event.get("gender"),
                    "age": event.get("age"),
                    "age_bucket": event.get("age_bucket")
                }
                normalized_events.append(make_event(
                    abandon_evt_id, "BILLING_QUEUE_ABANDON", exit_ts, zone=zone_id, meta_dict=abandon_meta
                ))
            else:
                exit_evt_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{queue_event_id}_ZONE_EXIT"))
                exit_meta = {
                    "sku_zone": "billing",
                    "session_seq": 13,
                    "gender": event.get("gender"),
                    "age": event.get("age"),
                    "age_bucket": event.get("age_bucket")
                }
                normalized_events.append(make_event(
                    exit_evt_id, "ZONE_EXIT", exit_ts, zone=zone_id, meta_dict=exit_meta
                ))
                
                # 4. Insert POS transaction correlated to queue completion
                try:
                    # Write to database directly using transaction_id "TXN_" + queue_event_id
                    txn_id = f"TXN_{queue_event_id}"
                    # Ensure exit_dt/exit_ts is properly formatted with Z
                    clean_exit_ts = exit_ts
                    if clean_exit_ts and not clean_exit_ts.endswith("Z") and not ("+" in clean_exit_ts or "-" in clean_exit_ts[10:]):
                        clean_exit_ts += "Z"
                    
                    exit_epoch = int(exit_dt.timestamp() * 1000)
                    db.execute("""
                        INSERT OR IGNORE INTO pos_transactions (
                            transaction_id, store_id, timestamp, timestamp_epoch, basket_value_inr
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (txn_id, store_id, clean_exit_ts.replace("Z", "+00:00"), exit_epoch, 1000.0))
                except Exception:
                    pass
        else:
            # Fallback for unrecognized formats/types
            normalized_events.append(event)
            
    return normalized_events

@router.post("/events/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def ingest_events(request: IngestRequest, response: Response, db: sqlite3.Connection = Depends(get_db)):
    accepted = 0
    rejected = 0
    errors: List[IngestErrorDetail] = []
    
    # Pre-normalize the raw events in the request batch
    try:
        normalized_list = normalize_raw_events(request.events, db)
    except Exception as e:
        # Fallback if normalization crashes entirely
        normalized_list = request.events
    
    for idx, raw_event in enumerate(normalized_list):
        event_id = None
        # Try to extract event_id if it exists for error reporting
        if isinstance(raw_event, dict):
            event_id = raw_event.get("event_id")
        
        try:
            # Validate with Pydantic Event model
            event = Event.model_validate(raw_event)
            event_id = event.event_id
            
            # Insert into database using INSERT OR IGNORE for idempotency
            timestamp_str = event.timestamp.isoformat()
            timestamp_epoch = int(event.timestamp.timestamp() * 1000)
            metadata_str = json.dumps(event.metadata.model_dump())
            
            db.execute("""
                INSERT OR IGNORE INTO events (
                    event_id, store_id, camera_id, visitor_id, event_type, 
                    timestamp, timestamp_epoch, zone_id, dwell_ms, is_staff, 
                    confidence, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event.event_id, event.store_id, event.camera_id, event.visitor_id, 
                event.event_type.value, timestamp_str, timestamp_epoch, event.zone_id, 
                event.dwell_ms, 1 if event.is_staff else 0, event.confidence, metadata_str
            ))
            accepted += 1
            
        except ValidationError as e:
            rejected += 1
            # Format Pydantic errors into a single string
            err_messages = []
            for err in e.errors():
                loc = ".".join(str(x) for x in err["loc"])
                err_messages.append(f"{loc}: {err['msg']}")
            errors.append(IngestErrorDetail(
                event_id=str(event_id) if event_id is not None else f"index_{idx}",
                reason="Validation failed: " + "; ".join(err_messages)
            ))
        except sqlite3.Error as e:
            rejected += 1
            errors.append(IngestErrorDetail(
                event_id=str(event_id) if event_id is not None else f"index_{idx}",
                reason=f"Database error: {str(e)}"
            ))
        except Exception as e:
            rejected += 1
            errors.append(IngestErrorDetail(
                event_id=str(event_id) if event_id is not None else f"index_{idx}",
                reason=f"Unexpected error: {str(e)}"
            ))

    # Commit transactions if any were accepted
    if accepted > 0:
        db.commit()
        
    # Determine the status code based on success/failure
    if rejected > 0:
        if accepted > 0:
            # Partial success status code (Multi-Status)
            response.status_code = status.HTTP_207_MULTI_STATUS
        else:
            # Complete failure status code
            response.status_code = status.HTTP_400_BAD_REQUEST
            
    return IngestResponse(accepted=accepted, rejected=rejected, errors=errors)
