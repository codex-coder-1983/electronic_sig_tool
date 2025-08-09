import sqlite3

# Connect to your database
conn = sqlite3.connect('signers.db')
c = conn.cursor()

# Add the 'page' column with a default value of 0 (meaning first page)
c.execute("ALTER TABLE signers ADD COLUMN page INTEGER DEFAULT 0")

conn.commit()
conn.close()

print("✅ 'page' column added successfully.")
