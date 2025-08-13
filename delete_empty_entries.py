import sqlite3

# Connect to your SQLite DB
conn = sqlite3.connect('signers.db')
c = conn.cursor()

# Delete empty or unsigned entries
c.execute("""
DELETE FROM signers
WHERE signature_path IS NULL
   OR TRIM(signature_path) = ''
   OR has_signed = 0;
""")

# Commit changes and close
conn.commit()
conn.close()

print("Cleanup done ✅")
