import os

db_path = "signers.db"
if os.path.exists(db_path):
    os.remove(db_path)
    print("signers.db deleted ✅")
else:
    print("No signers.db found.")