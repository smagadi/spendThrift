# spendThrift

Local-first credit card spend analyzer: ingest statements (ICICI & HDFC CSV today), categorize transactions, and view dashboard analytics. Data stays on your machine in DuckDB.

## Requirements

- Python 3.9+
- macOS / Linux (developed on macOS)

## Setup

```bash
cd spendThrift   # repo folder name may include a trailing space on disk
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/init_db.py
```

Creates `data/spends.duckdb` (empty schema). That file is **gitignored** and must not be pushed.

## Run the app

```bash
make run
# or: ./scripts/run_app.sh
```

Open [http://localhost:8501](http://localhost:8501) (Streamlit default).

Run only one Streamlit instance at a time (DuckDB file lock).

## Tests

```bash
make test
# or: .venv/bin/pytest -q
```

Tests use in-memory DuckDB and fixtures under `tests/fixtures/` — no real bank files.

## Local data (not in Git)

| Path | Purpose |
|------|---------|
| `data/spends.duckdb` | Your cards, transactions, categories |
| `bankstatements /` | Real CSV exports for upload (ICICI, HDFC, …) |

Keep statement CSVs and the DuckDB file **outside Git**. `.gitignore` blocks `*.duckdb`, `bankstatements*/`, and WAL files.

For your own copies, create folders such as:

```text
bankstatements /ICICI/
bankstatements /hdfc/
```

Register cards in the UI (bank + last 4 + cardholder), then upload matching statements.

## Push to GitHub

1. Create an empty repository on GitHub (no README if you already have this one).
2. From the project root:

```bash
git init   # if not already a repo
git add .
git status   # confirm no .duckdb or bankstatements CSVs are staged
git commit -m "Initial commit: spendThrift MVP"
git remote add origin git@github.com:YOUR_USER/spendThrift.git
git branch -M main
git push -u origin main
```

Always run `git status` before pushing. If you ever committed a database or statement by mistake, rotate cards / treat the repo as compromised and use `git filter-repo` or BFG to purge history.

## Docs

- Product behavior: [`docs/prd.md`](docs/prd.md)
- Build order: [`docs/plan.md`](docs/plan.md)

## Supported ingest (MVP)

- **ICICI** — comma CSV (`Transaction Details` section)
- **HDFC** — tilde-delimited CSV (`~|~`), Visa and UPI cards (one card per file)

Axis and other banks: planned.
