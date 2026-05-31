import os
import json
import urllib.request
import urllib.error
import argparse

API_URL = "http://localhost:8000/events/ingest"

def seed_from_output(output_dir: str):
    if not os.path.exists(output_dir):
        print(f"Error: Output directory {output_dir} does not exist.")
        return
        
    print(f"Scanning for events in {output_dir}...")
    
    events = []
    # Walk output directory to find events.jsonl
    for root, dirs, files in os.walk(output_dir):
        for file in files:
            if file == "events.jsonl":
                path = os.path.join(root, file)
                print(f"Reading events from {path}")
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            events.append(json.loads(line.strip()))
                            
    total_events = len(events)
    if total_events == 0:
        print("No events found to seed.")
        return
        
    print(f"Total events found: {total_events}")
    
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
                print("Error body:", e.read().decode("utf-8"))
            except Exception:
                pass
        except urllib.error.URLError as e:
            print(f"Batch {i//batch_size + 1} Connection Error: {e.reason}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=str, default="./data/output")
    args = parser.parse_args()
    seed_from_output(args.output_dir)
