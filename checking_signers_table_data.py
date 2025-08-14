import sqlite3

DB_PATH = "signers.db"  # adjust if needed

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

# Show table list
tables = c.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall()
print("Tables:", [t["name"] for t in tables])

# Show schema of signers
schema = c.execute("PRAGMA table_info(signers);").fetchall()
print("\nSchema:")
for col in schema:
    col_dict = dict(col)
    print(f"{col_dict['cid']}: {col_dict['name']} ({col_dict['type']})")

# Show all rows
rows = c.execute("SELECT * FROM signers;").fetchall()
print("\nRows:")
for row in rows:
    print(dict(row))

conn.close()
