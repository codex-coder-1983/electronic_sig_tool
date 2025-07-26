import sqlite3

conn = sqlite3.connect('signers.db')
c = conn.cursor()
c.execute('''
    CREATE TABLE IF NOT EXISTS signers (
        id TEXT PRIMARY KEY,
        name TEXT,
        email TEXT,
        x INTEGER,
        y INTEGER,
        signature_path TEXT,
        has_signed INTEGER DEFAULT 0
    )
''')
conn.commit()
conn.close()
