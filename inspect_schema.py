"""
Run this first, before touching main.py.

It prints every table in nba.sqlite and its columns, so you can fix the
SCHEMA_CONTEXT string in main.py to match your actual copy of the database
(Kaggle dataset versions occasionally differ slightly in column names).

Usage:
    python inspect_schema.py nba.sqlite
"""
import sqlite3
import sys


def main(db_path: str):
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cur.fetchall()]

    print(f"Found {len(tables)} tables:\n")
    for table in tables:
        print(f"== {table} ==")
        cur.execute(f"PRAGMA table_info('{table}')")
        for col in cur.fetchall():
            # col: (cid, name, type, notnull, dflt_value, pk)
            print(f"  {col[1]:<30} {col[2]}")
        cur.execute(f"SELECT COUNT(*) FROM '{table}'")
        count = cur.fetchone()[0]
        print(f"  rows: {count}\n")

    conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "nba.sqlite"
    main(db_path)
