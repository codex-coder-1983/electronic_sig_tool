import sqlite3

db_path = "signers.db"  # change this to your actual path
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Set default page value for all existing rows where page is NULL
cursor.execute("UPDATE signers SET page = 0 WHERE page IS NULL")
conn.commit()

conn.close()

print("Page column updated for all existing signers.")
