import sqlite3
import urllib.request
import json

conn = sqlite3.connect("data/tracklens.db")

# Insert mock transaction that is exactly 1 minute and 40 seconds after VIS_ST1008_20260410_0006 joined the queue
# Queue join epoch: 1775817620000 (2026-04-10 10:40:20 UTC)
# Transaction epoch: 1775817720000 (2026-04-10 10:42:00 UTC)
conn.execute("""
    INSERT OR REPLACE INTO pos_transactions (transaction_id, store_id, timestamp, timestamp_epoch, basket_value_inr) 
    VALUES ('MOCK_TX_1', 'ST1008', '2026-04-10T10:42:00Z', 1775817720000, 150.0)
""")
conn.commit()
print("Seeded mock transaction matching VIS_ST1008_20260410_0006.")

# Fetch metrics
resp = urllib.request.urlopen("http://localhost:8000/stores/ST1008/metrics?date=2026-04-10")
data = json.loads(resp.read().decode('utf-8'))
print("\nMetrics Response:")
print(json.dumps(data, indent=2))
