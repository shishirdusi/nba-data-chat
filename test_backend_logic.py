"""
Tests the SAFETY and EXECUTION logic in main.py against the mock database,
without calling the Claude API. This proves the guardrails work regardless
of what SQL a model generates -- run this before you even have an API key.

Usage:
    python test_backend_logic.py
"""
import os
import sqlite3
import sys

os.environ.setdefault("DB_PATH", "mock_nba.sqlite")
os.environ.setdefault("ANTHROPIC_API_KEY", "sk-test-placeholder-not-used-here")

sys.path.insert(0, os.path.dirname(__file__))
import main  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"


def check(label, condition):
    print(f"[{PASS if condition else FAIL}] {label}")
    return condition


def run():
    results = []

    # 1. Valid SELECT passes through unchanged (already has no LIMIT -> gets one added)
    sql = "SELECT full_name FROM team WHERE abbreviation = 'GSW'"
    safe = main.validate_sql(sql)
    results.append(check("adds LIMIT to unlimited query", "LIMIT 200" in safe))

    # 2. Rejects non-SELECT statements
    try:
        main.validate_sql("DELETE FROM team WHERE team_id = 1")
        results.append(check("rejects DELETE", False))
    except ValueError:
        results.append(check("rejects DELETE", True))

    # 3. Rejects multiple statements
    try:
        main.validate_sql("SELECT 1; DROP TABLE team;")
        results.append(check("rejects stacked statements", False))
    except ValueError:
        results.append(check("rejects stacked statements", True))

    # 4. Rejects forbidden keywords even inside a SELECT-looking string
    try:
        main.validate_sql("SELECT * FROM team; ATTACH DATABASE 'x' AS y")
        results.append(check("rejects ATTACH", False))
    except ValueError:
        results.append(check("rejects ATTACH", True))

    # 5. Actually executes a real query against the mock DB and returns rows
    conn = main.get_readonly_connection()
    cur = conn.cursor()
    cur.execute(main.validate_sql(
        "SELECT team_abbreviation_home, pts_home, pts_away "
        "FROM game WHERE season_id = '2015-16' ORDER BY pts_home DESC"
    ))
    rows = cur.fetchall()
    conn.close()
    results.append(check("executes real query, gets expected row count", len(rows) == 3))
    print(f"    -> rows: {rows}")

    # 6. Read-only connection actually blocks writes
    conn = main.get_readonly_connection()
    try:
        conn.execute("DELETE FROM team")
        conn.commit()
        results.append(check("read-only connection blocks writes", False))
    except sqlite3.OperationalError:
        results.append(check("read-only connection blocks writes", True))
    finally:
        conn.close()

    # 7. Audit log actually writes a line
    log_path = "test_audit_log.jsonl"
    if os.path.exists(log_path):
        os.remove(log_path)
    main.LOG_PATH = log_path
    main.log_audit("test question", "SELECT 1", 1, None)
    results.append(check("audit log writes a line", os.path.exists(log_path)))
    os.remove(log_path)

    print(f"\n{sum(results)}/{len(results)} checks passed")
    return all(results)


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
