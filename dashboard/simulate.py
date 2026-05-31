import argparse
import sys
import os
import json
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

def parse_args():
    parser = argparse.ArgumentParser(description="TrackLens Event Replay Simulator")
    parser.add_argument(
        "--store",
        type=str,
        required=True,
        help="Store identifier (e.g., STORE_BLR_002 or ST1008)"
    )
    parser.add_argument(
        "--speed",
        type=float,
        default=10.0,
        help="Speed multiplier for playback (default: 10.0)"
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="TrackLens API root URL (default: http://localhost:8000)"
    )
    return parser.parse_args()

def parse_timestamp(ts_str):
    # Standardize 'Z' to offset '+00:00' to support fromisoformat in older Pythons
    clean_ts = ts_str.replace("Z", "+00:00")
    return datetime.fromisoformat(clean_ts)

def post_batch_with_retry(api_url, events, max_retries=10):
    url = f"{api_url.rstrip('/')}/events/ingest"
    payload = json.dumps({"events": events}).encode("utf-8")
    
    backoff = 1.0
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5.0) as response:
                status = response.status
                body = response.read().decode("utf-8")
                if status in (200, 207):
                    return True
                else:
                    print(f"Error: API returned status {status}. Response: {body}")
        except urllib.error.URLError as e:
            # Typically Connection Refused or DNS failure
            print(f"Connection error to API: {e.reason}. API may not be running yet.")
        except Exception as e:
            print(f"Unexpected error posting batch: {e}")
            
        print(f"Retrying ingestion in {backoff:.1f} seconds (Attempt {attempt+1}/{max_retries})...")
        time.sleep(backoff)
        backoff = min(backoff * 2.0, 30.0)
        
    print("Fatal: Failed to send batch to API after maximum retries.")
    return False

def main():
    args = parse_args()
    
    # 1. Locate events file
    events_path = f"data/output/{args.store}/events.jsonl"
    if not os.path.exists(events_path):
        # Check if the fallback store ID schema works (e.g. ST1008)
        print(f"Error: Events file not found at {events_path}")
        
        # Look for folders in data/output to help user
        if os.path.exists("data/output"):
            available = os.listdir("data/output")
            print(f"Available stores in data/output: {available}")
        sys.exit(1)
        
    print(f"Reading events for store {args.store} from {events_path}...")
    
    # 2. Parse events
    events = []
    with open(events_path, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                evt = json.loads(line)
                dt = parse_timestamp(evt["timestamp"])
                events.append((dt, evt))
            except Exception as e:
                print(f"Warning: Skipping malformed line {line_num}: {e}")
                
    if not events:
        print("Error: No events found to replay.")
        sys.exit(1)
        
    # Sort events chronologically by timestamp
    events.sort(key=lambda x: x[0])
    total_events = len(events)
    print(f"Loaded {total_events} events. Timeline spans from {events[0][0].isoformat()} to {events[-1][0].isoformat()}.")
    print(f"Simulating replay at {args.speed}x speed multiplier...")
    
    # 3. Group events into batches of 1-second windows
    batches = []
    current_batch = []
    batch_start_time = None
    
    for dt, evt in events:
        if not current_batch:
            current_batch.append((dt, evt))
            batch_start_time = dt
        elif (dt - batch_start_time).total_seconds() <= 1.0:
            current_batch.append((dt, evt))
        else:
            batches.append(current_batch)
            current_batch = [(dt, evt)]
            batch_start_time = dt
            
    if current_batch:
        batches.append(current_batch)
        
    print(f"Grouped events into {len(batches)} batches based on 1-second timestamps.")
    
    # 4. Replay Loop
    replayed_count = 0
    prev_batch_time = None
    
    try:
        for idx, batch in enumerate(batches):
            batch_time = batch[0][0]
            
            # Calculate and execute delay
            if prev_batch_time is not None:
                delay = (batch_time - prev_batch_time).total_seconds()
                adjusted_delay = delay / args.speed
                if adjusted_delay > 0:
                    time.sleep(adjusted_delay)
            
            # Post the batch events payload
            batch_events = [evt for _, evt in batch]
            success = post_batch_with_retry(args.api_url, batch_events)
            if not success:
                print("Simulation aborted due to ingestion failure.")
                sys.exit(1)
                
            replayed_count += len(batch)
            percent = (replayed_count / total_events) * 100.0
            
            # Print status log
            current_time_str = batch_time.strftime("%H:%M:%S")
            print(f"Replayed {replayed_count}/{total_events} events ({percent:.1f}%) - Video time: {current_time_str}")
            
            prev_batch_time = batch_time
            
        print("Replay simulation completed successfully.")
        
    except KeyboardInterrupt:
        print("\nSimulation stopped by user (Ctrl+C). Exiting.")
        sys.exit(0)

if __name__ == "__main__":
    main()
