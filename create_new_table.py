import sqlite3

conn = sqlite3.connect('signers.db')
c = conn.cursor()

# Create table if it doesn't exist
c.execute('''
    CREATE TABLE IF NOT EXISTS signers (
        id TEXT,
        name TEXT,
        email TEXT,
        x INTEGER,
        y INTEGER,
        pdf_filename TEXT,
        signature_path TEXT,
        has_signed INTEGER DEFAULT 0,
        page INTEGER,
        sig_width INTEGER,
        sig_height INTEGER
    )
''')

conn.commit()
conn.close()
print("✅ signers table created.")
