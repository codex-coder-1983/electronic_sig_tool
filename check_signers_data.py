import sqlite3, os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "signers.db")

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("""
SELECT id, name, has_signed, signature_path
FROM signers
WHERE pdf_filename = 'Document_Acknowledgement_Form_QMS-FO-049_V3_-_Memo_Issuance_Process.pdf'
""")
rows = c.fetchall()
for row in rows:
    print(row)
conn.close()
