import sqlite3

# Connect to your existing database
conn = sqlite3.connect('signers.db')
c = conn.cursor()

# Check if 'email' column already exists
c.execute("PRAGMA table_info(signers)")
columns = [col[1] for col in c.fetchall()]

if 'email' not in columns:
    c.execute('ALTER TABLE signers ADD COLUMN email TEXT')
    print("✅ 'email' column added successfully.")
else:
    print("ℹ️ 'email' column already exists. No changes made.")

conn.commit()
conn.close()
