# SQLMate — AI SQL Assistant

A Streamlit app with four tools for working with SQL: natural-language-to-SQL
generation, dialect conversion (MySQL ↔ Oracle SQL), a database-free query
cost estimator, and SQL-to-English explanations.

## Features

| Page | What it does |
|---|---|
| **1. Natural Language → SQL** | Type a plain-English request, pick MySQL or Oracle SQL, and get a generated query (via Gemini). |
| **2. SQL Dialect Converter** | Paste SQL and convert MySQL ↔ Oracle SQL using SQLGlot. Flags constructs (ROWNUM, CONNECT BY, sequences, MERGE, etc.) that can't be translated 1:1, with an explanation why. |
| **3. Query Cost Estimator** | Static analysis (no DB connection) that scores complexity as Low/Medium/High/Very High, shows a progress bar, detected joins/GROUP BY/ORDER BY/DISTINCT/subqueries, and gives optimization suggestions. |
| **4. SQL → English** | Paste SQL and get a plain-English explanation covering SELECT, WHERE, JOIN, GROUP BY, ORDER BY, HAVING, LIMIT, and aggregate functions. Works instantly with no API key (rule-based); an optional AI toggle gives a richer explanation. |
| **5. Complexity Estimation** | Hand-written Big-O style structural analysis (e.g. `O(N₁ × N₂) + O(R log R)`) — counts tables/joins/subqueries, assumes naive nested-loop joins (no index info available statically), detects correlated vs. uncorrelated subqueries, and shows a step-by-step derivation with stated assumptions. Pure Python, no AI, no SQLGlot. |

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

The app opens at `http://localhost:8501`.

## Using AI features (Pages 1 and optionally 4)

The Gemini API key is never entered by the user — it's configured once by
whoever deploys the app, using Streamlit's built-in secrets store, so
end users (and recruiters trying the deployed app) never see or need a key
of their own.

**Local development:** create `.streamlit/secrets.toml` in the project root:

```toml
GEMINI_API_KEY = "your-key-here"
```

**Streamlit Community Cloud:** open your app's settings → **Secrets**, and
paste the same `GEMINI_API_KEY = "..."` line there. Never commit
`secrets.toml` to git — add it to `.gitignore`.

The app reads the key via `st.secrets.get("GEMINI_API_KEY")`. If it's not
configured, pages 1 and the AI-explanation toggle on page 4 show a clear
warning, while pages 2, 3, and 5 keep working with no key at all.

Google periodically retires model names (e.g. the entire Gemini 1.5 line was
shut down in 2026). The app defaults to `gemini-flash-latest`, an
auto-updating alias, so it should keep working without code changes. To
override it, add an optional second secret:

```toml
GEMINI_MODEL = "gemini-flash-latest"
```

**Trade-off to know:** since one key powers the app for everyone, your
Gemini free-tier quota is shared across all users of the deployed app.

## Project structure

```
sqlmate/
├── app.py                  # Streamlit entrypoint, 4-page sidebar nav
├── requirements.txt
├── modules/
│   ├── ai_client.py         # Gemini calls for NL→SQL and AI explain
│   ├── sql_converter.py     # SQLGlot-based MySQL ↔ Oracle conversion + caveats
│   ├── cost_estimator.py    # Heuristic static complexity scorer (sqlparse-based)
│   ├── complexity_estimator.py  # Big-O style structural analysis (pure Python, no AI)
│   └── sql_explainer.py     # Rule-based SQL → English (no AI needed)
```

## Notes / limitations

- **Cost Estimator is heuristic, not a real query planner.** It scores based
  on the presence/count of expensive constructs (joins, subqueries, DISTINCT,
  etc.) — it does not know table sizes, indexes, or actual execution plans.
- **Complexity Estimation is a separate, formal Big-O model** built from
  scratch: it assumes worst-case nested-loop joins (since no index
  information exists in raw SQL text), and reports its assumptions
  explicitly alongside the derivation. It's a teaching/reasoning tool, not
  a substitute for `EXPLAIN ANALYZE` on a real database.
- **Dialect conversion is best-effort.** SQLGlot handles most syntax
  differences well, but Oracle-specific features with no MySQL equivalent
  (PL/SQL packages, hierarchical CONNECT BY queries, sequences) are flagged
  rather than silently mistranslated.
- No authentication, no database connection, and no data is persisted
  between sessions — this is intentionally a lightweight, stateless tool.


