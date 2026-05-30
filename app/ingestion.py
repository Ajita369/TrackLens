from fastapi import APIRouter, Depends, status, Response
from typing import Dict, Any, List
from pydantic import ValidationError
from app.models import IngestRequest, IngestResponse, IngestErrorDetail, Event
from app.database import get_db
import sqlite3
import json

router = APIRouter()

@router.post("/events/ingest", response_model=IngestResponse, status_code=status.HTTP_200_OK)
def ingest_events(request: IngestRequest, response: Response, db: sqlite3.Connection = Depends(get_db)):
    accepted = 0
    rejected = 0
    errors: List[IngestErrorDetail] = []
    
    for idx, raw_event in enumerate(request.events):
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
