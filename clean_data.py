"""
Cleans known data quality issues in nba.sqlite, found during manual testing:

1. `game.season_type` has inconsistent labels for All-Star games
   ('All Star' vs 'All-Star') which splits one category into two under
   GROUP BY. This script normalizes both to 'All-Star'.

2. `game_info.attendance` contains at least one physically impossible value
   (200,049 for game_id 0029400853 — no NBA arena seats anywhere near that
   many people). This script nulls out any attendance value over 25,000
   (a generous upper bound; the largest NBA arenas seat ~20,000-21,000)
   rather than guessing a "correct" replacement value.

Run this ONCE after downloading nba.sqlite and before running the app.
It modifies the database in place — back up the original file first if
you want to keep an unmodified copy.

Usage:
    python3 clean_data.py nba.sqlite
"""
import sqlite3
import sys

import pandas as pd

ATTENDANCE_UPPER_BOUND = 25000


def clean_season_type(conn: sqlite3.Connection) -> int:
    df = pd.read_sql("SELECT game_id, season_type FROM game", conn)
    before = df["season_type"].value_counts().to_dict()

    df["season_type"] = df["season_type"].replace({"All Star": "All-Star"})

    changed = sum(
        v for k, v in before.items() if k == "All Star"
    )

    df.set_index("game_id")[["season_type"]].to_sql(
        "_season_type_update", conn, if_exists="replace"
    )
    conn.execute("""
        UPDATE game
        SET season_type = (
            SELECT season_type FROM _season_type_update
            WHERE _season_type_update.game_id = game.game_id
        )
    """)
    conn.execute("DROP TABLE _season_type_update")
    conn.commit()
    return changed


def clean_attendance(conn: sqlite3.Connection) -> int:
    df = pd.read_sql("SELECT game_id, attendance FROM game_info", conn)
    bad_mask = df["attendance"] > ATTENDANCE_UPPER_BOUND
    changed = int(bad_mask.sum())

    if changed:
        bad_ids = df.loc[bad_mask, "game_id"].tolist()
        placeholders = ",".join("?" for _ in bad_ids)
        conn.execute(
            f"UPDATE game_info SET attendance = NULL WHERE game_id IN ({placeholders})",
            bad_ids,
        )
        conn.commit()
    return changed


def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "nba.sqlite"
    conn = sqlite3.connect(db_path)

    st_changed = clean_season_type(conn)
    print(f"season_type: normalized {st_changed} row(s) from 'All Star' -> 'All-Star'")

    att_changed = clean_attendance(conn)
    print(f"attendance: nulled {att_changed} implausible value(s) over {ATTENDANCE_UPPER_BOUND}")

    conn.close()
    print("Done. nba.sqlite updated in place.")


if __name__ == "__main__":
    main()
