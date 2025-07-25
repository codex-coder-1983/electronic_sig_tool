import sqlite3

# Connect to (or create) a new SQLite database file
conn = sqlite3.connect('signers.db')

# Create a cursor object to run SQL commands
c = conn.cursor()

# Create the "signers" table
c.execute('''
    CREATE TABLE signers (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        x INTEGER NOT NULL,
        y INTEGER NOT NULL,
        has_signed INTEGER DEFAULT 0,
        signature_file TEXT
    )
''')

# Save changes and close the connection
conn.commit()
conn.close()

print("✅ Database and signers table created successfully.")
