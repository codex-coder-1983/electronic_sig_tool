import sqlite3

conn = sqlite3.connect("signers.db")
c = conn.cursor()
c.execute("ALTER TABLE signers ADD COLUMN status TEXT DEFAULT 'pending'")
conn.commit()
conn.close()
