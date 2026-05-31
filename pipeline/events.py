import uuid
import json
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

class EventEmitter:
    def __init__(self, store_id: str):
        self.store_id = store_id
        self.events = []
        
        # Tracks current zone state per visitor: {visitor_id: {"zone_id": str, "entered_at": datetime, "last_dwell_at": datetime, "sku_zone": str}}
        self.visitor_zones = {}
        # Set of visitors currently in billing zone (Cash Counter) to compute queue depth
        self.billing_queue = set()
        
    def _create_event(
        self, 
        event_type: str, 
        visitor_id: str, 
        camera_id: str, 
        timestamp: datetime,
        zone_id: Optional[str] = None, 
        dwell_ms: Optional[int] = None, 
        is_staff: bool = False, 
        confidence: float = 0.95,
        queue_depth: Optional[int] = None,
        sku_zone: Optional[str] = None,
        session_seq: int = 1
    ) -> Dict[str, Any]:
        """
        Helper to construct a schema-compliant Event dict.
        """
        # Ensure timestamp is ISO-8601 UTC format string
        # datetime string should end with Z
        timestamp_str = timestamp.isoformat().replace("+00:00", "Z")
        if not timestamp_str.endswith("Z"):
            timestamp_str += "Z"
            
        event = {
            "event_id": str(uuid.uuid4()),
            "store_id": self.store_id,
            "camera_id": camera_id,
            "visitor_id": visitor_id,
            "event_type": event_type,
            "timestamp": timestamp_str,
            "zone_id": zone_id,
            "dwell_ms": dwell_ms,
            "is_staff": is_staff,
            "confidence": round(confidence, 2),
            "metadata": {
                "queue_depth": queue_depth,
                "sku_zone": sku_zone,
                "session_seq": session_seq
            }
        }
        return event

    def emit_entry(self, visitor_id: str, timestamp: datetime, camera_id: str, confidence: float, is_staff: bool, session_seq: int = 1):
        evt = self._create_event("ENTRY", visitor_id, camera_id, timestamp, is_staff=is_staff, confidence=confidence, session_seq=session_seq)
        self.events.append(evt)
        print(f"Emitted ENTRY: visitor_id={visitor_id}, time={timestamp}")
        
    def emit_exit(self, visitor_id: str, timestamp: datetime, camera_id: str, confidence: float, is_staff: bool, session_seq: int = 1):
        # Trigger exit from current zone if still in one
        if visitor_id in self.visitor_zones:
            zone_info = self.visitor_zones[visitor_id]
            self.emit_zone_exit(visitor_id, zone_info["zone_id"], timestamp, camera_id, is_staff, zone_info["sku_zone"], session_seq + 1)
            del self.visitor_zones[visitor_id]
            
        evt = self._create_event("EXIT", visitor_id, camera_id, timestamp, is_staff=is_staff, confidence=confidence, session_seq=session_seq)
        self.events.append(evt)
        print(f"Emitted EXIT: visitor_id={visitor_id}, time={timestamp}")
        
    def emit_reentry(self, visitor_id: str, timestamp: datetime, camera_id: str, confidence: float, is_staff: bool, session_seq: int = 1):
        evt = self._create_event("REENTRY", visitor_id, camera_id, timestamp, is_staff=is_staff, confidence=confidence, session_seq=session_seq)
        self.events.append(evt)
        print(f"Emitted REENTRY: visitor_id={visitor_id}, time={timestamp}")

    def emit_zone_enter(self, visitor_id: str, zone_id: str, timestamp: datetime, camera_id: str, is_staff: bool, sku_zone: str, session_seq: int):
        evt = self._create_event("ZONE_ENTER", visitor_id, camera_id, timestamp, zone_id=zone_id, is_staff=is_staff, sku_zone=sku_zone, session_seq=session_seq)
        self.events.append(evt)
        
    def emit_zone_exit(self, visitor_id: str, zone_id: str, timestamp: datetime, camera_id: str, is_staff: bool, sku_zone: str, session_seq: int):
        evt = self._create_event("ZONE_EXIT", visitor_id, camera_id, timestamp, zone_id=zone_id, is_staff=is_staff, sku_zone=sku_zone, session_seq=session_seq)
        self.events.append(evt)

    def emit_zone_dwell(self, visitor_id: str, zone_id: str, timestamp: datetime, camera_id: str, is_staff: bool, dwell_ms: int, sku_zone: str, session_seq: int):
        evt = self._create_event("ZONE_DWELL", visitor_id, camera_id, timestamp, zone_id=zone_id, dwell_ms=dwell_ms, is_staff=is_staff, sku_zone=sku_zone, session_seq=session_seq)
        self.events.append(evt)

    def on_tracking_update(self, update: Dict[str, Any], timestamp: datetime, camera_id: str, is_staff: bool, session_seq: int):
        """
        Processes a tracking state update for a single visitor and manages transitions.
        """
        visitor_id = update["visitor_id"]
        zone_id = update["zone_id"]
        sku_zone = update["sku_zone"]
        confidence = update["confidence"]
        
        prev_zone_info = self.visitor_zones.get(visitor_id)
        
        # Case A: Entered a new zone
        if zone_id and (not prev_zone_info or prev_zone_info["zone_id"] != zone_id):
            # Exit previous zone if they were in one
            if prev_zone_info:
                self.emit_zone_exit(visitor_id, prev_zone_info["zone_id"], timestamp, camera_id, is_staff, prev_zone_info["sku_zone"], session_seq)
                if prev_zone_info["zone_id"] == "Cash Counter":
                    self.billing_queue.discard(visitor_id)
                    
            # Enter new zone
            self.visitor_zones[visitor_id] = {
                "zone_id": zone_id,
                "entered_at": timestamp,
                "last_dwell_at": timestamp,
                "sku_zone": sku_zone
            }
            self.emit_zone_enter(visitor_id, zone_id, timestamp, camera_id, is_staff, sku_zone, session_seq)
            
            # Special case: Billing Queue Join
            if zone_id == "Cash Counter" and not is_staff:
                # Queue depth includes others in the queue (before this visitor joined)
                # plus this visitor = current billing queue size
                self.billing_queue.add(visitor_id)
                queue_depth = len(self.billing_queue)
                if queue_depth > 0:
                    evt = self._create_event("BILLING_QUEUE_JOIN", visitor_id, camera_id, timestamp, 
                                             zone_id=zone_id, is_staff=False, confidence=confidence, 
                                             queue_depth=queue_depth, sku_zone=sku_zone, session_seq=session_seq + 1)
                    self.events.append(evt)
                    print(f"Emitted BILLING_QUEUE_JOIN: visitor_id={visitor_id}, depth={queue_depth}, time={timestamp}")
                    
        # Case B: Left a zone
        elif not zone_id and prev_zone_info:
            self.emit_zone_exit(visitor_id, prev_zone_info["zone_id"], timestamp, camera_id, is_staff, prev_zone_info["sku_zone"], session_seq)
            if prev_zone_info["zone_id"] == "Cash Counter":
                self.billing_queue.discard(visitor_id)
            del self.visitor_zones[visitor_id]
            
        # Case C: Still in same zone, check for ZONE_DWELL (emitted every 30 seconds of continuous dwell)
        elif zone_id and prev_zone_info and prev_zone_info["zone_id"] == zone_id:
            dwell_sec = (timestamp - prev_zone_info["last_dwell_at"]).total_seconds()
            if dwell_sec >= 30.0:
                total_dwell_ms = int((timestamp - prev_zone_info["entered_at"]).total_seconds() * 1000)
                self.emit_zone_dwell(visitor_id, zone_id, timestamp, camera_id, is_staff, total_dwell_ms, sku_zone, session_seq)
                self.visitor_zones[visitor_id]["last_dwell_at"] = timestamp

    def flush(self) -> List[Dict[str, Any]]:
        evts = self.events
        self.events = []
        return evts
        
    def save(self, output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "a") as f:
            for event in self.events:
                f.write(json.dumps(event) + "\n")
        print(f"Saved {len(self.events)} events to {output_path}")
        self.events = []
