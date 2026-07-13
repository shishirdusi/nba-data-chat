# Chat With Your NBA Data

I built this for my Paladio AI Summer Internship's 1 week project. It's a
"chat with your data" app for NBA stats — you type a question in English,
it answers you, and shows you the exact SQL it ran to get there.

## Stack

I kept this simple given the timeline:

- Database: SQLite, using the wyattowalsh/basketball dataset from Kaggle
- Backend: FastAPI (Python)
- NL → SQL: Direct calls to the Claude API — I felt as for a single
  "schema + question → SQL" step, a raw API call was faster to build and
  easier to debug
- Frontend: One plain HTML/JS file

## Setup

1. Grab the dataset. Download wyattowalsh/basketball from Kaggle, unzip it,
   and drop nba.sqlite into this folder next to main.py.

2. Clean the data. The raw dataset has a couple of known issues (see
   SCHEMA.md for details) — an inconsistent All-Star label and one
   physically impossible attendance value. Run this once, before starting
   the app:
   ```
   python3 clean_data.py nba.sqlite
   ```
   This modifies nba.sqlite in place. Back up the original file first if
   you want to keep an unmodified copy.

3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```

4. Set your API key:
   ```
   export ANTHROPIC_API_KEY=your_key_here
   ```

5. Start the backend:
   ```
   python3 -m uvicorn main:app --reload
   ```
   Leave this running — it's serving the API at http://localhost:8000.

6. Open frontend.html directly in your browser. Type a question, hit Ask.

## System workflow

Here's what actually happens when you ask a question:

- You type a question in frontend.html
- POST /ask → main.py
- Claude call #1: generate SQL
  - sees ONLY the schema in SCHEMA_CONTEXT (main.py)
  - told to say CANNOT_ANSWER if the schema can't support the question
- validate_sql()
  - single SELECT statement only
  - rejects INSERT/UPDATE/DELETE/DROP/ATTACH/etc.
  - forces a row LIMIT if the model didn't include one
- Execute against a READ-ONLY SQLite connection
- Claude call #2: phrase_answer()
  - turns the raw rows into one plain-English sentence
  - falls back to "Found N row(s)" if this call fails
  - Log the question, SQL, and result to audit_log.jsonl
- Response sent back to frontend.html:
  { answer, sql, columns, rows }
- UI renders the answer, a collapsible SQL panel, and a result table

The same schema is also exposed as structured JSON at GET /schema (with live row counts
pulled from the actual database), which powers the "Schema" button in the UI — click it to see
every table, its columns, and how many rows it has, without needing to open SCHEMA.md.

## What's in here

```
main.py             The backend — SQL generation, safety checks,
                 execution, and answer phrasing all live here

frontend.html         The chat UI, including the schema explorer panel

clean_data.py           Run once after downloading the dataset — fixes
                 the two known data quality issues (see SCHEMA.md)

inspect_schema.py          Small script I used to check the real table/column
                 names in nba.sqlite before writing the schema prompt

SCHEMA.md                 Full writeup of the schema + data issues I found

requirements.txt        Python deps

build_mock_db.py          Builds a fake test database — this is a dev tool,
                 not part of the actual app

test_backend_logic.py       Tests I ran against the mock db to sanity-check the
                  safety logic before touching the real dataset

audit_log.jsonl        Gets created when you run the app — one line per
                  question, logs what was asked, what SQL ran, and
                  whether it worked
```

## How I kept this safe

A few layers, so a bad or malicious question can't do anything destructive:

1. Claude only ever sees the schema I give it in SCHEMA_CONTEXT— I told it explicitly
   not to make up tables or columns it can't see.
2. If a question can't be answered with what's actually in the schema, Claude's told to say
   so instead of guessing.
3. Before any generated SQL touches the database, I check it: only a single SELECT is
   allowed, no INSERT/DELETE/DROP/ATTACH/etc., and I force a row limit even if the
   model forgot one.
4. On top of that, the database connection itself is open read-only — so even if something
   slipped past the keyword check, it physically can't write anything.
5. Every question gets logged to audit_log.jsonl— question, SQL, result count, and error if
   there was one.

## What actually worked

- Once I had the real dataset and an API key, the core loop — question in, SQL out,
  execute, answer back — just worked. I ran all 10 of my demo questions and every single
  one either gave a correct answer or surfaced a real, explainable data issue. Nothing
  crashed, nothing silently made something up.
- The safety checks held up — I tried breaking it with stacked statements and
  non-SELECT queries and they got rejected before ever reaching SQLite.
- The best result was asking "who scored the most points in a career, all-time?" — a
  question this schema genuinely can't answer since there's no player scoring stats table.
  Instead of inventing an answer, it correctly told me it didn't have the data. That's the
  whole point of the guardrails working.
- Adding a second Claude call just to phrase the raw result into a real sentence (instead of
  "Found 1 row(s)") made the whole thing feel much less like a raw database dump. If that
  call fails for whatever reason it falls back to the plain version instead of breaking the
  request.
- Writing clean_data.py to actually fix the two data issues (rather than just noting them)
  was straightforward with pandas — normalizing the All-Star label and nulling the
  impossible attendance value took about 20 lines total.
- Adding a schema explorer panel to the UI (backed by a structured / schema endpoint
  with live row counts) turned out to be a small change on top of what already existed —
  the endpoint just needed to return structured JSON instead of a text blob.

## What broke along the way

- I originally assumed there'd be a player-level stats table (points, rebounds, assists per
  player) — there isn't. Only team-level box scores. That killed a few of my planned demo
  questions, so I rewrote the list around what the schema actually supports instead of what
  I wished it had.
- Early on I had an invalid model name hardcoded, which just gave me a useless generic
  "Internal Server Error" until I added real error handling to surface what actually broke.
- I hadn't set up billing on my Anthropic account yet, which looked like the same kind of
  vague error until I dug into it.
- Pasted a question with a stray quotation mark in it once and it broke the generated SQL.

## What I'd do differently with more time

- I ended up fixing two of the three data issues I found (see clean_data.py and
  SCHEMA.md), but the third — All-Star games sitting in the same table as real franchise
  games — I only documented rather than fixed. A cleaner version would let you filter
  season_type IN ('Regular Season', 'Playoffs') by default for "all-time" superlative
  questions, or at least flag when an All-Star team shows up in a result.
- I'd add a retry step — if the generated SQL fails to execute, send the error back to
  Claude once and let it try to fix its own query.
- I'd round floating-point results (like average rebounds) to 1-2 decimals in the SQL itself
  instead of showing 10+ digits of precision in the table.
