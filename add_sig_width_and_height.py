# add_sig_width_and_height.py

import sqlite3

db_path = "signers.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("ALTER TABLE signers ADD COLUMN sig_width REAL DEFAULT 100")
cursor.execute("ALTER TABLE signers ADD COLUMN sig_height REAL DEFAULT 50")

conn.commit()
conn.close()

print("Added sig_width and sig_height columns with defaults.")
