import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signers.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, name, pdf_filename, has_signed, signature_path FROM signers")
rows = c.fetchall()
for row in rows:
    print(row)
conn.close()
