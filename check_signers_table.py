import sqlite3

conn = sqlite3.connect('signers.db')
c = conn.cursor()

c.execute("PRAGMA table_info(signers)")
columns = c.fetchall()

for col in columns:
    print(col)

conn.close()
