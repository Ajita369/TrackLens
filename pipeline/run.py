import os
import argparse
import cv2
import json
from datetime import datetime, timedelta, timezone
from pipeline.detect import PersonDetector
from pipeline.tracker import TrackerManager
from pipeline.zones import ZoneClassifier, EntryThreshold
from pipeline.events import EventEmitter
from pipeline.staff import StaffDetector
from pipeline.pos_correlator import POSCorrelator

def parse_args():
    parser = argparse.ArgumentParser(description="TrackLens CCTV Video Analytics Pipeline")
    parser.add_argument("--data-dir", type=str, default="./data", help="Path to input data directory")
    parser.add_argument("--output-dir", type=str, default="./data/output", help="Path to output events directory")
    parser.add_argument("--skip-frames", type=int, default=2, help="Number of frames to skip (process every N+1 frame)")
    parser.add_argument("--model-path", type=str, default="yolov8s.pt", help="Path to YOLOv8 model weights")
    return parser.parse_args()

def process_clip(
    video_path: str,
    camera_id: str,
    detector: PersonDetector,
    tracker_manager: TrackerManager,
    event_emitter: EventEmitter,
    staff_detector: StaffDetector,
    zone_classifier: ZoneClassifier,
    entry_threshold: EntryThreshold,
    skip_frames: int,
    base_time: datetime
):
    print(f"\n--- Processing {video_path} ({camera_id}) ---")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Could not open video file {video_path}")
        return
        
    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if fps <= 0:
        fps = 15.0  # Fallback to default
        
    # Date string formatted for visitor IDs
    date_str = base_time.strftime("%Y%m%d")
    
    frame_idx = 0
    processed_count = 0
    
    while True:
        ret, frame = cap.read()
        if not ret:
            break
            
        # Process every (skip_frames + 1)-th frame
        if frame_idx % (skip_frames + 1) == 0:
            # Video time calculation
            offset_sec = frame_idx / fps
            current_time = base_time + timedelta(seconds=offset_sec)
            
            # 1. Run detection
            detections = detector.process_frame(frame)
            
            # 2. Run tracking and zone classification
            tracking_updates = tracker_manager.update(
                detections=detections,
                frame=frame,
                camera_id=camera_id,
                zone_classifier=zone_classifier,
                entry_threshold=entry_threshold,
                timestamp_sec=offset_sec,
                date_str=date_str
            )
            
            # 3. Process tracking updates
            for update in tracking_updates:
                visitor_id = update["visitor_id"]
                zone_id = update["zone_id"]
                crossed_event = update["crossed_event"]
                bbox = update["bbox"]
                confidence = update["confidence"]
                
                # Check is_staff status from staff detector
                is_staff, staff_conf = staff_detector.check_is_staff(visitor_id, total_frames // (skip_frames + 1))
                
                # Store visitor appearance in staff detector
                staff_detector.add_visitor_frame(
                    visitor_id=visitor_id, 
                    frame=frame, 
                    bbox=bbox, 
                    zone_id=zone_id, 
                    camera_id=camera_id
                )
                
                # Retrieve current sequence sequence number from event emitter zone state
                session_seq = 1
                if visitor_id in event_emitter.visitor_zones:
                    # Increment session sequence
                    session_seq = event_emitter.visitor_zones[visitor_id].get("session_seq", 1) + 1
                
                # Handle ENTRY / EXIT threshold crossings (CAM 3 only)
                if camera_id == "CAM 3":
                    if crossed_event == "ENTRY":
                        # Save embedding for cross-camera Re-ID pool
                        emb_fn = update["frame_embedding_fn"]
                        emb = emb_fn()
                        tracker_manager.reid_matcher.add_exited(visitor_id, emb, offset_sec)
                        
                        event_emitter.emit_entry(visitor_id, current_time, camera_id, confidence, is_staff, session_seq)
                    elif crossed_event == "EXIT":
                        # Save embedding to recently exited pool for Re-Entry detection
                        emb_fn = update["frame_embedding_fn"]
                        emb = emb_fn()
                        tracker_manager.reid_matcher.add_exited(visitor_id, emb, offset_sec)
                        
                        event_emitter.emit_exit(visitor_id, current_time, camera_id, confidence, is_staff, session_seq)
                
                # Process zone changes and dwells
                event_emitter.on_tracking_update(
                    update=update,
                    timestamp=current_time,
                    camera_id=camera_id,
                    is_staff=is_staff,
                    session_seq=session_seq
                )
                
            processed_count += 1
            if processed_count % 100 == 0:
                percent = (frame_idx / total_frames) * 100
                print(f"Processing progress: frame {frame_idx}/{total_frames} ({percent:.1f}%)")
                
        frame_idx += 1
        
    cap.release()
    print(f"Finished processing clip. Total processed frames: {processed_count}")

def main():
    args = parse_args()
    
    # Store ID
    store_id = "ST1008"
    
    # Define file paths
    pos_csv_path = os.path.join(args.data_dir, "Brigade_Bangalore_10_April_26 (1)bc6219c.csv")
    output_file_path = os.path.join(args.output_dir, store_id, "events.jsonl")
    
    # Ensure output store directory exists
    os.makedirs(os.path.dirname(output_file_path), exist_ok=True)
    if os.path.exists(output_file_path):
        os.remove(output_file_path) # Clear old events
        
    # Baseline start time: 2026-04-10 20:10:00 UTC (from CCTV overlay)
    base_time = datetime(2026, 4, 10, 20, 10, 0, tzinfo=timezone.utc)
    
    # 1. Initialize detector, staff detector, and event emitter
    print("Initializing models...")
    detector = PersonDetector(model_path=args.model_path, conf_threshold=0.3)
    staff_detector = StaffDetector()
    event_emitter = EventEmitter(store_id=store_id)
    
    # Initialize a shared tracker manager for cross-camera Re-ID pool mapping
    tracker_manager = TrackerManager(store_id=store_id)
    
    # 2. Camera mapping
    # Process order: Entry camera FIRST, then Floor cameras, then Billing camera last
    cameras = [
        {"id": "CAM 3", "file": "CAM 3.mp4", "role": "entry"},   # Entry/Exit threshold
        {"id": "CAM 1", "file": "CAM 1.mp4", "role": "floor"},   # Product floor
        {"id": "CAM 2", "file": "CAM 2.mp4", "role": "floor"},   # Product floor
        {"id": "CAM 5", "file": "CAM 5.mp4", "role": "billing"}  # Billing queue area
    ]
    
    # Process each camera clip
    for cam in cameras:
        cam_id = cam["id"]
        filename = cam["file"]
        video_path = os.path.join(args.data_dir, "clips", filename)
        
        if not os.path.exists(video_path):
            print(f"Warning: Clip file {video_path} not found. Skipping...")
            continue
            
        # Instantiate spatial helper classes
        zone_classifier = ZoneClassifier(store_id, cam_id)
        entry_threshold = EntryThreshold() if cam_id == "CAM 3" else None
        
        process_clip(
            video_path=video_path,
            camera_id=cam_id,
            detector=detector,
            tracker_manager=tracker_manager,
            event_emitter=event_emitter,
            staff_detector=staff_detector,
            zone_classifier=zone_classifier,
            entry_threshold=entry_threshold,
            skip_frames=args.skip_frames,
            base_time=base_time
        )
        
    # 3. Calibrate staff templates and run final staff filter check on events
    print("\nCalibrating staff uniform color templates...")
    # Assume 15fps and processing every 3rd frame (skip=2), so effective fps = 5
    # Total frames is processed frames for entry/floor cameras
    total_effective_frames = 200 # Approx frame window size
    staff_detector.calibrate_uniform_templates(total_frames=total_effective_frames)
    
    # Flush all events generated so far
    raw_events = event_emitter.flush()
    print(f"Emitted {len(raw_events)} raw events. Post-processing staff flag...")
    
    # Apply calibrated staff checks to flag employees
    for event in raw_events:
        vid = event["visitor_id"]
        is_staff, staff_conf = staff_detector.check_is_staff(vid, total_frames=total_effective_frames)
        if is_staff:
            event["is_staff"] = True
            # Staff events are excluded from customer billing abandon calculations
            if event["event_type"] == "BILLING_QUEUE_JOIN":
                event["event_type"] = "ZONE_ENTER" # Convert to regular enter for staff
                event["metadata"]["queue_depth"] = None
                
    # 4. Run POS transaction correlation
    print("\nRunning POS Transaction Correlation...")
    correlator = POSCorrelator(pos_csv_path)
    final_events = correlator.correlate(raw_events, store_id)
    
    # Write to events.jsonl
    with open(output_file_path, "w") as f:
        for event in final_events:
            f.write(json.dumps(event) + "\n")
            
    print(f"\n=== Pipeline Completed! Generated {len(final_events)} final events ===")
    print(f"Output stored in {output_file_path}")

if __name__ == "__main__":
    main()
