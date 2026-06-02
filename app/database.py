import sqlite3
import os
import json
import csv
from datetime import datetime, timezone
from typing import Generator

DATABASE_PATH = os.environ.get("DATABASE_PATH", "./data/tracklens.db")
POS_CSV_PATH = os.environ.get("POS_CSV_PATH", "./data/Brigade_Bangalore_10_April_26 (1)bc6219c.csv")

def get_db_connection() -> sqlite3.Connection:
    # Ensure the parent directory exists
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    # Establish connection with a generous timeout to prevent locking issues
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    
    # Enable WAL mode for high concurrency
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn

def get_db() -> Generator[sqlite3.Connection, None, None]:
    conn = get_db_connection()
    try:
        yield conn
    finally:
        conn.close()

def load_pos_data(conn: sqlite3.Connection) -> None:
    """
    Parses pos_transactions.csv and seeds the pos_transactions table if empty.
    """
    # Check if we already have transactions loaded to avoid duplicate work
    cursor = conn.execute("SELECT COUNT(*) as cnt FROM pos_transactions")
    if cursor.fetchone()["cnt"] > 0:
        print("POS transactions already seeded.")
        return
        
    csv_path = POS_CSV_PATH
    if not os.path.exists(csv_path):
        # Scan data directory for matching CSV
        data_dir = os.path.dirname(DATABASE_PATH) or "./data"
        if os.path.exists(data_dir):
            files = os.listdir(data_dir)
            matching_files = [f for f in files if f.endswith(".csv") and ("pos" in f.lower() or "transaction" in f.lower())]
            if matching_files:
                csv_path = os.path.join(data_dir, matching_files[0])
                print(f"Dynamically resolved POS CSV file: {csv_path}")
                
    if not os.path.exists(csv_path):
        print(f"POS CSV file not found at {POS_CSV_PATH} and no matching file in data dir. Skipping initial seed.")
        return
        
    print(f"Seeding POS transactions from {csv_path}...")
    
    try:
        with open(csv_path, mode="r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            count = 0
            for row in reader:
                order_id = row.get("order_id")
                store_id = row.get("store_id")
                order_date = row.get("order_date")
                order_time = row.get("order_time")
                
                # Retrieve amount (GMV, NMV or total_amount)
                try:
                    amount = float(row.get("total_amount", 0.0) or row.get("NMV", 0.0) or 0.0)
                except ValueError:
                    amount = 0.0
                    
                if order_id and store_id and order_date and order_time:
                    try:
                        # Combine DD-MM-YYYY and HH:MM:SS
                        dt_str = f"{order_date.strip()} {order_time.strip()}"
                        dt = datetime.strptime(dt_str, "%d-%m-%Y %H:%M:%S")
                        dt = dt.replace(tzinfo=timezone.utc)
                        
                        timestamp_str = dt.isoformat().replace("+00:00", "Z")
                        timestamp_epoch = int(dt.timestamp() * 1000)
                        
                        conn.execute("""
                            INSERT OR IGNORE INTO pos_transactions (
                                transaction_id, store_id, timestamp, timestamp_epoch, basket_value_inr
                            ) VALUES (?, ?, ?, ?, ?)
                        """, (order_id, store_id, timestamp_str, timestamp_epoch, amount))
                        count += 1
                    except Exception as e:
                        pass
            
            conn.commit()
            print(f"Successfully seeded {count} POS transactions.")
    except Exception as e:
        print(f"Error seeding POS transactions: {e}")

def init_db() -> None:
    conn = get_db_connection()
    try:
        # Create events table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                camera_id TEXT NOT NULL,
                visitor_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                timestamp_epoch INTEGER NOT NULL,
                zone_id TEXT,
                dwell_ms INTEGER,
                is_staff INTEGER NOT NULL DEFAULT 0,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL,
                ingested_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
            );
        """)
        
        # Create POS transactions table for Phase 3 correlation
        conn.execute("""
            CREATE TABLE IF NOT EXISTS pos_transactions (
                transaction_id TEXT PRIMARY KEY,
                store_id TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                timestamp_epoch INTEGER NOT NULL,
                basket_value_inr REAL NOT NULL,
                ingested_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
            );
        """)
        
        # Create indexes for optimized queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_store_time ON events (store_id, timestamp_epoch);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_store_visitor ON events (store_id, visitor_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_events_store_type ON events (store_id, event_type);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pos_store_time ON pos_transactions (store_id, timestamp_epoch);")
        
        conn.commit()
        
        # Load POS data on initialization
        load_pos_data(conn)
        
    finally:
        conn.close()
