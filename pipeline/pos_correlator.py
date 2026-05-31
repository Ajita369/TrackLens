import csv
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

class POSCorrelator:
    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        
    def load_transactions(self, store_id: str) -> List[Dict[str, Any]]:
        """
        Loads and parses transactions for the given store_id from the CSV.
        """
        transactions = []
        if not os.path.exists(self.csv_path):
            print(f"Warning: POS file {self.csv_path} does not exist.")
            return transactions
            
        with open(self.csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Filter by store_id
                if row.get("store_id") != store_id:
                    continue
                    
                order_date = row.get("order_date")
                order_time = row.get("order_time")
                order_id = row.get("order_id")
                
                # Retrieve amount (GMV, NMV or total_amount)
                try:
                    amount = float(row.get("total_amount", 0.0) or row.get("NMV", 0.0) or 0.0)
                except ValueError:
                    amount = 0.0
                    
                if order_date and order_time:
                    try:
                        # Format is DD-MM-YYYY HH:MM:SS
                        dt_str = f"{order_date.strip()} {order_time.strip()}"
                        dt = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S")
                        dt = dt.replace(tzinfo=timezone.utc)
                        
                        transactions.append({
                            "transaction_id": order_id,
                            "timestamp": dt,
                            "amount": amount
                        })
                    except Exception as e:
                        print(f"Error parsing transaction row {row}: {e}")
                        
        # Sort transactions chronologically
        transactions.sort(key=lambda x: x["timestamp"])
        return transactions

    def correlate(self, events: List[Dict[str, Any]], store_id: str) -> List[Dict[str, Any]]:
        """
        Correlates billing queue joins with transactions to determine conversions and abandonments.
        Appends BILLING_QUEUE_ABANDON events for visitors who did not make a purchase.
        """
        transactions = self.load_transactions(store_id)
        if not transactions:
            print(f"No POS transactions found for store {store_id}. All queue joins will be marked as abandoned.")
            
        # 1. Gather all BILLING_QUEUE_JOIN events
        joins = [e for e in events if e["event_type"] == "BILLING_QUEUE_JOIN"]
        joins.sort(key=lambda x: datetime.fromisoformat(x["timestamp"].replace("Z", "+00:00")))
        
        # 2. Gather all ZONE_EXIT events for "Cash Counter" (billing zone) to use as abandon timestamps
        exits = {
            e["visitor_id"]: datetime.fromisoformat(e["timestamp"].replace("Z", "+00:00"))
            for e in events 
            if e["event_type"] == "ZONE_EXIT" and e["zone_id"] == "Cash Counter"
        }
        
        # 3. Correlate using greedy matching
        # Track matched visitor IDs
        matched_visitors = set()
        matched_txs = set()
        
        # Parse join event timestamps
        join_times = []
        for j in joins:
            t = datetime.fromisoformat(j["timestamp"].replace("Z", "+00:00"))
            join_times.append((j, t))
            
        for tx in transactions:
            tx_time = tx["timestamp"]
            tx_id = tx["transaction_id"]
            
            # Find all unmatched joins in the 5-minute window before the transaction
            candidates = []
            for j_evt, j_time in join_times:
                vid = j_evt["visitor_id"]
                if vid in matched_visitors:
                    continue
                    
                # 5-minute window condition: j_time <= tx_time and j_time >= tx_time - 5min
                time_diff = (tx_time - j_time).total_seconds()
                if 0.0 <= time_diff <= 300.0:
                    candidates.append((j_evt, j_time, time_diff))
                    
            if candidates:
                # Greedy: pick the closest in time (smallest time_diff)
                candidates.sort(key=lambda x: x[2])
                matched_evt = candidates[0][0]
                matched_vid = matched_evt["visitor_id"]
                
                matched_visitors.add(matched_vid)
                matched_txs.add(tx_id)
                print(f"Correlated visitor {matched_vid} with POS transaction {tx_id} (offset {candidates[0][2]:.1f}s)")
                
        # 4. Generate BILLING_QUEUE_ABANDON events for visitors who joined the queue but were not matched
        abandon_events = []
        for j_evt, j_time in join_times:
            vid = j_evt["visitor_id"]
            if vid in matched_visitors:
                continue
                
            # Visitor abandoned. Find their exit timestamp, fallback to 1 minute after join
            exit_time = exits.get(vid)
            if not exit_time:
                exit_time = j_time + timedelta(minutes=1)
                
            timestamp_str = exit_time.isoformat().replace("+00:00", "Z")
            if not timestamp_str.endswith("Z"):
                timestamp_str += "Z"
                
            # Create BILLING_QUEUE_ABANDON event
            abandon_evt = {
                "event_id": str(uuid.uuid4()),
                "store_id": j_evt["store_id"],
                "camera_id": j_evt["camera_id"],
                "visitor_id": vid,
                "event_type": "BILLING_QUEUE_ABANDON",
                "timestamp": timestamp_str,
                "zone_id": j_evt["zone_id"],
                "dwell_ms": None,
                "is_staff": False,
                "confidence": j_evt["confidence"],
                "metadata": {
                    "queue_depth": 0,  # Queue depth is set to 0 upon abandon
                    "sku_zone": j_evt["metadata"].get("sku_zone"),
                    "session_seq": j_evt["metadata"].get("session_seq", 1) + 1
                }
            }
            abandon_events.append(abandon_evt)
            print(f"Emitted BILLING_QUEUE_ABANDON for visitor {vid} at {timestamp_str}")
            
        # Combine original events and newly generated abandon events
        all_events = events + abandon_events
        # Sort chronologically by timestamp
        all_events.sort(key=lambda x: x["timestamp"])
        return all_events
