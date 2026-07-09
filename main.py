"""
FastAPI backend for "Chat with your NBA data".

Flow: question -> Claude (schema-aware SQL generation) -> validate SQL is safe
-> execute read-only against nba.sqlite -> return {answer, sql, columns, rows}.

Before running:
1. Put nba.sqlite in this folder (or set DB_PATH env var to its location).
2. Run inspect_schema.py against it and update SCHEMA_CONTEXT below to match
   the REAL table/column names in your copy of the dataset.
3. Set ANTHROPIC_API_KEY in your environment.
4. pip install -r requirements.txt
5. uvicorn main:app --reload
"""
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import anthropic

DB_PATH = os.environ.get("DB_PATH", "nba.sqlite")
LOG_PATH = os.environ.get("AUDIT_LOG_PATH", "audit_log.jsonl")
ROW_LIMIT = 200
MODEL = "claude-sonnet-5"

# ---------------------------------------------------------------------------
# Matches the real wyattowalsh/basketball nba.sqlite, verified via
# inspect_schema.py on 2026-07-08. NOTE: there is no player-season or
# player-career stats table in this dataset (points/rebounds/assists per
# player only exist buried in play_by_play, which is 13.6M rows of text and
# not used here). Player-level questions are limited to bio/draft info.
# ---------------------------------------------------------------------------
SCHEMA_CONTEXT = """
You can query the following tables. Only use the columns listed — if a
question needs data that isn't listed here (for example, individual player
scoring stats), say so instead of guessing a column name.

team(id, full_name, abbreviation, nickname, city, state, year_founded)
  -- one row per franchise

game(game_id, season_id, season_type, game_date,
     team_id_home, team_abbreviation_home, team_name_home,
     wl_home, pts_home, reb_home, ast_home, fg3m_home,
     team_id_away, team_abbreviation_away, team_name_away,
     wl_away, pts_away, reb_away, ast_away, fg3m_away)
  -- one row per game, team-level box score for both home and away side
  -- wl_home/wl_away are 'W' or 'L'. season_type distinguishes
  -- 'Regular Season' from 'Playoffs'.

game_info(game_id, game_date, attendance)
  -- join to game on game_id for attendance figures

common_player_info(person_id, first_name, last_name, position,
                    team_id, team_abbreviation, draft_year, season_exp,
                    from_year, to_year)
  -- player bio/career info. NO scoring stats here.

draft_history(person_id, player_name, season, round_number, round_pick,
              overall_pick, team_abbreviation)
  -- one row per drafted player

player(id, full_name, is_active)
  -- basic player lookup, NO scoring stats here
"""

SYSTEM_PROMPT = f"""You convert natural-language questions about NBA data into a
single SQLite SELECT query.

Schema:
{SCHEMA_CONTEXT}

Rules:
- Output ONLY the SQL query, nothing else. No explanation, no markdown fences.
- Only ever write a single SELECT statement. Never write INSERT, UPDATE,
  DELETE, DROP, ATTACH, PRAGMA, or multiple statements separated by semicolons.
- Only use tables and columns listed in the schema above. Never invent a
  column or table name.
- If the question cannot be answered with the columns available, respond with
  exactly: CANNOT_ANSWER: <one sentence explaining what data is missing>
- Always include a reasonable LIMIT if the result could be large.
"""

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|ATTACH|DETACH|PRAGMA|VACUUM|REPLACE|CREATE)\b",
    re.IGNORECASE,
)

app = FastAPI(title="Chat with your NBA data")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this before sharing beyond localhost
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


class AskRequest(BaseModel):
    question: str


def get_readonly_connection() -> sqlite3.Connection:
    db_file = Path(DB_PATH)
    if not db_file.exists():
        raise HTTPException(status_code=500, detail=f"Database not found at {DB_PATH}")
    return sqlite3.connect(f"file:{db_file}?mode=ro", uri=True)


def validate_sql(sql: str) -> str:
    """Raise if the SQL looks unsafe. Returns the (possibly limit-patched) SQL."""
    stripped = sql.strip().rstrip(";")

    if ";" in stripped:
        raise ValueError("Multiple statements are not allowed.")

    if not re.match(r"^\s*SELECT\b", stripped, re.IGNORECASE):
        raise ValueError("Only SELECT statements are allowed.")

    if FORBIDDEN_KEYWORDS.search(stripped):
        raise ValueError("Query contains a forbidden keyword.")

    if not re.search(r"\bLIMIT\b", stripped, re.IGNORECASE):
        stripped = f"{stripped} LIMIT {ROW_LIMIT}"

    return stripped


def log_audit(question: str, sql: str | None, row_count: int | None, error: str | None):
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "sql": sql,
        "row_count": row_count,
        "error": error,
    }
    with open(LOG_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


def generate_sql(question: str) -> str:
    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip()


def phrase_answer(question: str, columns: list[str], rows: list) -> str:
    """Turn raw query results into a one-sentence natural-language answer.

    Kept as a small, separate call (not the SQL-generation call) so a failure
    here never blocks returning the raw data — see the try/except around its
    call site in ask().
    """
    if not rows:
        return "No matching results were found for that question."

    # Cap what we send back to Claude to keep this fast/cheap; the raw table
    # is still returned to the UI regardless of what this phrasing looks like.
    preview_rows = rows[:20]
    result_text = json.dumps({"columns": columns, "rows": preview_rows})

    response = client.messages.create(
        model=MODEL,
        max_tokens=150,
        system=(
            "You answer a question in ONE short, natural sentence using only "
            "the query result data given to you. Do not mention SQL, tables, "
            "or columns. Just state the answer plainly, the way a person would."
        ),
        messages=[{
            "role": "user",
            "content": f"Question: {question}\nQuery result: {result_text}",
        }],
    )
    text = "".join(block.text for block in response.content if block.type == "text")
    return text.strip()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/schema")
def schema():
    return {"schema": SCHEMA_CONTEXT.strip()}


@app.post("/ask")
def ask(req: AskRequest):
    question = req.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        generated = generate_sql(question)
    except anthropic.APIError as e:
        log_audit(question, None, None, f"Anthropic API error: {e}")
        raise HTTPException(status_code=502, detail=f"Claude API call failed: {e}")

    if generated.startswith("CANNOT_ANSWER"):
        message = generated.split(":", 1)[-1].strip()
        log_audit(question, None, None, message)
        return {"answer": message, "sql": None, "columns": [], "rows": []}

    try:
        safe_sql = validate_sql(generated)
    except ValueError as e:
        log_audit(question, generated, None, str(e))
        raise HTTPException(status_code=400, detail=f"Generated query rejected: {e}")

    conn = get_readonly_connection()
    try:
        cur = conn.cursor()
        cur.execute(safe_sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
    except sqlite3.Error as e:
        log_audit(question, safe_sql, None, str(e))
        raise HTTPException(status_code=400, detail=f"Query execution failed: {e}")
    finally:
        conn.close()

    log_audit(question, safe_sql, len(rows), None)

    try:
        answer_text = phrase_answer(question, columns, rows)
    except anthropic.APIError:
        # Don't fail the whole request just because the phrasing step broke —
        # the data is still good, fall back to a plain factual line.
        answer_text = f"Found {len(rows)} row(s)."

    return {
        "answer": answer_text,
        "sql": safe_sql,
        "columns": columns,
        "rows": rows,
    }
