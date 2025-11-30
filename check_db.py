#!/usr/bin/env python3
"""Check database operations in both bot and worker."""
import sqlite3
import sys

db_path = "/app/media_lab.db"
if len(sys.argv) > 1:
    db_path = sys.argv[1]

try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT id, status, user_id, price, type FROM operations ORDER BY id DESC LIMIT 10")
    rows = cursor.fetchall()
    print(f"Database: {db_path}")
    print(f"Operations found: {len(rows)}")
    for row in rows:
        print(f"ID: {row[0]}, Status: {row[1]}, User: {row[2]}, Price: {row[3]}, Type: {row[4]}")
    conn.close()
except Exception as e:
    print(f"Error: {e}")

