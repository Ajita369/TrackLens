import sqlite3

conn = sqlite3.connect("data/tracklens.db")
conn.row_factory = sqlite3.Row

print("=== BILLING_QUEUE_JOIN EVENTS ===")
joins = conn.execute("SELECT visitor_id, timestamp, timestamp_epoch FROM events WHERE event_type='BILLING_QUEUE_JOIN'").fetchall()
for j in joins:
    print(f"Visitor: {j['visitor_id']}, Time: {j['timestamp']}, Epoch: {j['timestamp_epoch']}")

print("\n=== POS TRANSACTIONS ===")
txs = conn.execute("SELECT transaction_id, timestamp, timestamp_epoch FROM pos_transactions").fetchall()
for t in txs:
    print(f"TX: {t['transaction_id']}, Time: {t['timestamp']}, Epoch: {t['timestamp_epoch']}")
    
print("\n=== JOIN CORRELATION TEST ===")
# Test the JOIN query
res = conn.execute("""
    SELECT e.visitor_id, e.timestamp as event_time, p.transaction_id, p.timestamp as tx_time, 
           (p.timestamp_epoch - e.timestamp_epoch) as diff_ms
    FROM events e
    JOIN pos_transactions p 
      ON p.store_id = e.store_id
      AND p.timestamp_epoch BETWEEN e.timestamp_epoch AND (e.timestamp_epoch + 300000)
    WHERE e.event_type = 'BILLING_QUEUE_JOIN'
""").fetchall()
print(f"Matched rows: {len(res)}")
for r in res:
    print(f"Visitor {r['visitor_id']} at {r['event_time']} matched with TX {r['transaction_id']} at {r['tx_time']} (Diff: {r['diff_ms']/1000}s)")
