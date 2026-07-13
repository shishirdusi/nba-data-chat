# Schema — Chat With Your NBA Data

## Dataset

Source: wyattowalsh/basketball on Kaggle — a pre-built SQLite database of NBA game, team,
player, and draft data.

The full database has 16 tables. This project uses a trimmed subset of 6, chosen to cover team
performance, game results, attendance, and draft/player bio questions while keeping the
schema small enough for reliable NL-to-SQL generation.

This same information is also available live in the app itself — click the "Schema" button in
frontend.html to see every table, its columns, and its current row count, without needing to read
this file.

## Tables in use

### Team
One row per franchise.
```
id, full_name, abbreviation, nickname, city, state, year_founded
```

### Game
One row per game. Team-level box score stats for both home and away sides.
```
game_id, season_id, season_type, game_date,
team_id_home, team_abbreviation_home, team_name_home,
wl_home, pts_home, reb_home, ast_home, fg3m_home,
team_id_away, team_abbreviation_away, team_name_away,
wl_away, pts_away, reb_away, ast_away, fg3m_away
```
wl_home/wl_away are 'W' or 'L'. season_type distinguishes 'Regular Season', 'Playoffs', 'Pre
Season', and All-Star games (see known issues below).

### game_info
Attendance data, joins to game on game_id.
```
game_id, game_date, attendance
```

### common_player_info
Player bio and career info. No scoring stats.
```
person_id, first_name, last_name, position,
team_id, team_abbreviation, draft_year, season_exp,
from_year, to_year
```

### draft_history
One row per drafted player.
```
person_id, player_name, season, round_number, round_pick,
overall_pick, team_abbreviation
```

### player
Basic player lookup. No scoring stats.
```
id, full_name, is_active
```

## Known limitation: no player scoring stats

There is no player-season or player-career stats table in this dataset. Points/rebounds/assists
per player only exist buried inside play_by_play(13.6M rows of play-by-play text), which is
excluded from this project's schema as impractical to aggregate reliably.

As a result, questions like "who scored the most points in a career" are correctly refused by
the app rather than answered with invented data — see the demo question list below.

## Known data quality issues (found via testing)

Two of the three issues below are now fixed by running clean_data.py(pandas) once against a
fresh copy of nba.sqlite, before starting the app. The script is idempotent — running it twice
doesn't cause problems, it just finds nothing left to fix the second time.

1. Attendance outlier — FIXED by clean_data.py: game_info.attendance contained at
   least one clearly erroneous value — 200,049 for game_id 0029400853, which is not
   physically possible for any NBA arena. clean_data.py nulls out any attendance value
   over 25,000 (a generous upper bound; the largest NBA arenas seat ~20,000-21,000)
   rather than guessing a "correct" replacement.

2. Inconsistent All-Star labeling — FIXED by clean_data.py: season_type contained both
   'All Star' and 'All-Star' as separate string values for the same category, which split what
   should be one group into two under GROUP BY season_type. The script normalizes
   both to 'All-Star'.

3. All-Star/exhibition games mixed into "all-time" superlatives — NOT fixed,
   documented only: Because game contains All-Star Game rows alongside real franchise
   games, "all-time" queries about single-game records (most points, most three-pointers,
   most wins) can surface All-Star team results (e.g. "Team LeBron") rather than actual
   franchises, unless the query explicitly filters season_type IN ('Regular Season',
   'Playoffs'). This showed up across three separate demo questions during testing. Fixing
   this properly would mean deciding whether All-Star games belong in the queryable
   schema at all, which felt like a bigger call than the other two fixes — so I left it as a
   documented limitation instead of silently dropping data.

## Demo questions

1. Which team had the best regular-season record in the 2015-16 season?
2. Which team scored the most total points in a single game, all-time?
3. Compare the average rebounds per game for two named teams in a given season.
4. Which team had the highest attendance for a single game?
5. How does average attendance compare between regular season and playoff games?
6. Which team made the most three-pointers as a team in a single game?
7. What was a specific team's playoff record in a given season?
8. Who scored the most points in a career, all-time? (deliberately unanswerable — tests the
   hallucination guardrail)
9. Which draft class had the most first-round picks who played 10+ years?
10. Which team has the most total wins across all seasons in the dataset?
