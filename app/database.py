import sqlite3
import os
import json
from contextlib import contextmanager
from typing import Generator

DATABASE_PATH = os.environ.get("DATABASE_PATH", "./data/tracklens.db")

def get_db_connection() -> sqlite3.Connection:
    # Ensure the parent directory exists
    db_dir = os.path.dirname(DATABASE_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    
    # Establish connection with a generous timeout to prevent locking issues
    conn = sqlite3.connect(DATABASE_PATH, timeout=30.0)
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
    finally:
        conn.close()
