"""
Builds a small synthetic nba.sqlite with the same shape as the real
wyattowalsh/basketball dataset (subset used in main.py), so the backend
logic can be tested end to end before the real dataset is downloaded.

This is NOT real NBA data — just enough rows to sanity-check SQL execution,
joins, and the safety guardrails in main.py.

Usage:
    python build_mock_db.py
"""
import sqlite3
from pathlib import Path

DB_PATH = "mock_nba.sqlite"


def main():
    Path(DB_PATH).unlink(missing_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE team (
            team_id INTEGER PRIMARY KEY,
            full_name TEXT,
            abbreviation TEXT,
            city TEXT,
            year_founded INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE game (
            game_id INTEGER PRIMARY KEY,
            season_id TEXT,
            game_date TEXT,
            team_id_home INTEGER,
            team_abbreviation_home TEXT,
            wl_home TEXT,
            pts_home INTEGER,
            team_id_away INTEGER,
            team_abbreviation_away TEXT,
            wl_away TEXT,
            pts_away INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE player (
            id INTEGER PRIMARY KEY,
            full_name TEXT,
            is_active INTEGER
        )
    """)
    cur.execute("""
        CREATE TABLE common_player_info (
            person_id INTEGER PRIMARY KEY,
            first_name TEXT,
            last_name TEXT,
            position TEXT,
            team_id INTEGER,
            draft_year INTEGER,
            season_exp INTEGER
        )
    """)

    teams = [
        (1, "Golden State Warriors", "GSW", "San Francisco", 1946),
        (2, "Boston Celtics", "BOS", "Boston", 1946),
        (3, "Los Angeles Lakers", "LAL", "Los Angeles", 1947),
        (4, "Miami Heat", "MIA", "Miami", 1988),
    ]
    cur.executemany("INSERT INTO team VALUES (?,?,?,?,?)", teams)

    games = [
        (1, "2015-16", "2016-04-10", 1, "GSW", "W", 125, 2, "BOS", "L", 104),
        (2, "2015-16", "2016-04-12", 3, "LAL", "L", 90, 1, "GSW", "W", 112),
        (3, "2015-16", "2016-04-13", 2, "BOS", "W", 118, 4, "MIA", "L", 111),
        (4, "2022-23", "2023-01-15", 4, "MIA", "W", 108, 3, "LAL", "L", 101),
        (5, "2022-23", "2023-02-01", 1, "GSW", "L", 99, 4, "MIA", "W", 107),
    ]
    cur.executemany("INSERT INTO game VALUES (?,?,?,?,?,?,?,?,?,?,?)", games)

    players = [
        (1, "Steph Curry", 1),
        (2, "Jayson Tatum", 1),
        (3, "LeBron James", 1),
        (4, "Jimmy Butler", 1),
    ]
    cur.executemany("INSERT INTO player VALUES (?,?,?)", players)

    infos = [
        (1, "Steph", "Curry", "G", 1, 2009, 15),
        (2, "Jayson", "Tatum", "F", 2, 2017, 7),
        (3, "LeBron", "James", "F", 3, 2003, 21),
        (4, "Jimmy", "Butler", "F", 4, 2011, 13),
    ]
    cur.executemany("INSERT INTO common_player_info VALUES (?,?,?,?,?,?,?)", infos)

    conn.commit()
    conn.close()
    print(f"Built {DB_PATH} with {len(teams)} teams, {len(games)} games, "
          f"{len(players)} players.")


if __name__ == "__main__":
    main()
